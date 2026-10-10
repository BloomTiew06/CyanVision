"""Home ("Today"): the one number that matters, this week's order at a glance, and the few decisions that need the
owner today, each doable in one click (the same actions as the A, R, I and S tools). No full product lists here:
they live in the LARIS tools and Products."""
from html import escape

import numpy as np
import pandas as pd
import streamlit as st

import assistant
import assistant_tools as T
import laris_fx as fx
import laris_ui as ui
import planning
import store
from workspace import alerts as A
from workspace import waste as R

ss = st.session_state
ctx = ss["ctx"]
ui.require_plan(ctx)
as_of, ref = ctx["week"]["as_of"], ctx["ref"]
anim = ui.first_view("page:home")
att = planning.attention(ctx)
saved_al, saved_wa = store.get("alerts", {}), store.get("waste", {})
done = lambda saved, p, states: saved.get(f"{ref}|{p}", {}).get("status") in states

# ---------------- A. greeting: the one number that matters ----------------
who = ss["owner"] if ss.get("title") in (None, "", "(none)") else f"{ss['title']} {ss['owner']}"
greet = "Hi"
week = "Today"
n = att["total"]
if n:
    phrase = f"{n} product{'s' if n != 1 else ''} need{'s' if n == 1 else ''} you this week"
    st.markdown(ui.page_header(week, f"Hi, {who}. {phrase}.", "Here's your shop at a glance.", mark=phrase),
                unsafe_allow_html=True)
else:
    st.markdown(ui.page_header(week, f"Hi, {who}. You're on track this week.", "Here's your shop at a glance.",
                               mark="on track"), unsafe_allow_html=True)

# ---------------- B. this week's order (every figure from planning.business_summary) ----------------
s = planning.business_summary(ctx)
b, rs, sa, pr, inv, iss = s["budget"], s["restock"], s["sales"], s["profit"], s["inventory"], s["issues"]
scale = max(b["available_rm"], b["order_rm"], 1)
left = b["remaining_rm"]
chg = sa["change_pct"]
gp_ok = sa["last_7_days_rm"] > 0 and np.isfinite(pr["gross_profit_7d_rm"]) and pr["products_without_cost"] < len(
    ctx["plan"])
low_n = len(inv["low_stock"]) + len(inv["out_of_stock"])
lead = f"{b['products_in_order']} products in the order · {len(att['urgent'])} may run out before the next delivery"
legend = ((f"{ui.money(left)} left" if left >= -0.5 else f"Over budget by {ui.money(-left)}")
          + (f" · the full recommended order is {ui.money(b['full_order_rm'])}" if b["budget_limited"] else ""))
stats = [("Run out soon", ("html", ui.count(len(att["urgent"]), "h_urgent") + " " + ui.plural(len(att["urgent"]), "product")),
          "before the next delivery", "risk" if att["urgent"] else None),
         ("May go to waste", ("html", ui.count(len(att["waste"]), "h_waste") + " " + ui.plural(len(att["waste"]), "product")),
          "expiry or excess stock", None),
         ("Sales, last 7 days", ui.money(sa["last_7_days_rm"]),
          f"{chg:+.1f}% vs week before" if chg is not None and np.isfinite(chg) else "no earlier week", None),
         ("Gross profit, 7 days", ui.money(pr["gross_profit_7d_rm"]) if gp_ok else "–",
          f"{pr['margin_pct_7d']:.1f}% margin" if gp_ok else "needs cost prices", "lime" if gp_ok else None),
         ("Stock at cost", ui.money(inv["stock_value_rm"]), f"{low_n} low · {len(inv['excess'])} excess", None)]
