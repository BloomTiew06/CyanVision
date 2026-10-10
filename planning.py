"""LARIS 2.0 page logic: pure functions that turn the shared planning context (laris_core.build_context) into
what each page shows. No Streamlit imports and no new forecasting or optimisation: every number is derived from
the context's rows (risk), plan (actions and quantities) and week (forecast and history), so pages can't
contradict each other.
"""
from math import ceil
from urllib.parse import quote

import numpy as np
import pandas as pd
from scipy.stats import norm

ACTION_LABEL = {"RESTOCK": "Buy more", "REDUCE": "Buy less", "STOP": "Skip this order", "MAINTAIN": "As usual"}
ACTION_HELP = {
    "RESTOCK": "These products may run low before your next delivery or need a larger order than usual.",
    "REDUCE": "These products may need a smaller order than usual.",
    "STOP": "Existing stock may be enough, or some products may expire before they sell.",
    "MAINTAIN": "These products do not currently need a significant change.",
}
LEVEL_RANK = {"URGENT": 0, "WARNING": 1, "MONITOR": 2}


def order_ref(store, as_of):
    return f"KM-{store}-{pd.Timestamp(as_of):%Y%m%d}"


def round_pack(q, pack):
    pack = max(1, int(pack))
    return float(max(0, round(q / pack)) * pack)


# ---------------- order message (Send & Sync, Home) ----------------
def order_message(plan, shop, as_of, ref):
    order = plan[plan["order_qty"] > 0]
    lines = [f"Order {ref} from {shop}, week of {pd.Timestamp(as_of):%d %b %Y}:"]
    lines += [f"- {q:,.0f} x {n}" for n, q in zip(order["name"], order["order_qty"])]
    lines.append(f"Estimated total: RM {order['order_rm'].sum():,.2f}")
    lines.append("Please confirm availability and delivery date. Thank you.")
    return "\n".join(lines)


def whatsapp_url(message, phone=""):
    """wa.me link with the message pre-filled; WhatsApp opens it as a draft the owner must send."""
    digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
    return f"https://wa.me/{digits}?text={quote(message, safe='')}"


# ---------------- Home: insights recap ----------------
def insights(ctx):
    """Plain-language findings, most urgent first. Each is (level, text, LARIS tool letter). Data-supported only."""
    plan, rows = ctx["plan"], ctx["rows"].set_index("product")
    out = []
    urgent = plan[plan["urgent"]]
    must_u, other_u = urgent[urgent["must_have"]], urgent[~urgent["must_have"]]
    if len(must_u):
        out.append(("URGENT", f"{len(must_u)} must-have product(s) may run out before your next delivery: "
                              f"{', '.join(must_u['name'])}.", "A"))
    if len(other_u):
        out.append(("URGENT", f"{len(other_u)} other product(s) may run out before your next delivery.",
                    "A"))
    if ctx["order_rm"] > ctx["budget_rm"] + 0.5:
        out.append(("WARNING", f"Your order exceeds your budget by RM {ctx['order_rm'] - ctx['budget_rm']:,.0f}.",
                    "I"))
    elif ctx["budget_limited"]:
        short = plan[(plan["ideal"] > 0) & (plan["qty"] < plan["ideal"])]
        out.append(("WARNING", f"Your budget leaves RM {ctx['ideal_rm'] - ctx['totals']['spent_rm']:,.0f} of the "
                               f"recommended order unfilled; {len(short)} product(s) get less than they need.",
                    "I"))
    stop = plan[plan["action"] == "STOP"]
    if len(stop):
        rm = float(rows.loc[stop["product"], "expected_expire_rm"].sum())
        out.append(("WARNING", f"{len(stop)} product(s) have more stock than they're likely to sell in time"
                               + (f" (about RM {rm:,.0f} may expire)." if rm >= 1 else "."), "R"))
    rising = plan[plan["trend"] == "Growing"]
    if len(rising):
        out.append(("INFO", f"{len(rising)} product(s) are expected to sell noticeably more next week.",
                    "L"))
    return out


