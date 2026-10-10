"""LARIS shared context: everything the pages show for one shop, replay week and set of inputs.

Layer 1 (AI model) outputs are read from outputs/ (forecasts.parquet, sigma.csv). Layer 2 (risk
assessment, categories, priority) and layer 3 (budget allocation) run live here via inventory.py.
No Streamlit imports, so this can be tested on its own.
"""
from math import ceil, sqrt

import numpy as np
import pandas as pd

from inventory import (TAU_ACT, TIER_RANK, _normal_loss, allocate_budget, assess, categorize, dead_stock,
                       horizon_demand, make_item, priority, product_settings, score_allocation)

# Sample kedai runcit (ILLUSTRATIVE): item names, RM prices and weekly sales are made up for the demo. Each item
# replays the daily sales pattern of one Favorita product family, scaled to these weekly sales.
SAMPLE_SHOP = {  # family: (item, cost RM, selling price RM, units sold last 7 days)
    "GROCERY I": ("Maggi Curry 5-pack", 4.20, 5.20, 60),
    "BEVERAGES": ("Milo 1kg", 15.50, 18.90, 20),
    "DAIRY": ("Fresh milk 1L", 6.20, 7.50, 35),
    "BREAD/BAKERY": ("White bread loaf", 3.40, 4.10, 70),
    "EGGS": ("Eggs, grade B (tray of 30)", 11.00, 13.50, 25),
    "POULTRY": ("Fresh chicken 1kg", 9.00, 11.00, 30),
    "PRODUCE": ("Sawi (vegetables) 500g", 2.00, 3.00, 40),
    "MEATS": ("Beef 500g", 18.00, 22.00, 10),
    "FROZEN FOODS": ("Frozen burger patties 12pc", 9.50, 12.00, 15),
    "CLEANING": ("Dishwashing liquid 900ml", 4.50, 6.00, 12),
    "PERSONAL CARE": ("Shampoo 400ml", 12.00, 15.90, 8),
    "DELI": ("Fishballs 500g", 6.00, 7.90, 20),
}

QGRID = np.round(np.linspace(0.01, 0.99, 99), 2)   # same grid as pipeline.uncertainty_table
QCOLS = [f"q{int(round(x * 100)):02d}" for x in QGRID]


def conformal_quantiles(unc, product, L):
    """Validation error quantiles of L-day totals for a product (fallback: all products), or None."""
    if unc is None or L > 7:
        return None
    u = unc[(unc["L"] == L) & (unc["product"] == product)]
    if u.empty:
        u = unc[(unc["L"] == L) & (unc["product"] == "ALL")]
    return None if u.empty else u[QCOLS].iloc[0].to_numpy(float)

COVER_PATTERN = [1.5, 6, 4, 12, 0.8, 1, 3.5, 4, 1.5, 10, 0.5, 3]   # default stock = N days of forecast (a mix)
PRESETS = {
    "Mixed week": {"budget_pct": 60, "cover": {}, "default": None},
    "Normal week": {"budget_pct": 100, "cover": {}, "default": 6.0},
    "Tight budget": {"budget_pct": 60, "cover": {"EGGS": 1.0, "BREAD/BAKERY": 0.5, "DAIRY": 15.0},
                     "default": None},
    "Sparse history": {"budget_pct": 75, "cover": {}, "default": 6.0, "widest_band": 0.8},
}
INPUT_COLUMNS = ["product", "Name", "Must-have", "On hand", "On order", "Sales last 7 days", "Unit cost (RM)",
                 "Margin (RM)", "Shelf life (days)", "Lead time (days)", "Review (days)", "Pack size"]
Z90 = 1.645