note = f"of your {ui.money(b['available_rm'])} budget (cash or credit)"
if fx.enabled():
    with st.container(key="hero_box"):
        l, r = st.columns([1.7, 1])
        l.markdown('<div class="lr-hero lr-hero-flat"><div class="eyebrow">THIS WEEK&#39;S ORDER</div>'
                   f'<div class="lead">{escape(lead)}</div></div>', unsafe_allow_html=True)
        with r:
            fx.number(ui.money(b["order_rm"]), "home_order", label=f"This week's order: {ui.money(b['order_rm'])}",
                      size="40px", color="#F7F5EE", align="flex-end")
            st.markdown(f'<div class="lr-hero lr-hero-flat"><span class="note">{escape(note)}'
                        f'{ui.delta_chip("home_order", b["order_rm"])}</span></div>', unsafe_allow_html=True)
        fx.meter([(b["order_rm"] / scale, "#C7ED72")], "home_meter", marker=b["available_rm"] / scale, height=12,
                 track="#10382B", marker_color="#F7F5EE", label=f"Order {ui.money(b['order_rm'])} of a "
                                                                  f"{ui.money(b['available_rm'])} budget")
        st.markdown(f'<div class="lr-hero lr-hero-flat"><div class="legend">{escape(legend)}</div>'
                    f'<div class="stats">{ui.hero_stats(stats)}</div></div>', unsafe_allow_html=True)
else:
    st.markdown(ui.hero(eyebrow="THIS WEEK'S ORDER", lead=lead, big=ui.money(b["order_rm"]), big_note=note,
                        extra=ui.delta_chip("home_order", b["order_rm"]), fill=b["order_rm"] / scale,
                        marker=b["available_rm"] / scale, anim=anim, legend=legend, stats=stats),
                unsafe_allow_html=True)
al = planning.alert_table(ctx).set_index("product") if att["urgent"] else None
wa = planning.waste_table(ctx).set_index("product") if att["waste"] else None
plan_ix = ctx["plan"].set_index("product")

# ---------------- 1 · LARIS predicts ----------------
ui.stage(1, "LARIS predicts", "the next 7 days, from the AI forecast and its measured error")
focus = next((p for p in att["urgent"] if plan_ix.at[p, "must_have"]), None) or (att["urgent"] or [None])[0]
if focus is None:
    rising = ctx["plan"][ctx["plan"]["trend"] == "Growing"]
    focus = rising["product"].iloc[0] if len(rising) else ctx["plan"]["product"].iloc[0]
left, right = st.columns([1.35, 1], gap="medium")
with left.container(border=True, key="card_home_forecast"):
    fname = ui.split_name(plan_ix.at[focus, "name"])[1]
    rng = ui.forecast_range(ctx, focus)
    a, b = st.columns([1.6, 1], vertical_alignment="center")
    a.markdown(f'{ui.prediction_badge()}<span class="lr-name">{escape(fname)}</span><br>'
               f'<span class="lr-range">{escape(rng or "–")}<small>units expected next 7 days</small></span>',
               unsafe_allow_html=True)
    reveal = b.toggle("Backtest: compare with actual sales", key="home_reveal",
                      help="For a past week the actual sales are known: see how close the forecast was.")
    chart, note = ui.forecast_chart(ctx, focus, height=230, reveal=reveal)
    st.altair_chart(chart, width="stretch")
    if reveal:
        st.markdown(ui.reveal_note(ctx, focus), unsafe_allow_html=True)
    else:
        st.caption(note)
with right.container(border=True, key="card_home_problems"):
    st.markdown(f'{ui.prediction_badge("PREDICTED PROBLEMS")}<span class="lr-muted">this week</span>',
                unsafe_allow_html=True)
    rows_html = []
    for p in att["urgent"][:4]:
        r = al.loc[p]
        when = f"Runs out ~{r['runout']:%a %d %b}" if r["runout"] is not None and not pd.isna(r["runout"]) else "Runs low"
        rows_html.append(f'<div class="lr-predrow"><div class="what"><b>{escape(ui.split_name(r["name"])[1])}</b><br>'
                         f'<span class="when">{escape(when)} · delivery {r["delivery"]:%a %d %b}</span></div>'
                         f'{ui.product_spark(ctx, p, 120, 34)}</div>')
    for p in att["waste"][:2]:
        r = wa.loc[p]
        rows_html.append(f'<div class="lr-predrow"><div class="what"><b>{escape(ui.split_name(r["name"])[1])}</b><br>'
                         f'<span class="when waste">~{r["unsold"]:,.0f} may go unsold · {ui.money(r["tied_rm"])}</span></div>'
                         f'{ui.product_spark(ctx, p, 120, 34)}</div>')
    if rows_html:
        st.markdown("".join(rows_html), unsafe_allow_html=True)
    else:
        st.markdown(ui.empty("✓", "No stockouts or waste predicted this week"), unsafe_allow_html=True)
    ui.tool_button("A", "See every prediction", key="home_to_a")