# ---------------- A: alerts ----------------
def alert_table(ctx):
    """Products that may run out, with an urgency level, run-out date range and a recommended option."""
    plan, rows, as_of = ctx["plan"], ctx["rows"].set_index("product"), ctx["week"]["as_of"]
    out = []
    for p in plan.itertuples():
        r = rows.loc[p.product]
        cover, lead, rev = p.cover_days, int(r["lead_time"]), int(r["review"])
        if p.urgent:
            level = "URGENT"
        elif p.action not in ("RESTOCK", "MAINTAIN"):   # the plan already says buy less / don't reorder
            continue
        elif cover < lead + rev:
            level = "WARNING"
        elif p.action == "RESTOCK" or cover < 7:
            level = "MONITOR"
        else:
            continue
        fc7, avail = r["demand_7d"], r["on_hand"] + r["on_order"]
        b = r["band_pct"] if np.isfinite(r["band_pct"]) else 0.5
        daily = fc7 / 7
        lo = avail / (daily * (1 + b)) if daily > 0 else np.inf
        hi = avail / (daily * max(0.2, 1 - b)) if daily > 0 else np.inf
        rm = float(r["rm_at_risk"])
        if level == "URGENT" and (p.must_have or rm >= 20):
            choice = "topup"
            why = ("A must-have product" if p.must_have else "A product with a lot of margin at stake") + \
                  " may run out before the scheduled delivery. A small emergency top-up may protect sales."
        elif level == "URGENT":
            choice = "next"
            why = "It may run short for a day or two, but it isn't a must-have and little margin is at stake, so a " \
                  "short gap may be acceptable. Make sure it's in this order."
        elif level == "WARNING":
            choice = "next"
            why = "Stock should last until the next delivery but not the one after, so include it in this order."
        else:
            choice = "none"
            why = "Stock looks sufficient for now; check it again before the next order."
        short = float(r["bridge_qty"]) if r["bridge_qty"] > 0 else float(ceil(max(0.0, r["expected_short"])))
        when = lambda d: as_of + pd.Timedelta(days=float(d)) if np.isfinite(d) else None
        out.append({"product": p.product, "name": p.name, "level": level, "must_have": p.must_have,
                    "stock": avail, "daily": daily, "cover": cover, "delivery": as_of + pd.Timedelta(days=lead),
                    "lead": lead, "runout": when(cover), "runout_lo": when(lo), "runout_hi": when(hi),
                    "rm_at_risk": rm, "bridge_qty": short, "unit_cost": float(r["unit_cost"]),
                    "order_qty": p.order_qty, "choice": choice, "why": why, "reason": p.risk})
    df = pd.DataFrame(out)
    if len(df):
        df["_l"] = df["level"].map(LEVEL_RANK)
        df = df.sort_values(["_l", "must_have", "rm_at_risk"], ascending=[True, False, False]) \
               .drop(columns="_l").reset_index(drop=True)
    return df


# ---------------- L: look ahead ----------------
RANKINGS = {"Biggest increase": ("change", False), "Most units": ("fc7", False),
            "Least certain": ("band", False), "Order soonest": ("deadline_days", True)}


def daily_forecast(ctx, product):
    """The same daily forecast the plan used: model pattern x the shop's scaling, or flat recent sales."""
    r = ctx["rows"].set_index("product").loc[product]
    if r["forecast_source"] == "model":
        return ctx["week"]["fc_wide"][product].to_numpy() * r["ratio"]
    return np.full(7, r["demand_last7"] / 7)


def look_ahead_table(ctx, rank_by="Biggest increase"):
    """Expected demand per product with stock-up options (full / part / skip the extra) where it applies."""
    plan, rows, as_of = ctx["plan"], ctx["rows"].set_index("product"), ctx["week"]["as_of"]
    out = []
    for p in plan.itertuples():
        r = rows.loc[p.product]
        daily = daily_forecast(ctx, p.product)
        peak = int(np.argmax(daily)) if daily.sum() > 0 else 0
        lead = int(r["lead_time"])
        band = float(r["band_pct"]) if np.isfinite(r["band_pct"]) else np.inf
        uncertain = bool(r["low_confidence"]) or band > 0.5
        deadline_days = peak - lead
        peak_txt = f"{(as_of + pd.Timedelta(days=peak)):%a %d %b}"
        if deadline_days < 0:
            deadline = (f"Order today: delivery takes {lead} day(s), so stock ordered later arrives after the "
                        f"busiest day ({peak_txt}).")
        else:
            deadline = (f"Order by {(as_of + pd.Timedelta(days=deadline_days)):%a %d %b} to have stock before the "
                        f"busiest day ({peak_txt}).")
        opts, rec, rec_why = {}, None, ""
        if p.ideal > p.usual:
            opts = {"full": p.ideal, "part": round_pack((p.ideal + p.usual) / 2, r["pack_size"]), "skip": p.usual}
            short_life = r["perishable"] and r["shelf_life"] <= 7
            reasons = ([f"the forecast is uncertain (range ±{band:.0%})" if np.isfinite(band) else
                        "the forecast is uncertain"] if uncertain else []) + \
                      ([f"it keeps only {r['shelf_life']} day(s)"] if short_life else []) + \
                      (["your budget doesn't cover the full amount"] if p.qty < p.ideal else [])
            if reasons:
                lead_in = ("Demand may increase" if p.trend == "Growing" else
                           "Your stock and usual order may not cover expected sales")
                rec, rec_why = "part", f"{lead_in}, but " + " and ".join(reasons) + "."
            else:
                rec, rec_why = "full", (("Demand is expected to rise" if p.trend == "Growing" else
                                         "Your stock and usual order may not cover expected sales")
                                        + ", the forecast is fairly steady and the stock keeps.")
        out.append({"product": p.product, "name": p.name, "fc7": r["demand_7d"], "last7": r["demand_last7"],
                    "change": p.change, "trend": p.trend, "cover": p.cover_days, "band": band,
                    "uncertain": uncertain, "delivery": as_of + pd.Timedelta(days=lead),
                    "deadline_days": deadline_days, "deadline": deadline, "action": p.action, "why": p.why,
                    "options": opts, "recommended": rec, "rec_why": rec_why, "order_qty": p.order_qty})
    df = pd.DataFrame(out)
    if len(df):
        col, asc = RANKINGS.get(rank_by, RANKINGS["Biggest increase"])
        df = df.sort_values(col, ascending=asc, na_position="last").reset_index(drop=True)
    return df


