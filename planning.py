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

ACTION_LABEL = {"RESTOCK": "Buy more", "REDUCE": "Buy less", "STOP": "Don't reorder", "MAINTAIN": "As usual"}
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
    """Plain-language findings, most urgent first. Each is (level, text, page). Only data-supported findings."""
    plan, rows = ctx["plan"], ctx["rows"].set_index("product")
    out = []
    urgent = plan[plan["urgent"]]
    must_u, other_u = urgent[urgent["must_have"]], urgent[~urgent["must_have"]]
    if len(must_u):
        out.append(("URGENT", f"{len(must_u)} must-have product(s) may run out before your next delivery: "
                              f"{', '.join(must_u['name'])}.", "views/alerts.py"))
    if len(other_u):
        out.append(("URGENT", f"{len(other_u)} other product(s) may run out before your next delivery.",
                    "views/alerts.py"))
    if ctx["order_rm"] > ctx["budget_rm"] + 0.5:
        out.append(("WARNING", f"Your order exceeds your budget by RM {ctx['order_rm'] - ctx['budget_rm']:,.0f}.",
                    "views/budget.py"))
    elif ctx["budget_limited"]:
        short = plan[(plan["ideal"] > 0) & (plan["qty"] < plan["ideal"])]
        out.append(("WARNING", f"Your budget leaves RM {ctx['ideal_rm'] - ctx['totals']['spent_rm']:,.0f} of the "
                               f"recommended order unfilled; {len(short)} product(s) get less than they need.",
                    "views/budget.py"))
    stop = plan[plan["action"] == "STOP"]
    if len(stop):
        rm = float(rows.loc[stop["product"], "expected_expire_rm"].sum())
        out.append(("WARNING", f"{len(stop)} product(s) have more stock than they're likely to sell in time"
                               + (f" (about RM {rm:,.0f} may expire)." if rm >= 1 else "."), "views/waste.py"))
    rising = plan[plan["trend"] == "Growing"]
    if len(rising):
        out.append(("INFO", f"{len(rising)} product(s) are expected to sell noticeably more next week.",
                    "views/look_ahead.py"))
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
    if r["ratio"] > 0:
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
                rec, rec_why = "part", "Demand may increase, but " + " and ".join(reasons) + "."
            else:
                rec, rec_why = "full", "Demand is expected to rise, the forecast is fairly steady and the stock keeps."
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


def sales_summary(ctx, days=28):
    """Recorded sales per product over the last `days` days before the planning week (None = all available),
    priced with the shop's selling price and cost. Gross profit = revenue - cost of goods sold (not net profit).
    Products without history only have their 'sold last 7 days' figure, so they count in the 7-day period only."""
    week, rows = ctx["week"], ctx["rows"]
    as_of, scale, past = week["as_of"], ctx["scale"], week["past"]
    first = past["date"].min() if len(past) else as_of - pd.Timedelta(days=7)
    start = max(first, as_of - pd.Timedelta(days=days)) if days else first
    units_hist = past[(past["date"] >= start) & (past["date"] < as_of)].groupby("product")["y"].sum()
    out = []
    for r in rows.itertuples():
        price = r.unit_cost + r.margin
        if r.ratio > 0:
            units, has_hist = float(units_hist.get(r.product, 0.0)) * scale * r.ratio, True
        elif days == 7:
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
              "start": start, "end": as_of - pd.Timedelta(days=1), "days": int((as_of - start).days),
              "no_history": int((~df["has_history"]).sum()), "no_cost": int((~df["cost_known"]).sum())}
    return df, totals


def profit_insights(ctx, summary):
    """Findings that link sales performance to stock decisions. Each is (title, text, product, page)."""
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
                                                 "before the next delivery.", p, "views/alerts.py"))
        elif p in top_margin and pl["cover_days"] < r["lead_time"]:
            out.append(("High margin, running low", f"{name} earns one of your best margins, but its stock may not "
                                                    "last until the delivery.", p, "views/alerts.py"))
        if pl["cover_days"] > 14 and stock_rm >= 50:
            out.append(("High stock, slow sales", f"About RM {stock_rm:,.0f} is tied up in {name}, which may take "
                                                  f"{pl['cover_days']:.0f} days to sell.", p, "views/waste.py"))
        mp = s.at[p, "margin_pct"]
        if p in top_rev and pd.notna(mp) and mp < 15:
            out.append(("High sales, thin margin", f"{name} sells a lot but keeps only {mp:.0f}% as gross margin. "
                                                   "Check its cost and selling price.", p, "views/products.py"))
        if pl["trend"] == "Declining":
            out.append(("Sales expected to drop", f"{name} is expected to sell {abs(pl['change']):.0%} less next "
                                                  "week.", p, "views/look_ahead.py"))
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


# ---------------- My Products: card view ----------------
SORTS = {"Most urgent": None, "Highest revenue": ("revenue", False), "Highest gross profit": ("gross_profit", False),
         "Highest margin %": ("margin_pct", False), "Name (A–Z)": ("name", True), "Lowest stock": ("stock", True),
         "Highest stock": ("stock", False), "Fastest-selling": ("sold7", False), "Slowest-selling": ("sold7", True)}
FILTERS = ["All products", "Must-have", "Buy more", "Buy less", "Don't reorder", "As usual", "May run out",
           "Expiry risk"]


def product_cards(ctx, sort="Most urgent", flt="All products", search=""):
    """Plan rows plus 7-day revenue and gross profit, filtered, searched and sorted for the card view."""
    plan, rows = ctx["plan"], ctx["rows"].set_index("product")
    s7 = sales_summary(ctx, 7)[0].set_index("product")
    ps = plan["product"]
    df = plan.assign(stock=[rows.at[p, "on_hand"] + rows.at[p, "on_order"] for p in ps],
                     sold7=[rows.at[p, "demand_last7"] for p in ps],
                     revenue=s7.loc[ps, "revenue"].to_numpy(), gross_profit=s7.loc[ps, "gross_profit"].to_numpy(),
                     margin_pct=s7.loc[ps, "margin_pct"].to_numpy(),
                     expiry=[bool(rows.at[p, "dead_flag"] and rows.at[p, "perishable"]) for p in ps])
    if search:
        df = df[df["name"].str.contains(search, case=False, regex=False)]
    by_label = {v: k for k, v in ACTION_LABEL.items()}
    if flt == "Must-have":
        df = df[df["must_have"]]
    elif flt in by_label:
        df = df[df["action"] == by_label[flt]]
    elif flt == "May run out":
        df = df[df["urgent"]]
    elif flt == "Expiry risk":
        df = df[df["expiry"]]
    if SORTS.get(sort):
        col, asc = SORTS[sort]
        df = df.sort_values(col, ascending=asc, na_position="last")
    return df.reset_index(drop=True)