def week_view(fc, store, as_of, scale=1.0):
    """Forecast and recent history for one store, for the 7 days starting at `as_of`."""
    as_of = pd.Timestamp(as_of)
    end = as_of + pd.Timedelta(days=6)
    sub = fc[fc["store"] == store]
    window = sub[(sub["date"] >= as_of) & (sub["date"] <= end)]
    days = pd.date_range(as_of, end)
    fc_wide = window.pivot_table(index="date", columns="product", values="pred_model").reindex(days).fillna(0)
    act_wide = window.pivot_table(index="date", columns="product", values="y").reindex(days)
    past = sub[sub["date"] < as_of]
    last7 = past[past["date"] >= as_of - pd.Timedelta(days=7)].groupby("product")["y"].sum()
    return {
        "as_of": as_of, "end": end, "sub": sub, "window": window, "past": past,
        "products": sorted(window["product"].unique()),
        "fc_wide": fc_wide * scale, "act_wide": act_wide * scale, "last7": last7 * scale,
        "promo_days": window.assign(p=window["promo"] > 0).groupby("product")["p"].sum(),
        "holiday": bool(window["holiday"].max()) if len(window) else False,
    }


def sigma_for(sig, store, product, daily_fc, scale=1.0):
    """Validation-period daily error spread for one series (scaled); fallback 30% of the forecast."""
    sid = f"{store}|{product}"
    if sid in sig.index:
        return float(sig.loc[sid, "sigma_d"]) * scale, False
    return max(1.0 * scale, float(np.mean(daily_fc)) * 0.3), True


def default_inputs(week, settings, sig, store, preset="Mixed week"):
    """Editable shop inputs: stock levels set as days of forecast cover (deterministic per preset),
    plus PLACEHOLDER settings from product_settings.csv."""
    p = PRESETS.get(preset, PRESETS["Mixed week"])
    widest = None
    if p.get("widest_band"):
        ratios = {}
        for prod in week["products"]:
            mean = float(week["fc_wide"][prod].mean())
            s, _ = sigma_for(sig, store, prod, week["fc_wide"][prod])
            ratios[prod] = s / mean if mean > 0 else 0
        widest = max(ratios, key=ratios.get) if ratios else None
    rows = []
    for i, prod in enumerate(week["products"]):
        s = product_settings(settings, prod)
        name, cost, price, sales7 = SAMPLE_SHOP.get(prod, (s["display_name"], s["unit_cost_rm"],
                                                           s["unit_cost_rm"] + s["margin_rm"], None))
        if sales7 is None:
            sales7 = round(float(week["last7"].get(prod, 0.0)))
        cover = p["cover"].get(prod, p["default"] if p["default"] is not None else COVER_PATTERN[i % len(COVER_PATTERN)])
        if widest == prod:
            cover = p["widest_band"] * int(s["lead_time_days"])
        rows.append({
            "product": prod, "Name": f"{s['icon']} {name}".strip(), "Must-have": bool(s["must_have"]),
            "On hand": float(round(sales7 / 7 * cover)), "On order": 0.0, "Sales last 7 days": float(sales7),
            "Unit cost (RM)": float(cost), "Margin (RM)": round(float(price) - float(cost), 2),
            "Shelf life (days)": int(s["shelf_life_days"]), "Lead time (days)": int(s["lead_time_days"]),
            "Review (days)": int(s["review_days"]), "Pack size": int(s["pack_size"]),
        })
    return pd.DataFrame(rows, columns=INPUT_COLUMNS), widest


def _track_record(past, product, as_of, days=28):
    """Model vs same-day-last-week error on the last `days` days before as_of (actuals already known)."""
    g = past[(past["product"] == product) & (past["date"] >= as_of - pd.Timedelta(days=days))]
    g = g.dropna(subset=["y", "pred_model", "pred_naive7"])
    tot = g["y"].sum()
    if len(g) < 7 or tot <= 0:
        return None, None, len(g)
    return (float((g["y"] - g["pred_model"]).abs().sum() / tot),
            float((g["y"] - g["pred_naive7"]).abs().sum() / tot), len(g))


