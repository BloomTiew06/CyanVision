"""LARIS business assistant: question -> business tools -> answer.

AI path: any OpenAI-compatible chat-completions service (configured by environment variables, see README). The model
chooses tools from assistant_tools; the tools do every calculation; the model explains the results.
Fallback path (no AI configured, or the service fails): a small deterministic router answers common questions with
the same tools, and every such answer is labelled as a quick answer, not AI analysis.

Never sends owner names or supplier contacts to the model; only product-level business figures.
"""
import json
import os
import re
import socket
import time
import urllib.error
import urllib.request

import assistant_tools as T

HISTORY_TURNS = 10        # recent messages sent to the model for follow-ups (bounded context)
MAX_TOOL_ROUNDS = 5
TIMEOUT_S = 30

SYSTEM = """You are LARIS, a friendly, concise assistant for the owner of a small Malaysian grocery shop.
Rules:
- Get every number from the tools. Never estimate, invent or recalculate revenue, profit, stock or quantities.
- If a tool says data is missing or unavailable, say so plainly. Never make up product names or figures.
- Say which figures are recorded sales, which are LARIS calculations, and which are forecasts or estimates.
- You cannot send or place orders, buy anything, or change stock, and neither can a button. LARIS never places
  orders: the owner sends the order themselves from the Orders page (it opens a WhatsApp draft they send).
- Only after you call propose_order_change may you mention a Confirm button, and then only to change that one
  product's quantity in this week's order. Never tell the owner to press Confirm for anything else, and never say
  a change was made.
- Answer in plain English (no jargon), in this shape: a direct answer; the key figures (short list or small table);
  one or two sentences of why; the recommended next step. Use RM. Keep it under about 150 words unless asked."""


class ProviderError(Exception):
    """A friendly, user-facing explanation of why the AI service couldn't answer."""