# ---------------- R: reduce waste ----------------
def waste_table(ctx):
    """Products where buying less (or nothing) avoids expiry or cash tied up, with options and a recommendation."""
    plan, rows = ctx["plan"], ctx["rows"].set_index("product")
    out = []
    for p in plan.itertuples():
        r = rows.loc[p.product]
        lead, rev, cost = int(r["lead_time"]), int(r["review"]), float(r["unit_cost"])
        avail, daily = r["on_hand"] + r["on_order"], r["demand_7d"] / 7
        slow = p.trend == "Declining" and p.cover_days > lead + rev
        if r["dead_flag"] and r["perishable"]:
            kind = "Expiry risk"
        elif r["dead_flag"]:
            kind = "Excess stock"
        elif p.action == "REDUCE":
            kind = "Needs less than usual"
        elif slow:
            kind = "Slow-moving"
        else:
            continue
        if r["perishable"] and r["dead_flag"]:
            unsold = float(r["expected_expire_units"])
        else:
            unsold = max(0.0, avail - daily * (lead + rev))
        if p.action == "STOP":
            choice = "skip"
            why = ("You already have more stock than is likely to sell before it expires. Buying more would add to "
                   "what may be thrown away." if r["perishable"] else
                   "You already have enough stock to cover expected demand for weeks. Buying more ties up cash.")
        elif p.action == "REDUCE":
            choice = "cut"
            why = p.why[0].upper() + p.why[1:]
        else:
            choice = "keep"
            why = "Sales are slowing, but the usual order still fits the stock you have. Watch it next week."
        out.append({"product": p.product, "name": p.name, "kind": kind, "stock": avail,
                    "sold7": r["demand_last7"], "sales_before_expiry": float(r["demand_shelf_life"]),
                    "unsold": unsold, "tied_rm": unsold * cost, "shelf_life": int(r["shelf_life"]),
                    "perishable": bool(r["perishable"]), "usual": p.usual, "recommended_qty": p.qty,
                    "order_qty": p.order_qty, "choice": choice, "why": why,
                    "front": bool(r["perishable"] and unsold >= 1)})
    df = pd.DataFrame(out)
    if len(df):
        df = df.sort_values("tied_rm", ascending=False).reset_index(drop=True)
    return df


# ---------------- I: invest within budget ----------------
def budget_breakdown(ctx):
    """Which products the budget covers fully, partly or not at all, with the optimiser's own reason."""
    plan, alloc = ctx["plan"], ctx["alloc"].set_index("product")
    need = plan[plan["ideal"] > 0]
    full = need[need["qty"] >= need["ideal"]]
    cut = need[need["qty"] < need["ideal"]]

    def why(p):
        stock = f"current stock covers {p.cover_days:.1f} days" if np.isfinite(p.cover_days) else "no sales expected"
        reason = alloc.at[p.product, "cut_reason"]
        base = "lower value per ringgit than the products kept" if reason.startswith("Budget") else reason.lower()
        if p.must_have and p.qty > 0:
            return f"Must-have: covered up to about its expected sales; the extra safety stock was cut first; {stock}."
        return f"{'Must-have, but ' if p.must_have else ''}{base}; {stock}."
    cut = cut.assign(reason=[why(p) for p in cut.itertuples()], status=np.where(cut["qty"] > 0, "Reduced", "Left out"))
    return {"full": full, "cut": cut}


STRATEGIES = {"essentials": "Protect essentials first", "value": "Best value per ringgit"}


def strategy_compare(ctx):
    """Both strategies the optimiser supports, at the current budget, scored on the same forecast (ESTIMATES):
    essentials = must-haves filled up to expected demand first, then value per RM; value = value per RM only
    (must-haves still carry their goodwill cost, but aren't filled first)."""
    from inventory import allocate_budget, score_allocation
    out = {}
    for key, protect in (("essentials", True), ("value", False)):
        alloc, tot = allocate_budget(ctx["items"], ctx["budget_rm"], protect_must_have=protect)
        s = score_allocation(ctx["items"], alloc["qty"].to_numpy())
        out[key] = {"spent": tot["spent_rm"], "loss": s["exp_lost_margin_rm"] + s["exp_waste_rm"],
                    "lost_margin": s["exp_lost_margin_rm"], "must_short": s["must_have_short_units"]}
    return out