# ---------------- 2 · LARIS decides ----------------
ui.stage(2, "LARIS decides", f"the best order for your {ui.money(ctx['budget_rm'])} budget, must-haves first")
left, right = st.columns([1.35, 1], gap="medium")
with left.container(border=True, key="card_home_alloc"):
    st.markdown(f'{ui.decision_badge("HOW THE BUDGET IS SPENT")}<span class="lr-muted">funded vs cut, per product'
                "</span>", unsafe_allow_html=True)
    chart = ui.allocation_chart(ctx)
    if chart is None:
        st.markdown(ui.empty("✓", "Nothing to order this week"), unsafe_allow_html=True)
    else:
        st.altair_chart(chart, width="stretch")
        st.caption("Must-haves are funded first, up to their expected sales; then each ringgit goes where it protects the "
                   "most profit.")
with right.container(border=True, key="card_home_decisions"):
    st.markdown(f'{ui.decision_badge()}<span class="lr-muted">one click each</span>', unsafe_allow_html=True)
    shown = 0
    for p in [p for p in att["urgent"] if not done(saved_al, p, ("Resolved", "Snoozed"))][:3]:
        r = al.loc[p]
        rr = r.copy()
        rr["product"] = p
        name = ui.split_name(r["name"])[1]
        status = saved_al.get(f"{ref}|{p}", {}).get("status", "New")
        row = pd.Series(rr).to_frame().T.itertuples().__next__()
        with st.container(key=f"decide_al_{ui.safe_key(p)}"):
            st.markdown(f'<span class="lr-name">{escape(name)}</span><br><span class="lr-muted">Short by about '
                        f'{r["bridge_qty"]:,.0f} before the delivery · {ui.money(r["rm_at_risk"])} margin at risk</span>',
                        unsafe_allow_html=True)
            st.button(A._primary_label(row, status), key=f"home_al_{p}", type="primary", width="stretch",
                      on_click=A._primary, args=(ref, row, name, status))
        shown += 1
    for p in [p for p in att["waste"] if not done(saved_wa, p, ("Dismissed", "Snoozed", "Applied to order"))][:2]:
        r = wa.loc[p]
        name = ui.split_name(r["name"])[1]
        qty = {"cut": r["recommended_qty"], "skip": 0.0, "keep": r["usual"]}.get(r["choice"])
        with st.container(key=f"decide_wa_{ui.safe_key(p)}"):
            st.markdown(f'<span class="lr-name">{escape(name)}</span><br><span class="lr-muted">About {r["unsold"]:,.0f} '
                        f'may go unsold (≈ {ui.money(r["tied_rm"])} at cost)</span>', unsafe_allow_html=True)
            if qty is not None and qty != r["order_qty"]:
                st.button("Skip the reorder" if r["choice"] == "skip" else f"Order {qty:,.0f} instead",
                          key=f"home_wa_{p}", width="stretch", on_click=R._apply,
                          args=(ref, p, name, qty, r["choice"]))
            else:
                ui.tool_button("R", "Review in R · Waste", key=f"home_wa_{p}")
        shown += 1
    if ctx["budget_limited"]:
        with st.container(key="decide_budget"):
            cut = planning.budget_breakdown(ctx)["cut"]
            st.markdown(f'<span class="lr-name">Budget trade-off</span><br><span class="lr-muted">Covers '
                        f'{ui.money(ctx["totals"]["spent_rm"])} of the {ui.money(ctx["ideal_rm"])} LARIS would order; '
                        f'{len(cut)} product(s) get less.</span>', unsafe_allow_html=True)
            ui.tool_button("I", "See the trade-offs", key="home_i")
        shown += 1
    if not shown:
        st.markdown(ui.empty("✓", "No decisions waiting", "Your stock and order look on track."), unsafe_allow_html=True)