def _anomaly(past, product, as_of, sigma_raw):
    """Unusual recent sales: 2+ of the last 7 days outside +/-3 sigma of the model, or a zero run
    in a normally busy series (possible stockout, data error or demand shift)."""
    g = past[(past["product"] == product) & (past["date"] >= as_of - pd.Timedelta(days=28))].sort_values("date")
    if g.empty:
        return False, ""
    last = g[g["date"] >= as_of - pd.Timedelta(days=7)]
    z = (last["y"] - last["pred_model"]) / max(sigma_raw, 1e-9)
    n_out = int((z.abs() > 3).sum())
    zero_run = len(last) >= 5 and (last["y"].tail(5) == 0).all() and g["y"].median() >= 5
    if zero_run:
        return True, "no sales for 5+ days in a normally busy product"
    if n_out >= 2:
        return True, f"sales were outside the model's range on {n_out} of the last 7 days"
    return False, ""


def assess_products(week, sig, store, inputs, service=0.95, scale=1.0, unc=None, alert_cfg=None):
    """Layer 2: risk, category, priority and a plain-language explanation for every product.

    When the pipeline's alert backtest chose the validation-error (conformal) uncertainty model,
    P(stockout before delivery) and expected units short use those error quantiles; the alert
    threshold is the one chosen on the validation period."""
    alert_cfg = alert_cfg or {}
    use_conformal = alert_cfg.get("uncertainty_model") == "conformal"
    tau = float(alert_cfg.get("tau_act", TAU_ACT))
    rows, items = [], []
    for _, r in inputs.iterrows():
        prod = r["product"]
        # The model's daily pattern is scaled to the shop's own recent sales; a product with no sales history in
        # the data (e.g. added by the user) gets a flat forecast at its recent sales rate.
        sales7, data7 = float(r["Sales last 7 days"]), float(week["last7"].get(prod, 0.0))
        # forecast_source says where the 7-day forecast comes from, so every screen can tell a real forecast of 0
        # ('model' with zero recent sales) from a missing one ('unavailable'): model = the AI model's pattern scaled
        # to the shop; baseline = no model forecast, so last week's sales repeated; unavailable = neither exists.
        if prod in week["fc_wide"] and data7 > 0:
            ratio, source = sales7 / data7, "model"
            daily = week["fc_wide"][prod].to_numpy() * ratio
            sigma, fallback = sigma_for(sig, store, prod, daily, scale * ratio)
        else:
            ratio, source = 0.0, "baseline" if sales7 > 0 else "unavailable"
            daily = np.full(7, sales7 / 7)
            sigma, fallback = max(0.5, 0.3 * sales7 / 7), True
        sigma = max(sigma, 1e-9)   # zero recent sales scales the error to 0; avoid dividing by it below
        lead, rev, shelf = int(r["Lead time (days)"]), int(r["Review (days)"]), int(r["Shelf life (days)"])
        cost, margin, pack = float(r["Unit cost (RM)"]), float(r["Margin (RM)"]), int(r["Pack size"])
        on_hand, on_order, must = float(r["On hand"]), float(r["On order"]), bool(r["Must-have"])
        a = assess(daily, sigma, on_hand, on_order, lead, rev, service, cost, margin, pack, shelf)
        d = dead_stock(daily, sigma, on_hand, shelf, cost)
        w = a["window"]
        mu_w, sd_w = horizon_demand(daily, w), sigma * sqrt(w)
        avail = on_hand + on_order
        q = conformal_quantiles(unc, prod, lead) if use_conformal else None
        p_lead = horizon_demand(daily, lead)
        if q is not None and p_lead > 0:
            a["p_stockout"] = float(1 - np.interp(avail / p_lead - 1, q, QGRID, left=0.005, right=0.995))
            a["expected_short"] = float(np.maximum(0, p_lead * (1 + q) - avail).mean())
            a["margin_at_risk"] = a["expected_short"] * margin
        window_short = sd_w * _normal_loss((avail - mu_w) / sd_w)
        fc7 = a["demand_7d"]
        band_pct = Z90 * sigma * sqrt(7) / fc7 if fc7 > 0 else float("inf")

        effects = {}
        wp = week["window"][week["window"]["product"] == prod]
        for name in ("promo", "holiday", "payday"):
            col = f"pred_no_{name}"
            if col in wp:
                effects[name] = float((wp["pred_model"] - wp[col]).sum()) * scale * ratio
        hist_n = int(week["past"][week["past"]["product"] == prod]["y"].notna().sum())
        m_err, n_err, _ = _track_record(week["past"], prod, week["as_of"])
        anomaly, anomaly_why = _anomaly(week["past"], prod, week["as_of"], sigma / (scale * ratio) if ratio else sigma)
        low_why = []
        if source == "unavailable":
            low_why.append("no sales history and no sales last week, so there is no forecast")
        elif hist_n == 0:
            low_why.append("no sales history, so the forecast simply repeats your recent sales")
        elif hist_n < 28:
            low_why.append(f"only {hist_n} days of sales history")
        if fallback:
            low_why.append("no measured forecast error for this product")
        if m_err is not None and n_err is not None and m_err > n_err:
            low_why.append("the model was less accurate than 'same day last week' for this product lately")
        if band_pct > 1.0:
            low_why.append("the forecast range is wider than the forecast itself")

        row = {**a, "product": prod, "name": r["Name"], "must_have": must, "lead_time": lead,
               "review": rev, "shelf_life": shelf, "unit_cost": cost, "margin": margin, "pack_size": pack,
               "on_hand": on_hand, "on_order": on_order, "sigma": sigma, "band_pct": band_pct,
               "demand_last7": sales7, "window_short": window_short, "ratio": ratio,
               "forecast_source": source,
               "dead_flag": d["flag"], "perishable": d["perishable"], "days_of_cover": d["days_of_cover"],
               "expected_expire_units": d["expected_expire_units"], "expected_expire_rm": d["expected_expire_rm"],
               "demand_shelf_life": d["demand_shelf_life"],
               "dead_action": d["action"], "low_confidence": bool(low_why), "low_why": low_why,
               "anomaly": anomaly, "anomaly_why": anomaly_why, "model_err28": m_err, "naive_err28": n_err,
               "promo_days": int(week["promo_days"].get(prod, 0)), "holiday": week["holiday"],
               "effects": effects, "tau_act": tau,
               "uncertainty": "past errors of the model" if q is not None else "measured daily error"}
        row["category"], row["label"] = categorize(row)
        row["tier"], row["rm_at_risk"], row["act_by"] = priority(row)
        if row["category"] == "STOCKOUT_IMMINENT":
            row["bridge_qty"] = float(max(1, ceil(row["expected_short"] / pack)) * pack)
        else:
            row["bridge_qty"] = 0.0
        row["bridge_value"] = row["bridge_qty"] * cost
        row["action"] = action_text(row)
        row["why"] = explain(row)
        rows.append(row)
        items.append(make_item(prod, daily, sigma, on_hand, on_order,
                               {"lead_time_days": lead, "review_days": rev, "shelf_life_days": shelf,
                                "unit_cost_rm": cost, "margin_rm": margin, "pack_size": pack,
                                "must_have": must}, must_have=must, dead=d["flag"]))
    df = pd.DataFrame(rows)
    if len(df):
        df["_t"] = df["tier"].map(TIER_RANK)
        df = df.sort_values(["_t", "rm_at_risk"], ascending=[True, False]).drop(columns="_t").reset_index(drop=True)
    return df, items