def config(secrets=None):
    """AI settings from environment variables (or Streamlit secrets passed in). Enabled only with a key AND a model."""
    get = lambda k, d="": os.environ.get(k) or (secrets or {}).get(k) or d
    key, model = get("AI_API_KEY"), get("AI_MODEL")
    off = os.environ.get("LARIS_AI_DISABLED") == "1"   # kill switch (tests use it so they never call a service)
    return {"api_key": key, "model": model, "base_url": get("AI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            "enabled": bool(key and model) and not off}


def http_transport(cfg, payload, retries=1):
    """POST to {base_url}/chat/completions. Raises ProviderError with a plain explanation on any failure.
    A rate limit (429) is retried once after a short wait (free tiers allow only a few requests a minute)."""
    req = urllib.request.Request(f"{cfg['base_url']}/chat/completions", data=json.dumps(payload).encode("utf-8"),
                                 headers={"Authorization": f"Bearer {cfg['api_key']}",
                                          "Content-Type": "application/json",
                                          # some providers' firewalls reject Python's default user agent
                                          "User-Agent": "LARIS/2.1"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 429 and retries > 0:
            try:
                wait = min(float(e.headers.get("Retry-After", 3)), 8)
            except (TypeError, ValueError):
                wait = 3
            time.sleep(wait)
            return http_transport(cfg, payload, retries - 1)
        msg = {401: "the AI key was rejected", 403: "the AI service refused the request (the key may not be allowed to use this model)",
               404: "the AI model or address wasn't found", 429: "the AI service is busy or out of credit"}.get(
            e.code, f"the AI service returned an error ({e.code})")
        raise ProviderError(msg) from e
    except (urllib.error.URLError, socket.timeout, TimeoutError) as e:
        raise ProviderError("the AI service couldn't be reached or took too long") from e
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ProviderError("the AI service sent a reply LARIS couldn't read") from e


def _ai_answer(question, history, ctx, cfg, transport):
    week = ctx["week"]
    today = (f"\nThe planning week is {week['as_of']:%A %d %B %Y} to {week['end']:%d %b %Y}. Use dates exactly as "
             "the tools give them.")
    messages = [{"role": "system", "content": SYSTEM + today}]
    messages += [{"role": m["role"], "content": m["content"]} for m in history[-HISTORY_TURNS:]
                 if m["role"] in ("user", "assistant")]
    messages.append({"role": "user", "content": question})
    used, proposal = [], None
    for _ in range(MAX_TOOL_ROUNDS):
        data = transport(cfg, {"model": cfg["model"], "messages": messages, "tools": T.TOOL_SPECS,
                               "tool_choice": "auto", "temperature": 0.2})
        try:
            msg = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as e:
            raise ProviderError("the AI service sent an unexpected reply") from e
        calls = msg.get("tool_calls") or []
        if not calls:
            text = (msg.get("content") or "").strip()
            if not text:
                raise ProviderError("the AI service sent an empty reply")
            return {"text": text, "source": "ai", "tools": used, "proposal": proposal}
        messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
        for c in calls:
            name = c.get("function", {}).get("name", "")
            try:
                args = json.loads(c.get("function", {}).get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            result = T.run_tool(ctx, name, args)
            used.append(name)
            if name == "propose_order_change" and result.get("status") == "needs_confirmation":
                proposal = result
            messages.append({"role": "tool", "tool_call_id": c.get("id", name), "content": json.dumps(result)})
    raise ProviderError("the AI service didn't finish its answer")


def ask(question, history, ctx, cfg, memory, transport=None):
    """Answer one question. Returns {text, source: ai|fallback|error, tools, proposal}. Never raises."""
    question = (question or "").strip()
    if not question:
        return {"text": "Ask me anything about your shop's stock, sales or this week's order.", "source": "fallback",
                "tools": [], "proposal": None}
    if cfg.get("enabled"):
        try:
            return _ai_answer(question, history, ctx, cfg, transport or http_transport)
        except ProviderError as e:
            fb = fallback(question, ctx, memory)
            return {**fb, "source": "error",
                    "text": f"Sorry, I couldn't get an AI answer because {e}. Here's a quick answer from LARIS's own "
                            f"calculations instead:\n\n{fb['text']}"}
    return fallback(question, ctx, memory)


# ---------------- deterministic fallback: common questions, same tools, labelled as quick answers ----------------
def _rm(x):
    return "RM –" if x is None else f"RM {x:,.0f}"


def _table(head, rows):
    return "\n".join(["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] +
                     ["| " + " | ".join(str(c) for c in r) + " |" for r in rows])


def _days_txt(d):
    return "–" if d is None else f"{d:.1f} days"


def _restock(ctx, memory):
    d = T.get_restock_recommendations(ctx)
    items = d["items"]
    memory["last_products"] = [i["name"] for i in items]
    if not items:
        return "Nothing needs ordering this week: your stock covers expected sales."
    urgent = [i for i in items if i["runs_out_before_delivery"]]
    rows = [(i["name"], f"{i['order_qty']:,.0f}", _rm(i["line_cost"]), "yes" if i["runs_out_before_delivery"] else "")
            for i in items]
    return (f"**Order {len(items)} products this week, about {_rm(d['order_total'])} in total** "
            f"(budget {_rm(d['available_budget'])}).\n\n" + _table(["Product", "Order", "Cost", "Runs out first?"], rows)
            + f"\n\n{len(urgent)} of them may run out before the next delivery. Quantities come from LARIS's optimiser "
              "within your budget.\n\n**Next:** check the list in LARIS › R · Recommend, then send it from Orders.")


def _budget(ctx, memory):
    d = T.get_budget_status(ctx)
    left = d["remaining_after_order"]
    cut = d["products_reduced_or_left_out"]
    memory["last_products"] = [c["name"] for c in cut]
    text = (f"**Plan to spend about {_rm(d['order_total'])} of your {_rm(d['available_budget'])} budget.**\n\n"
            f"- Full recommended order (no cash limit): {_rm(d['full_recommended_order'])}\n"
            f"- {'Left after this order' if left >= 0 else 'Over budget by'}: {_rm(abs(left))}\n")
    if cut:
        text += f"- {len(cut)} product(s) get less than they need: " + ", ".join(c["name"] for c in cut) + "\n"
        add = d["extra_cash_scenario"]
        if add["would_add"]:
            text += (f"\nAn extra {_rm(add['extra_rm'])} would add " + ", ".join(f"{a['units']:,.0f} × {a['name']}"
                     for a in add["would_add"]) + f" (estimated {_rm(add['estimated_loss_avoided_rm'])} of lost "
                     "profit and waste avoided).\n")
    return text + "\n**Next:** change the budget in the top bar, or see the trade-offs in LARIS › R · Recommend."


def _best(ctx, memory):
    d = T.get_sales_summary(ctx, 7)
    top = d["best_sellers_by_revenue"]
    memory["last_products"] = [t["name"] for t in top]
    if not top:
        return "I don't have recorded sales for last week."
    rows = [(t["name"], _rm(t["revenue_rm"]), f"{t['units']:,.0f}") for t in top]
    return (f"**Your best seller last week was {top[0]['name']}** ({d['period'][0]} to {d['period'][1]}).\n\n"
            + _table(["Product", "Revenue", "Units"], rows) + "\n\nThese are recorded sales priced at your selling "
            "prices.\n\n**Next:** make sure the top sellers are in stock (LARIS › I · Inventory).")


def _profit(ctx, memory):
    d = T.get_profit_summary(ctx, 28)
    note = (f" {d['products_without_cost_price']} product(s) have no cost price, so they're left out."
            if d["products_without_cost_price"] else "")
    memory["last_products"] = [t["name"] for t in d["top_gross_profit"]]
    if d["gross_profit_rm"] is None:
        return "I can see your sales, but there isn't enough cost data to calculate gross profit." + note
    return (f"**Gross profit for the last 28 days ({d['period'][0]} to {d['period'][1]}) was "
            f"{_rm(d['gross_profit_rm'])}** on {_rm(d['revenue_rm'])} of sales, a {d['gross_margin_pct']:.1f}% "
            f"margin.\n\nTop contributors: " + ", ".join(f"{t['name']} ({_rm(t['gross_profit_rm'])})"
                                                          for t in d["top_gross_profit"][:3])
            + f".\n\nThis is gross profit (sales minus what the goods cost), not net profit: rent, wages and other "
              f"running costs aren't included.{note}\n\n**Next:** see LARIS › S · Sales for margins by product.")


def _runout(ctx, memory):
    d = T.get_stockout_risks(ctx)
    items = [i for i in d["items"] if i["level"] in ("URGENT", "WARNING")]
    memory["last_products"] = [i["name"] for i in items]
    extra = f"\n\nNo forecast for: {', '.join(d['no_forecast'])}, so I can't judge them." if d["no_forecast"] else ""
    if not items:
        return "No product is expected to run out before your next delivery." + extra
    rows = [(i["name"], i["level"].title(), _days_txt(i["stock_lasts_days"]), i["next_delivery_if_ordered_today"])
            for i in items]
    first = min(items, key=lambda i: i["stock_lasts_days"] if i["stock_lasts_days"] is not None else 1e9)
    return (f"**{first['name']} may run out first: its stock lasts about {_days_txt(first['stock_lasts_days'])}.**\n\n"
            + _table(["Product", "Urgency", "Stock lasts", "Delivery if ordered today"], rows)
            + "\n\nRanked by whether stock runs out before an order placed today can arrive, then must-haves and "
              "margin at risk. Days are estimates from the forecast." + extra
            + "\n\n**Next:** see LARIS › R · Recommend for what to order or top up.")


def _excess(ctx, memory):
    d = T.get_excess_stock(ctx)
    memory["last_products"] = [i["name"] for i in d["items"]]
    if not d["items"]:
        return "No product looks overstocked or at risk of expiring."
    rows = [(i["name"], i["type"], f"{i['estimated_unsold']:,.0f}", _rm(i["estimated_cost_tied_up_rm"]))
            for i in d["items"]]
    return ("**These products have more stock than they're likely to sell in time.**\n\n"
            + _table(["Product", "Type", "Est. unsold", "Cost tied up"], rows)
            + "\n\nEstimates assume the stock on hand is fresh (expiry dates aren't recorded).\n\n"
              "**Next:** skip or cut their next order in LARIS › R · Recommend.")


def _inventory(ctx, memory):
    d = T.get_inventory_status(ctx)
    low = [i for i in d["items"] if i["status"] in ("Out of stock", "Low")]
    memory["last_products"] = [i["name"] for i in low]
    rows = [(i["name"], i["status"], f"{i['stock']:,.0f}", _days_txt(i["stock_lasts_days"])) for i in low]
    head = f"**{len(low)} product(s) are low or out of stock.**" if low else "**No product is low or out of stock.**"
    return (head + ("\n\n" + _table(["Product", "Status", "Stock", "Lasts"], rows) if rows else "")
            + f"\n\nStock value at cost: {_rm(d['stock_value_at_cost_rm'])}"
            + (f" ({d['products_without_cost_price']} product(s) have no cost price)." if d["products_without_cost_price"]
               else ".") + "\n\n**Next:** see LARIS › I · Inventory.")


def _summary(ctx, memory):
    s = T.get_business_summary(ctx)
    b, sa, pr = s["budget"], s["sales"], s["profit"]
    memory["last_products"] = s["restock"]["running_out"]
    change = f" ({sa['change_pct']:+.1f}% vs the week before)" if sa["change_pct"] is not None else ""
    return (f"**This week: order about {_rm(b['order_rm'])} of your {_rm(b['available_rm'])} budget.**\n\n"
            f"- May run out first: {', '.join(s['restock']['running_out']) or 'none'}\n"
            f"- Sales last 7 days: {_rm(sa['last_7_days_rm'])}{change}\n"
            f"- Gross profit last 7 days: {_rm(pr['gross_profit_7d_rm'])}\n"
            f"- Overstocked: {', '.join(s['inventory']['excess']) or 'none'}\n\n**Next:** review LARIS › R · Recommend.")


def _product(ctx, memory, p):
    d = T.get_product_details(ctx, p)
    memory["last_products"] = [d["name"]]
    return (f"**{d['name']}: {d['recommendation'][0].lower() + d['recommendation'][1:]}.**\n\n"
            f"- Stock: {d['stock']:,.0f} (lasts {_days_txt(d['stock_lasts_days'])})\n"
            f"- Forecast next 7 days: {d['forecast_next_7_days']} ({d['forecast_source']})\n"
            f"- Sold last 7 days: {d['sold_last_7_days']:,.0f}\n\nWhy: {d['why']} {d['risk']}"
            + (f" {d['estimated_impact']} (estimate)." if d["estimated_impact"] else "")
            + "\n\n**Next:** open it in LARIS › L · Look Up for the full forecast.")


def _most_urgent(ctx, memory):
    names = memory.get("last_products") or []
    plan = ctx["plan"].assign(plain=ctx["plan"]["name"].map(T.plain))
    pick = plan[plan["plain"].isin([T.plain(n) for n in names])] if names else plan
    if pick.empty:
        return "Which products do you mean? Ask me what to restock or what may run out first."
    pick = pick.assign(_u=~pick["urgent"]).sort_values(["_u", "cover_days"])
    r = pick.iloc[0]
    when = f"its stock lasts about {r['cover_days']:.1f} days" if r["cover_days"] < 1e9 else "it has no expected sales"
    return (f"**{r['plain']} is the most urgent{' of those' if names else ''}**: {when}"
            + (", which may not last until the next delivery." if r["urgent"] else ".")
            + f"\n\nLARIS suggests ordering {r['order_qty']:,.0f}. {r['why']}")


INTENTS = [  # (keywords, handler); first match wins, checked in this order
    (("most urgent", "which of those", "which of them", "which one", "first of"), _most_urgent),
    (("run out", "running out", "stockout", "stock out", "at risk"), _runout),
    (("spend", "budget", "afford"), _budget),
    (("restock", "reorder", "what should i order", "what to order", "what should i buy"), _restock),
    (("best", "top seller", "selling", "popular"), _best),
    (("profit", "margin", "make this month", "earn"), _profit),
    (("expire", "excess", "overstock", "waste", "too much stock"), _excess),
    (("low stock", "inventory", "stock level", "out of stock", "how much stock"), _inventory),
    (("summary", "overview", "how is my shop", "how's my shop", "how are we doing"), _summary),
]
HELP = ("I can answer questions like: what should I restock, how much should I spend, what may run out first, which "
        "products sell best, how much profit I made, what is overstocked, or why a product is recommended "
        "(name the product).")


def fallback(question, ctx, memory):
    """Deterministic answers from the same tools; also turns 'set <product> to <n>' into a confirmable proposal."""
    q = question.lower()
    p, cands = T.find_product(ctx, question)
    m = re.search(r"\b(?:set|change|make|order)\b.*?\b(\d+)\b", q)
    if m and p:
        prop = T.propose_order_change(ctx, p, int(m.group(1)))
        if prop.get("status") == "needs_confirmation":
            text = (f"I can change this week's order for **{prop['name']}** from {prop['current_order_qty']:,.0f} to "
                    f"**{prop['proposed_qty']:,} units** ({_rm(prop['proposed_line_cost_rm'])}). Nothing has changed "
                    "yet: press **Confirm** below to apply it.")
            return {"text": text, "source": "fallback", "tools": ["propose_order_change"], "proposal": prop}
    if p and ("why" in q or not any(any(k in q for k in keys) for keys, _ in INTENTS)):
        return {"text": _product(ctx, memory, p), "source": "fallback", "tools": ["get_product_details"],
                "proposal": None}
    for keys, fn in INTENTS:
        if any(k in q for k in keys):
            return {"text": fn(ctx, memory), "source": "fallback", "tools": [fn.__name__.strip("_")], "proposal": None}
    if cands:
        return {"text": "Which one do you mean: " + ", ".join(T.plain(c) for c in cands) + "?", "source": "fallback",
                "tools": [], "proposal": None}
    return {"text": HELP, "source": "fallback", "tools": [], "proposal": None}


def check_connection(cfg, transport=None):
    """One tiny request (no shop data) to confirm the AI settings work. Returns (ok, message)."""
    if not cfg.get("enabled"):
        return False, "Not configured: set AI_API_KEY and AI_MODEL."
    try:
        data = (transport or http_transport)(cfg, {"model": cfg["model"], "max_tokens": 5, "messages": [
            {"role": "user", "content": "Reply with the word OK."}]})
        data["choices"][0]["message"]
        return True, f"Connected to {cfg['model']}."
    except ProviderError as e:
        return False, f"Not working: {e}."
    except (KeyError, IndexError, TypeError):
        return False, "Not working: the AI service sent an unexpected reply."