# ---------------- S: reorder levels ----------------
def reorder_levels(ctx):
    """Reorder point = expected demand over the delivery time + safety stock (service-level z x daily error x
    sqrt(delivery days)); maximum = the order-up-to level the plan already uses (demand over delivery + review
    period, capped by shelf life, plus safety stock)."""
    rows = ctx["rows"]
    z = float(norm.ppf(ctx["service"]))
    rop = rows["demand_lead"] + z * rows["sigma"] * np.sqrt(rows["lead_time"].astype(float))
    pos = rows["on_hand"] + rows["on_order"]
    return pd.DataFrame({"product": rows["product"], "name": rows["name"], "stock": pos,
                         "reorder_point": np.ceil(rop), "max_level": np.ceil(rows["order_up_to"]),
                         "below": pos < rop})


# ---------------- Sales & profitability ----------------
PERIODS = {"Last 7 days": 7, "Last 28 days": 28, "Last 90 days": 90, "All available": None}


def sales_summary(ctx, days=28, offset=0):
    """Recorded sales per product over `days` days ending `offset` days before the planning week (days=None = all
    available), priced with the shop's selling price and cost. Gross profit = revenue - cost of goods sold (not net
    profit). Products without a model history only have their 'sold last 7 days' figure, so they count in the most
    recent 7-day period only."""
    week, rows = ctx["week"], ctx["rows"]
    as_of, scale, past = week["as_of"], ctx["scale"], week["past"]
    end = as_of - pd.Timedelta(days=offset)
    first = past["date"].min() if len(past) else end - pd.Timedelta(days=7)
    start = max(first, end - pd.Timedelta(days=days)) if days else first
    start = min(start, end)
    units_hist = past[(past["date"] >= start) & (past["date"] < end)].groupby("product")["y"].sum()
    out = []
    for r in rows.itertuples():
        price = r.unit_cost + r.margin
        if r.forecast_source == "model":
            units, has_hist = float(units_hist.get(r.product, 0.0)) * scale * r.ratio, True
        elif days == 7 and offset == 0:
            units, has_hist = float(r.demand_last7), True
        else:
            units, has_hist = np.nan, False
        revenue = units * price
        cost_known = r.unit_cost > 0
        cogs = units * r.unit_cost if cost_known else np.nan
        gp = revenue - cogs if cost_known else np.nan
        out.append({"product": r.product, "name": r.name, "units": units, "revenue": revenue, "cogs": cogs,
                    "gross_profit": gp,
                    "margin_pct": gp / revenue * 100 if cost_known and has_hist and revenue > 0 else np.nan,
                    "has_history": has_hist, "cost_known": cost_known})
    df = pd.DataFrame(out)
    known = df[df["cost_known"] & df["has_history"]]
    gp, known_rev = float(known["gross_profit"].sum()), float(known["revenue"].sum())
    totals = {"revenue": float(df["revenue"].sum(skipna=True)), "cogs": float(known["cogs"].sum()),
              "gross_profit": gp, "margin_pct": gp / known_rev * 100 if known_rev > 0 else np.nan,
              "start": start, "end": end - pd.Timedelta(days=1), "days": int((end - start).days),
              "no_history": int((~df["has_history"]).sum()), "no_cost": int((~df["cost_known"]).sum())}
    return df, totals