def action_text(row):
    code = row["category"]
    if code == "STOCKOUT_IMMINENT":
        if row["low_confidence"]:
            return "Check the shelf now; if it's low, top up from a wholesaler and include it in this order"
        return (f"Buy {row['bridge_qty']:,.0f} from a wholesaler today (RM {row['bridge_value']:,.0f}) "
                "and include it in this order")
    if code in ("REORDER_NEEDED", "DEMAND_SURGE"):
        return "Include it in this order (see Budget & orders)"
    if code in ("EXPIRY_RISK", "OVERSTOCK"):
        return row["dead_action"]
    if code == "SALES_ANOMALY":
        return "Check the shelf and the POS records for this product"
    if code == "LOW_CONFIDENCE":
        return "Check stock manually; the forecast is less reliable here"
    return "No action needed this cycle"


def explain(row):
    """Evidence for one product as (tag, text) pairs. Tags say where each statement comes from:
    'AI forecast' (the trained model), 'Calculation' (from the forecast and measured error),
    'Your setting' (shop inputs, placeholders by default), 'Track record', 'Caution'."""
    out = []
    fc7, last7 = row["demand_7d"], row["demand_last7"]
    if last7 <= 0:
        change = "no sales in the last 7 days"
    elif abs(fc7 / last7 - 1) < 0.005:
        change = f"about the same as last 7 days' {last7:,.0f}"
    else:
        change = f"{fc7 / last7 - 1:+.0%} vs last 7 days' {last7:,.0f}"
    out.append(("AI forecast", f"Expected to sell {fc7:,.0f} in the next 7 days ({change})."))
    fx = row.get("effects") or {}
    names = {"promo": f"the planned promotion ({row['promo_days']} day(s))", "holiday": "the public holiday",
             "payday": "payday"}
    shown = False
    for k, v in fx.items():
        if abs(v) >= max(1.0, 0.02 * fc7):
            out.append(("AI what-if", f"The model estimates {names[k]} {'adds' if v > 0 else 'removes'} about "
                                      f"{abs(v):,.0f} units this week (same model re-run without it)."))
            shown = True
    if not shown and not fx:
        drivers = ([f"a promotion on {row['promo_days']} day(s)"] if row["promo_days"] else []) + \
                  (["a public holiday"] if row["holiday"] else [])
        if drivers:
            out.append(("AI forecast", "The model takes into account " + " and ".join(drivers) + " this week."))
    if np.isfinite(row["band_pct"]):
        out.append(("Calculation", f"Likely range ±{row['band_pct']:.0%} over 7 days, from the model's measured error."))
    avail = row["on_hand"] + row["on_order"]
    lasts = _days(avail / (fc7 / 7)) if fc7 > 0 else "no sales expected"
    out.append(("Calculation", f"Stock of {avail:,.0f} lasts {lasts}; delivery takes {row['lead_time']} day(s)."))
    out.append(("Calculation", f"{row['p_stockout']:.0%} chance of running out before the delivery arrives "
                               f"(from the {row['uncertainty']}; LARIS alerts at {row['tau_act']:.0%} or more, a level "
                               "chosen on past weeks)."))
    if row["dead_flag"]:
        out.append(("Calculation", f"{row['days_of_cover']:,.0f} days of stock vs a {row['shelf_life']}-day shelf life"
                                   + (f"; about {row['expected_expire_units']:,.0f} units (RM {row['expected_expire_rm']:,.0f}) "
                                      "may expire unsold." if row["perishable"] else ".")))
    if row["rm_at_risk"] > 0:
        out.append(("Calculation", f"RM {row['rm_at_risk']:,.0f} at risk if nothing is done."))
    if row["model_err28"] is not None:
        out.append(("Track record", f"Last 28 days for this product: model error {row['model_err28']:.0%} vs "
                                    f"{row['naive_err28']:.0%} for 'same day last week'."))
    if row["anomaly"]:
        out.append(("Caution", f"Unusual recent sales: {row['anomaly_why']}."))
    for w in row["low_why"]:
        out.append(("Caution", f"Lower confidence: {w}."))
    out.append(("Your setting", f"Lead time {row['lead_time']} d, shelf life {row['shelf_life']} d, margin RM "
                                f"{row['margin']:.2f}{', must-have' if row['must_have'] else ''} (placeholders unless you changed them)."))
    return out