proof = planning.proof_summary(ctx["metrics"])
t75 = (proof["replay"]["totals"] or {}).get("75%", {})
laris, usual = t75.get("LARIS (AI forecast + optimiser)"), {k: v for k, v in t75.items() if k.startswith("Usual")}
if laris and usual:
    best = min(usual.values(), key=lambda v: v["lost_margin_plus_waste_rm"])["lost_margin_plus_waste_rm"]
    gain = 1 - laris["lost_margin_plus_waste_rm"] / best if best > 0 else 0
    x, y = st.columns([5, 1.3], vertical_alignment="center")
    x.markdown(ui.label("BACKTEST", "simulated") + f'<span class="lr-muted">Tested on past weeks at 75% of the cash '
               f"needed, deciding this way lost <b>{abs(gain):.0%} {'less' if gain >= 0 else 'more'}</b> profit and stock "
               "to waste than the best usual way of ordering.</span>", unsafe_allow_html=True)
    y.page_link("views/proof.py", label="See the proof", icon=":material/verified:")

# ---------------- 3 · You act ----------------
ui.stage(3, "You act", "check the order and send it to your supplier yourself")
status = store.get("orders", {}).get(ref, {}).get("status", "Draft")
order = ctx["plan"][ctx["plan"]["order_qty"] > 0]
left, right = st.columns([1.35, 1], gap="medium")
with left:
    if order.empty:
        st.markdown(ui.empty("🧾", "Nothing to order this week"), unsafe_allow_html=True)
    else:
        st.markdown(ui.whatsapp_preview(planning.order_message(ctx["plan"], ctx["shop"], as_of, ref),
                                        ss.get("supplier_name") or "Your supplier", ss.get("supplier_phone")),
                    unsafe_allow_html=True)
with right.container(border=True, key="card_home_send"):
    st.markdown(f'<span class="lr-name">Order {escape(ref)}</span><br><span class="lr-muted">{len(order)} items · '
                f'{ui.money(ctx["order_rm"])} · status: {escape(status.lower())} (your record)</span>',
                unsafe_allow_html=True)
    st.link_button("Open WhatsApp draft", planning.whatsapp_url(planning.order_message(ctx["plan"], ctx["shop"], as_of,
                                                                                      ref), ss.get("supplier_phone")),
                   type="primary", icon=":material/send:", width="stretch", disabled=order.empty)
    ui.tool_button("S", "Review, track and record delivery", key="home_s")
    st.caption("WhatsApp opens with the message filled in; you check it and press send.")

# ---------------- D. the assistant ----------------
try:
    secrets = dict(st.secrets)
except Exception:
    secrets = {}
cfg = assistant.config(secrets)
chat = ss.setdefault("chat", [])
memory = ss.setdefault("chat_mem", {})
SOURCE = {"ai": "AI answer · numbers from LARIS's calculations",
          "fallback": "Quick answer from LARIS's own calculations (AI assistant not set up; see Settings › Assistant)",
          "error": "AI unavailable · quick answer from LARIS's own calculations", "app": "LARIS"}
SUGGESTIONS = ["What should I restock this week?", "How much should I spend on replenishment?",
               "Which products are selling best?", "How much profit did I make this month?",
               "Which products are at risk of running out?", "Which of those is the most urgent?"]