def profit_insights(ctx, summary):
    """Findings that link sales performance to stock decisions. Each is (title, text, product, tool letter or
    page path)."""
    plan, rows = ctx["plan"].set_index("product"), ctx["rows"].set_index("product")
    s = summary[summary["has_history"] & (summary["revenue"] > 0)].set_index("product")
    if s.empty:
        return []
    top_rev = set(s.nlargest(max(1, len(s) // 3), "revenue").index)
    m = s.dropna(subset=["margin_pct"])
    top_margin = set(m.nlargest(max(1, len(m) // 3), "margin_pct").index) if len(m) else set()
    out = []
    for p in s.index:
        pl, r = plan.loc[p], rows.loc[p]
        name, stock_rm = pl["name"], (r["on_hand"] + r["on_order"]) * r["unit_cost"]
        if p in top_rev and (pl["urgent"] or pl["action"] == "RESTOCK"):
            out.append(("High sales, low stock", f"{name} is one of your top sellers by revenue and may run short "
                                                 "before the next delivery.", p, "A"))
        elif p in top_margin and pl["cover_days"] < r["lead_time"]:
            out.append(("High margin, running low", f"{name} earns one of your best margins, but its stock may not "
                                                    "last until the delivery.", p, "A"))
        if pl["cover_days"] > 14 and stock_rm >= 50:
            out.append(("High stock, slow sales", f"About RM {stock_rm:,.0f} is tied up in {name}, which may take "
                                                  f"{pl['cover_days']:.0f} days to sell.", p, "R"))
        mp = s.at[p, "margin_pct"]
        if p in top_rev and pd.notna(mp) and mp < 15:
            out.append(("High sales, thin margin", f"{name} sells a lot but keeps only {mp:.0f}% as gross margin. "
                                                   "Check its cost and selling price.", p, "views/products.py"))
        if pl["trend"] == "Declining":
            out.append(("Sales expected to drop", f"{name} is expected to sell {abs(pl['change']):.0%} less next "
                                                  "week.", p, "L"))
    return out


# ---------------- My Products: table view ----------------
NUMERIC = ["Stock", "Sold last 7 days", "Cost price (RM)", "Selling price (RM)", "Delivery days", "Shelf life (days)"]


def to_view(inputs):
    return pd.DataFrame({
        "product": inputs["product"], "Product": inputs["Name"], "Stock": inputs["On hand"],
        "Sold last 7 days": inputs["Sales last 7 days"], "Cost price (RM)": inputs["Unit cost (RM)"],
        "Selling price (RM)": inputs["Unit cost (RM)"] + inputs["Margin (RM)"],
        "Delivery days": inputs["Lead time (days)"], "Shelf life (days)": inputs["Shelf life (days)"],
        "Must-have": inputs["Must-have"]})


def validate_products(edited, old, columns):
    """Editor table -> shop inputs. Returns (inputs or None, errors, warnings). Fully blank rows are ignored and
    reported; anything invalid is reported, never silently dropped or replaced."""
    old = old.set_index("product")
    errors, warnings, rows, seen, blank = [], [], [], set(), 0
    for i, e in enumerate(edited.to_dict("records"), start=1):
        name = str(e.get("Product")).strip() if pd.notna(e.get("Product")) else ""
        if not name and all(pd.isna(e.get(c)) for c in NUMERIC):
            blank += 1
            continue
        label = f"Row {i} ({name})" if name else f"Row {i}"
        if not name:
            errors.append(f"{label}: add a product name.")
            continue
        if name.lower() in seen:
            errors.append(f"{label}: '{name}' appears more than once. Use a unique name.")
            continue
        seen.add(name.lower())
        missing = [c for c in NUMERIC if pd.isna(e.get(c))]
        if missing:
            errors.append(f"{label}: fill in {', '.join(missing)}.")
            continue
        v = {c: float(e[c]) for c in NUMERIC}
        neg = [c for c in NUMERIC if v[c] < 0]
        if neg:
            errors.append(f"{label}: {', '.join(neg)} can't be negative.")
            continue
        if v["Delivery days"] < 1 or v["Shelf life (days)"] < 1:
            errors.append(f"{label}: delivery days and shelf life must be at least 1 day.")
            continue
        if v["Cost price (RM)"] == 0:
            warnings.append(f"{name}: no purchase price, so LARIS won't recommend ordering it until you add one.")
        elif v["Selling price (RM)"] < v["Cost price (RM)"]:
            warnings.append(f"{name}: selling price is below cost, so LARIS won't recommend ordering it.")
        key = e.get("product") if isinstance(e.get("product"), str) and e.get("product") else name
        o = old.loc[key] if key in old.index else None
        rows.append({
            "product": key, "Name": name,
            "Must-have": bool(e.get("Must-have")) if pd.notna(e.get("Must-have")) else False,
            "On hand": v["Stock"], "On order": float(o["On order"]) if o is not None else 0.0,
            "Sales last 7 days": v["Sold last 7 days"], "Unit cost (RM)": v["Cost price (RM)"],
            "Margin (RM)": v["Selling price (RM)"] - v["Cost price (RM)"],
            "Shelf life (days)": int(v["Shelf life (days)"]), "Lead time (days)": int(v["Delivery days"]),
            "Review (days)": int(o["Review (days)"]) if o is not None else 7,
            "Pack size": int(o["Pack size"]) if o is not None else 1,
        })
    if blank:
        warnings.append(f"{blank} empty row(s) were ignored.")
    if not rows and not errors:
        errors.append("Add at least one product with a name.")
    if errors:
        return None, errors, warnings
    return pd.DataFrame(rows, columns=columns), errors, warnings


# ---------------- forecasts, shared by Look Up, Recommend, Home and the assistant ----------------
SOURCE_LABEL = {"model": "AI model", "baseline": "Last week's sales (no model)", "unavailable": "Forecast unavailable"}


def forecast_text(value, source):
    """'26' for a forecast (including a real 0), 'Forecast unavailable' when there is none."""
    return "Forecast unavailable" if source == "unavailable" or pd.isna(value) else f"{value:,.0f}"


# ---------------- L: look up ----------------
def lookup_table(ctx, query=""):
    """One row per product: stock, sales, the canonical 7-day forecast (NaN only when unavailable), reorder levels
    and this week's order, all from the shared context."""
    plan, rows = ctx["plan"], ctx["rows"].set_index("product")
    lv = reorder_levels(ctx).set_index("product")
    out = []
    for p in plan.itertuples():
        r = rows.loc[p.product]
        out.append({"product": p.product, "name": p.name, "stock": r["on_hand"] + r["on_order"],
                    "sold7": r["demand_last7"], "forecast_7d": p.forecast_7d,
                    "forecast": forecast_text(p.forecast_7d, p.forecast_source),
                    "source": SOURCE_LABEL[p.forecast_source], "cover_days": p.cover_days,
                    "reorder_point": lv.at[p.product, "reorder_point"], "order_qty": p.order_qty,
                    "action": ACTION_LABEL[p.action], "must_have": p.must_have})
    df = pd.DataFrame(out)
    if query and len(df):
        df = df[df["name"].str.contains(query.strip(), case=False, regex=False)]
    return df.reset_index(drop=True)


# ---------------- I: inventory ----------------
STOCK_RANK = {"Out of stock": 0, "Low": 1, "Excess": 2, "OK": 3}


def inventory_table(ctx):
    """Stock status per product: Out of stock, Low (runs out before an order placed today arrives), Excess (more
    than it can sell in time), OK. Value at cost only where a cost price exists."""
    plan, rows = ctx["plan"].set_index("product"), ctx["rows"]
    lv = reorder_levels(ctx).set_index("product")
    out = []
    for r in rows.itertuples():
        pl = plan.loc[r.product]
        stock = r.on_hand + r.on_order
        if stock <= 0:
            status = "Out of stock"
        elif pl["urgent"] or pl["cover_days"] < r.lead_time:
            status = "Low"
        elif r.dead_flag:
            status = "Excess"
        else:
            status = "OK"
        out.append({"product": r.product, "name": r.name, "stock": stock, "daily": r.demand_7d / 7,
                    "cover_days": pl["cover_days"], "status": status, "lead_time": r.lead_time,
                    "value_rm": stock * r.unit_cost if r.unit_cost > 0 else np.nan,
                    "reorder_point": lv.at[r.product, "reorder_point"], "max_level": lv.at[r.product, "max_level"],
                    "forecast_source": r.forecast_source})
    df = pd.DataFrame(out)
    if len(df):
        df = df.assign(_r=df["status"].map(STOCK_RANK)).sort_values(["_r", "cover_days"]).drop(columns="_r")
    return df.reset_index(drop=True)


# ---------------- A / S: trends ----------------
def sales_compare(ctx, days=7):
    """Revenue for the last `days` vs the `days` before, over products with recorded history in both periods."""
    cur, ct = sales_summary(ctx, days)
    prev, pt = sales_summary(ctx, days, offset=days)
    both = cur["has_history"] & prev["has_history"] & (prev["revenue"] > 0) & (pt["days"] == days)
    now_rm, before_rm = float(cur.loc[both, "revenue"].sum()), float(prev.loc[both, "revenue"].sum())
    return {"days": days, "revenue_rm": now_rm, "previous_rm": before_rm if both.any() else np.nan,
            "change_pct": (now_rm / before_rm - 1) * 100 if before_rm > 0 else np.nan,
            "products_compared": int(both.sum()), "period": (ct["start"], ct["end"]),
            "previous_period": (pt["start"], pt["end"])}


def weekly_sales(ctx, weeks=8):
    """Revenue and gross profit for each of the last `weeks` full weeks before the planning week."""
    out = []
    for w in range(weeks):
        df, t = sales_summary(ctx, 7, offset=7 * w)
        if t["days"] < 7:
            break
        out.append({"week_start": t["start"], "revenue": t["revenue"], "gross_profit": t["gross_profit"]})
    return pd.DataFrame(out).sort_values("week_start").reset_index(drop=True) if out else pd.DataFrame()


# ---------------- one business summary: Home's panel and the assistant both read this ----------------
def _names(df, col="name", n=None):
    names = list(df[col])
    return names[:n] if n else names


def business_summary(ctx):
    plan, rows = ctx["plan"], ctx["rows"]
    inv = inventory_table(ctx)
    s7, t7 = sales_summary(ctx, 7)
    cmp = sales_compare(ctx, 7)
    urgent = plan[plan["urgent"]]
    restock = plan[plan["action"] == "RESTOCK"]
    known_cost = inv["value_rm"].notna()
    return {
        "week": {"start": str(ctx["week"]["as_of"].date()), "end": str(ctx["week"]["end"].date())},
        "budget": {"available_rm": ctx["budget_rm"], "order_rm": ctx["order_rm"],
                   "recommended_order_rm": ctx["totals"]["spent_rm"], "full_order_rm": ctx["ideal_rm"],
                   "remaining_rm": ctx["budget_rm"] - ctx["order_rm"], "budget_limited": ctx["budget_limited"],
                   "products_in_order": int((plan["order_qty"] > 0).sum())},
        "restock": {"buy_more": _names(restock), "running_out": _names(urgent),
                    "most_urgent": [{"name": r.name, "order_qty": r.order_qty, "stock_days": round(r.cover_days, 1),
                                     "reason": r.risk} for r in urgent.head(3).itertuples()]},
        "sales": {"last_7_days_rm": t7["revenue"], "period": [str(t7["start"].date()), str(t7["end"].date())],
                  "previous_7_days_rm": cmp["previous_rm"], "change_pct": cmp["change_pct"],
                  "products_compared": cmp["products_compared"]},
        "profit": {"gross_profit_7d_rm": t7["gross_profit"], "margin_pct_7d": t7["margin_pct"],
                   "products_without_cost": t7["no_cost"],
                   "note": "Gross profit = revenue - cost of goods; running costs are not included."},
        "inventory": {"out_of_stock": _names(inv[inv["status"] == "Out of stock"]),
                      "low_stock": _names(inv[inv["status"] == "Low"]), "excess": _names(inv[inv["status"] == "Excess"]),
                      "stock_value_rm": float(inv.loc[known_cost, "value_rm"].sum()),
                      "products_without_cost": int((~known_cost).sum())},
        "issues": {"forecast_unavailable": _names(plan[plan["forecast_source"] == "unavailable"]),
                   "baseline_forecast": _names(plan[plan["forecast_source"] == "baseline"]),
                   "unusual_recent_sales": _names(rows[rows["anomaly"]]),
                   "less_reliable_forecast": _names(rows[rows["low_confidence"]])},
    }


def product_trends(ctx, days=7):
    """Units and revenue per product for the last `days` vs the `days` before (products with history in both)."""
    cur, _ = sales_summary(ctx, days)
    prev, _ = sales_summary(ctx, days, offset=days)
    df = cur[["product", "name", "units", "revenue", "has_history"]].merge(
        prev[["product", "units", "revenue", "has_history"]], on="product", suffixes=("", "_prev"))
    df = df[df["has_history"] & df["has_history_prev"]].copy()
    df["change_pct"] = np.where(df["units_prev"] > 0, (df["units"] / df["units_prev"].where(df["units_prev"] > 0) - 1)
                                * 100, np.nan)
    return df.drop(columns=["has_history", "has_history_prev"]).reset_index(drop=True)


# ---------------- Proof: the evaluation the pipeline measured, as a few plain verdicts ----------------
MODEL_KEY = "Model (gradient boosting)"
GATE_TEXT = {
    "G1": "The AI forecast beats the best simple rule on 7-day error (95% confidence interval below zero)",
    "G2": "85–95% of actual 7-day sales fall inside the 90% forecast range",
    "G3": "Ordering with LARIS loses less (lost profit + waste) than every usual rule at 50% and 75% cash, in most stores",
    "G4": "G3 still holds under the sensitivity checks (margins, goodwill, shelf lives, late deliveries)",
}


def proof_summary(metrics):
    """Plain verdicts from metrics.json (written by pipeline.py on held-out weeks). Nothing is recomputed here;
    every figure is read from the file. Gates G1-G4 are the ones fixed in LARIS_OVERVIEW.md before any results."""
    m = metrics or {}
    out = {"source": m.get("data_source", "unknown"), "mock": "MOCK" in m.get("data_source", ""), "gates": {}}
    wk = m.get("test_weekly_totals") or {}
    out["accuracy"] = [{"method": k, "wape": v.get("WMAPE"), "mae": v.get("MAE"), "bias": v.get("bias"),
                        "model": k == MODEL_KEY} for k, v in wk.items()]
    ci = {k: v for k, v in (m.get("model_vs_baselines_7day_ci") or {}).items() if k != "label"}
    base = {k: v["WMAPE"] for k, v in wk.items() if k != MODEL_KEY and "WMAPE" in v}
    if base and ci:
        best = min(base, key=base.get)
        hi = (ci.get(best) or {}).get("ci95", [None, None])[1]
        out["best_rule"] = {"name": best, "wape": base[best], "diff": (ci.get(best) or {}).get("diff"),
                            "ci95": (ci.get(best) or {}).get("ci95")}
        out["gates"]["G1"] = "PASS" if hi is not None and hi < 0 else "FAIL"
        out["beats_rules"] = sum(1 for v in ci.values() if v.get("ci95", [0, 0])[1] < 0)
        out["n_rules"] = len(ci)
    else:
        out["gates"]["G1"] = "NOT RUN"
    cov = m.get("lead_time_interval_coverage") or {}
    c7 = (cov.get("conformal") or {}).get("L7_90")
    c7 = c7 if c7 is not None else m.get("band_coverage_90")
    out["coverage"] = {"L7_90": c7, "daily_90": m.get("band_coverage_90"),
                       "by_horizon": {L: (cov.get("conformal") or {}).get(f"L{L}_90") for L in (1, 3, 7)}}
    out["gates"]["G2"] = "NOT RUN" if c7 is None else "PASS" if 0.85 <= c7 <= 0.95 else "FAIL"
    out["unseen"] = m.get("unseen_stores")
    ab = m.get("alert_backtest") or {}
    out["alerts"] = {"rows": [{"method": k, **v} for k, v in (ab.get("test") or {}).items()],
                     "pr_auc": ab.get("test_pr_auc"), "reliability": ab.get("reliability") or [],
                     "label": ab.get("label", ""), "tau": ab.get("tau_act")}
    bs = m.get("budget_simulation") or {}
    tot = bs.get("totals_by_budget") or {}
    out["replay"] = {"totals": tot, "label": bs.get("label", ""), "stores": bs.get("stores", []),
                     "assumptions": bs.get("assumptions", [])}
    laris = "LARIS (AI forecast + optimiser)"
    if tot:
        wins = []
        for pct in ("50%", "75%"):
            t = tot.get(pct, {})
            usual = {k: v for k, v in t.items() if k.startswith("Usual")}
            rate = (bs.get("laris_win_rate_by_store") or {}).get(pct, {})
            wins.append(bool(usual) and laris in t and all(
                t[laris]["lost_margin_plus_waste_rm"] < v["lost_margin_plus_waste_rm"] and rate.get(k, 0) > 0.5
                for k, v in usual.items()))
        out["gates"]["G3"] = "PASS" if all(wins) else "FAIL"
        sens = bs.get("sensitivity_75pct") or {}
        out["sensitivity_failures"] = [k for k, v in sens.items() if not v.get("laris_lowest_vs_usual", True)]
        out["gates"]["G4"] = ("NOT RUN" if not sens else
                              "PASS" if bs.get("conclusion_holds_in_all_scenarios") else "FAIL")
    else:
        out["gates"]["G3"] = out["gates"]["G4"] = "NOT RUN"
        out["sensitivity_failures"] = []
    return out


def attention(ctx):
    """The products that need the owner this week, counted once, so Home and the LARIS tiles always agree:
    urgent = may run out before an order placed today arrives (A); waste = may expire unsold or is excess stock (R)."""
    al = alert_table(ctx)
    wa = waste_table(ctx)
    urgent = list(al.loc[al["level"] == "URGENT", "product"]) if len(al) else []
    waste = list(wa.loc[wa["kind"].isin(["Expiry risk", "Excess stock"]), "product"]) if len(wa) else []
    waste = [p for p in waste if p not in urgent]
    return {"urgent": urgent, "waste": waste, "total": len(urgent) + len(waste)}


def forecast_grid(ctx):
    """One row per product with the 7 daily forecasts (the same daily_forecast the plan used), the 7-day total, last
    week's sales and the change. Pure reshaping: no new forecasting."""
    as_of = ctx["week"]["as_of"]
    days = pd.date_range(as_of, periods=7)
    rows = ctx["rows"].set_index("product")
    out = []
    for p in ctx["plan"].itertuples():
        d = daily_forecast(ctx, p.product)
        out.append({"product": p.product, "name": p.name, **{f"{day:%a %d}": float(v) for day, v in zip(days, d)},
                    "total": float(np.sum(d)), "last7": float(rows.at[p.product, "demand_last7"]), "change": p.change,
                    "source": p.forecast_source, "must_have": bool(p.must_have)})
    return pd.DataFrame(out), [f"{day:%a %d}" for day in days]


def purchase_order(plan, ref, as_of, supplier=""):
    """This week's order as purchase-order lines (only products with a quantity)."""
    order = plan[plan["order_qty"] > 0]
    return pd.DataFrame({"PO number": ref, "Order date": f"{pd.Timestamp(as_of):%Y-%m-%d}", "Supplier": supplier or "",
                         "Product": order["name"].map(lambda n: str(n).split(" ", 1)[1]
                                                      if not str(n)[:1].isalnum() and " " in str(n) else str(n)),
                         "Quantity": order["order_qty"].astype(int), "Unit cost (RM)": order["unit_cost"].round(2),
                         "Line total (RM)": order["order_rm"].round(2)})


def activity(state, names=None, limit=50):
    """Every decision LARIS has recorded (alerts, waste, orders, stock counts), newest first. `state` is the local
    store's dict (store.load())."""
    names = names or {}
    rows = []
    for key, v in (state.get("alerts") or {}).items():
        ref, _, p = key.partition("|")
        rows.append({"When": v.get("at", ""), "Area": "A · Alert", "Product": names.get(p, p), "What": v.get("status", ""),
                     "Detail": v.get("choice", "")})
    for key, v in (state.get("waste") or {}).items():
        ref, _, p = key.partition("|")
        rows.append({"When": v.get("at", ""), "Area": "R · Waste", "Product": names.get(p, p), "What": v.get("status", ""),
                     "Detail": v.get("choice", "")})
    for ref, v in (state.get("orders") or {}).items():
        for h in v.get("history", []):
            rows.append({"When": h.get("at", ""), "Area": "S · Order", "Product": ref, "What": h.get("status", ""),
                         "Detail": h.get("note", "")})
    for v in state.get("stock_log") or []:
        rows.append({"When": v.get("at", ""), "Area": "Stock count", "Product": v.get("name", ""),
                     "What": f"{v.get('before', 0):,.0f} → {v.get('after', 0):,.0f}", "Detail": v.get("reason", "")})
    df = pd.DataFrame(rows, columns=["When", "Area", "Product", "What", "Detail"])
    return df.sort_values("When", ascending=False).head(limit).reset_index(drop=True)