def build_context(fc, sig, settings, store, as_of, inputs, budget_rm=None, scale=1.0, service=0.95,
                  unc=None, alert_cfg=None, protect_must_have=True, adjust=None, extra_rm=50.0):
    """The one shared planning context every page reads, computed once per run.

    budget_rm: cash for this order (None = the full recommended order). protect_must_have: the optimiser's
    strategy (True = essentials first, then value per RM; False = value per RM only). adjust: the owner's
    quantity overrides {product: qty}; they change the order (order_qty / order_rm) but never the recommendation
    (qty), so both stay visible."""
    week = week_view(fc, store, as_of, scale)
    rows, items = assess_products(week, sig, store, inputs, service, scale, unc, alert_cfg)
    ctx = {"week": week, "rows": rows, "items": items, "store": store, "scale": scale, "service": service,
           "protect_must_have": protect_must_have, "empty": not items}
    if not items:
        return {**ctx, "plan": pd.DataFrame(), "alloc": pd.DataFrame(), "totals": {}, "ideal_rm": 0.0,
                "budget_rm": float(budget_rm or 0), "order_rm": 0.0, "budget_limited": False, "scenario": None}
    _, ideal_tot = allocate_budget(items, None, protect_must_have=protect_must_have)
    budget = ideal_tot["ideal_rm"] if budget_rm is None else max(0.0, float(budget_rm))
    alloc, tot = allocate_budget(items, budget, protect_must_have=protect_must_have)
    names = dict(zip(rows["product"], rows["name"]))
    alloc["name"] = alloc["product"].map(names)
    plan = plan_table(rows, alloc, items)
    adjust = adjust or {}
    plan["order_qty"] = [float(adjust.get(p, q)) for p, q in zip(plan["product"], plan["qty"])]
    plan["adjusted"] = plan["order_qty"] != plan["qty"]
    plan["order_rm"] = plan["order_qty"] * plan["unit_cost"]
    return {**ctx, "plan": plan, "alloc": alloc, "totals": tot, "ideal_rm": ideal_tot["ideal_rm"],
            "budget_rm": budget, "order_rm": float(plan["order_rm"].sum()),
            "budget_limited": tot["spent_rm"] < ideal_tot["ideal_rm"] - 0.5,
            "scenario": budget_scenario(items, alloc, budget, extra_rm, names, protect_must_have)}