# verify an action the owner confirmed on the previous run, against the rebuilt plan
v = ss.pop("chat_verify", None)
if v:
    pid, qty, name = v
    plan = ctx["plan"].set_index("product")
    if pid in plan.index and plan.at[pid, "order_qty"] == qty:
        chat.append({"role": "assistant", "source": "app", "content":
                     f"Done: this week's order for **{name}** is now **{qty:,} units** "
                     f"({ui.money(plan.at[pid, 'order_rm'])}). You can change it back in LARIS › I · Invest."})
    else:
        chat.append({"role": "assistant", "source": "app",
                     "content": f"Sorry, the change for {name} didn't apply. Nothing in your order was changed."})


def _confirm(i):
    m = chat[i]
    p = m["proposal"]
    m["pending"] = False
    plan = ss["ctx"]["plan"]
    qty = p.get("proposed_qty")
    if p.get("product_id") not in set(plan["product"]) or not isinstance(qty, int) or not 0 <= qty <= T.MAX_QTY:
        chat.append({"role": "assistant", "source": "app", "content": "That change isn't valid any more, so nothing "
                                                                      "was changed."})
        return
    ui.set_qty_value(p["product_id"], qty)
    ss["chat_verify"] = (p["product_id"], qty, p["name"])


def _cancel(i):
    chat[i]["pending"] = False
    chat.append({"role": "assistant", "source": "app", "content": "Cancelled. Nothing was changed."})


def _ask(q):
    ss["chat_q"] = q


st.write("")
with st.expander("Ask LARIS, the assistant", icon=":material/forum:", expanded=bool(chat)), \
        st.container(key="chatcard"):
    a, c = st.columns([5, 1.2], vertical_alignment="center")
    a.markdown('<span class="lr-muted">'
               + ("AI assistant on. " if cfg["enabled"] else "Quick answers (AI assistant not set up). ")
               + "Answers use your shop's numbers; LARIS never sends orders or changes stock by itself.</span>",
               unsafe_allow_html=True)
    if chat:
        c.button("Clear chat", key="chat_clear", width="stretch",
                 on_click=lambda: (ss.update(chat=[], chat_mem={})))
    log = st.container(height=430, border=False)
    with log:
        if not chat:
            with st.chat_message("assistant", avatar=":material/storefront:"):
                st.markdown(f"{greet}, {who}. What would you like to know about your shop today?")
        for i, m in enumerate(chat):
            with st.chat_message(m["role"], avatar=":material/storefront:" if m["role"] == "assistant"
                                 else ":material/person:"):
                st.markdown(m["content"])
                if m["role"] == "assistant":
                    st.caption(SOURCE.get(m.get("source"), ""))
                    if m.get("proposal") and m.get("pending"):
                        x, y, _ = st.columns([1, 1, 3])
                        x.button("Confirm", key=f"chat_ok_{i}", type="primary", on_click=_confirm, args=(i,))
                        y.button("Cancel", key=f"chat_no_{i}", on_click=_cancel, args=(i,))
    cols = st.columns(3)
    for i, q in enumerate(SUGGESTIONS):
        with cols[i % 3]:
            st.button(q, key=f"sugg_{i}", on_click=_ask, args=(q,), width="stretch")
    typed = st.chat_input("Ask about stock, sales, profit or this week's order…", key="chat_in")

question = typed or ss.pop("chat_q", None)
if question:
    chat.append({"role": "user", "content": question})
    with log:   # show the question and a placeholder while LARIS works out the answer
        with st.chat_message("user", avatar=":material/person:"):
            st.markdown(question)
        with st.chat_message("assistant", avatar=":material/storefront:"):
            st.markdown(ui.skeleton() + '<span class="lr-muted">Checking your shop\'s numbers…</span>',
                        unsafe_allow_html=True)
    r = assistant.ask(question, chat[:-1], ctx, cfg, memory)
    chat.append({"role": "assistant", "content": r["text"], "source": r["source"], "tools": r["tools"],
                 "proposal": r["proposal"], "pending": bool(r["proposal"])})
    st.rerun()