def budget_scenario(items, alloc, budget, extra, names, protect_must_have=True):
    """What `extra` RM more would add, and the estimated drop in expected lost profit + waste (an ESTIMATE from
    the same forecast distribution the optimiser uses)."""
    more, _ = allocate_budget(items, budget + extra, protect_must_have=protect_must_have)
    added = more.set_index("product")["qty"] - alloc.set_index("product")["qty"]
    loss = lambda q: (lambda s: s["exp_lost_margin_rm"] + s["exp_waste_rm"])(score_allocation(items, q))
    return {"extra": extra, "added": [(names.get(p, p), q) for p, q in added.items() if q > 0],
            "saves": loss(alloc["qty"].to_numpy()) - loss(more["qty"].to_numpy()),
            "spent_more": float(more["spend_rm"].sum() - alloc["spend_rm"].sum())}


ACTION_RANK = {"RESTOCK": 0, "STOP": 1, "REDUCE": 2, "MAINTAIN": 3}


def _days(x):
    """Days of stock in words (stock / average daily forecast), the same measure the product page shows."""
    if not np.isfinite(x):
        return "no sales expected"
    return f"about {x:.1f} days" if round(x, 1) < 3 else f"about {x:,.0f} days"


def plan_table(rows, alloc, items):
    """One recommendation per product, compared with simply reordering last week's sales (the 'usual order'):
    RESTOCK (order clearly more), REDUCE (clearly less), STOP (dead stock: don't reorder), MAINTAIN.
    impact_rm = expected lost profit + expected waste of the usual order minus that of LARIS's order (an ESTIMATE
    from the forecast distribution; positive = LARIS's order is expected to lose less). Ranked by urgency, then
    impact."""
    a = alloc.set_index("product")
    it = {x["product"]: x for x in items}
    loss = lambda x, q: (lambda s: s["exp_lost_margin_rm"] + s["exp_waste_rm"])(score_allocation([x], [q]))
    out = []
    for _, r in rows.iterrows():
        p, x = r["product"], it[r["product"]]
        pack = x["pack_size"]
        qty, ideal = float(a.at[p, "qty"]), float(a.at[p, "ideal_qty"])
        usual = float(round(r["demand_last7"] * r["review"] / 7 / pack) * pack)
        fc7, last7, lead = r["demand_7d"], r["demand_last7"], int(r["lead_time"])
        avail = r["on_hand"] + r["on_order"]
        cover = avail / (fc7 / 7) if fc7 > 0 else float("inf")
        change = fc7 / last7 - 1 if last7 > 0 else 0.0
        trend = "Growing" if change > 0.1 else "Declining" if change < -0.1 else "Stable"
        stockout = r["category"] == "STOCKOUT_IMMINENT"
        if r["dead_flag"]:
            action = "STOP"
        elif stockout or (ideal > usual * 1.2 and ideal - usual >= pack):
            action = "RESTOCK"
        elif ideal < usual * 0.8:
            action = "REDUCE"
        else:
            action = "MAINTAIN"
        impact = loss(x, usual) - loss(x, qty)

        rod = r["run_out_day"]
        spoils = x["overstock_cost"] >= x["unit_cost"] - 1e-9 and cover < 0.8 * r["window"]
        if stockout:
            risk = (f"Likely to run out in {_days(cover)}; the next delivery takes {lead} day(s)."
                    if rod is not None and not pd.isna(rod) else
                    f"{r['p_stockout']:.0%} chance of running out before the next delivery ({lead} day(s)).")
        elif r["dead_flag"] and r["perishable"]:
            risk = (f"About {r['expected_expire_units']:,.0f} units may expire unsold: {_days(cover)} of stock, "
                    f"{r['shelf_life']}-day shelf life.")
        elif r["dead_flag"]:
            risk = f"Overstocked: {_days(cover)} of stock is tying up cash."
        elif trend == "Declining":
            risk = f"Sales expected to fall {abs(change):.0%} this week."
        elif action == "RESTOCK":
            risk = f"Stock lasts {_days(cover)}, not enough until the following delivery."
        elif action == "REDUCE" and spoils:
            risk = f"Spoils within {r['shelf_life']} day(s), so leftovers get thrown away."
        elif action == "REDUCE":
            risk = f"Stock lasts {_days(cover)}, enough to need less than usual."
        else:
            risk = f"Stock lasts {_days(cover)}."

        if action == "STOP":
            rec = "Don't reorder" + ("; put it on sale before it expires" if r["perishable"] else "; consider a promotion")
        elif action == "RESTOCK":
            rec = (f"Order {qty:,.0f} units (you'd usually order {usual:,.0f})" if qty > usual else
                   f"Order {qty:,.0f} units today")
            if qty < ideal:
                rec += f"; your budget covers {qty:,.0f} of the {ideal:,.0f} needed"
        elif action == "REDUCE":
            rec = f"Reduce the order from {usual:,.0f} to {qty:,.0f} units"
        else:
            rec = f"Order {qty:,.0f} units, as usual" if qty else "No order needed this week"

        cash = max(0.0, usual - qty) * x["unit_cost"]
        if action == "RESTOCK":
            impact_txt = f"Avoids about RM {impact:,.0f} in lost profit" if impact >= 1 else "Limited by your budget"
        elif action in ("REDUCE", "STOP") and impact >= 0.9 * cash and impact >= 1:
            impact_txt = f"Avoids about RM {impact:,.0f} of stock likely to go to waste"
        elif action in ("REDUCE", "STOP"):
            impact_txt = f"Frees RM {cash:,.0f} cash" + (f", avoids about RM {impact:,.0f} in likely losses"
                                                          if impact >= 1 else "")
        else:
            impact_txt = ""

        sold = f"Expected to sell {fc7:,.0f} next week" + (
            f", up {change:.0%} on last week" if trend == "Growing" else
            f", down {abs(change):.0%} on last week" if trend == "Declining" else ", about the same as last week")
        why = {
            "RESTOCK": (f"{sold}; current stock may not last until the next supplier delivery." if stockout else
                        f"{sold}; current stock and your usual order won't cover it until the next order arrives."),
            "REDUCE": (f"{sold}; it spoils within {r['shelf_life']} day(s), so ordering a little less than last "
                       "week's sales is expected to lose less than throwing leftovers away." if spoils else
                       f"{sold}; the stock you have already covers most of it, so last week's order would leave extra."),
            "STOP": f"{sold}; the stock you have would take {_days(cover)} to sell"
                    + (", longer than its shelf life." if r["perishable"] else "."),
            "MAINTAIN": f"{sold}; your usual order fits.",
        }[action]
        if r["forecast_source"] == "unavailable":
            risk = "No forecast: no sales history and nothing recorded as sold last week."
            rec = "Check stock manually before ordering"
            why = "LARIS can't forecast this product yet. Enter last week's sales in Products to get a forecast."
            impact_txt = ""
        out.append({"product": p, "name": r["name"], "action": action, "must_have": r["must_have"],
                    "forecast_7d": fc7 if r["forecast_source"] != "unavailable" else np.nan,
                    "forecast_source": r["forecast_source"],
                    "risk": risk, "rec": rec, "impact_rm": impact, "impact_txt": impact_txt, "why": why,
                    "qty": qty, "ideal": ideal, "usual": usual, "spend_rm": qty * x["unit_cost"],
                    "unit_cost": x["unit_cost"], "margin": x["margin"], "pack_size": pack,
                    "trend": trend, "change": change, "cover_days": cover, "urgent": stockout})
    df = pd.DataFrame(out)
    if len(df):
        df["_u"] = np.where(df["urgent"], 0, np.where(df["action"] == "MAINTAIN", 2, 1))
        df["_i"] = df["impact_rm"].clip(lower=0) + df["action"].map(ACTION_RANK) * 1e-6
        df = df.sort_values(["_u", "_i"], ascending=[True, False]).drop(columns=["_u", "_i"]).reset_index(drop=True)
    return df


def demo_week(fc, settings):
    """The pitch scenario, chosen by a stated rule rather than by hand: in the median-volume store,
    the replay week (starting Wednesday) where the AI predicts the largest rise in must-have demand
    over the previous 7 days' actual sales."""
    test = fc[fc["split"] == "test"]
    vol = test.groupby("store")["y"].sum().sort_values()
    store = vol.index[len(vol) // 2]
    must = [p for p in fc["product"].unique() if bool(product_settings(settings, p)["must_have"])]
    sub = fc[(fc["store"] == store) & fc["product"].isin(must)].set_index("date")
    end = test["date"].max()
    best, best_d = -np.inf, None
    for d in sorted(test["date"].unique()):
        d = pd.Timestamp(d)
        if d.dayofweek != 2 or d + pd.Timedelta(days=6) > end:
            continue
        nxt = sub.loc[d:d + pd.Timedelta(days=6), "pred_model"].sum()
        prev = sub.loc[d - pd.Timedelta(days=7):d - pd.Timedelta(days=1), "y"].sum()
        rise = nxt / prev - 1 if prev > 0 else -np.inf
        if rise > best:
            best, best_d = rise, d
    return store, best_d, best
