"""LARIS shared context: everything the pages show for one shop, replay week and set of inputs.

Layer 1 (AI model) outputs are read from outputs/ (forecasts.parquet, sigma.csv). Layer 2 (risk
assessment, categories, priority) and layer 3 (budget allocation) run live here via inventory.py.
No Streamlit imports, so this can be tested on its own.
"""
from math import sqrt

import numpy as np
import pandas as pd

from inventory import (TIER_RANK, _normal_loss, allocate_budget, assess, categorize, dead_stock,
                       horizon_demand, make_item, priority, product_settings)

COVER_PATTERN = [1.5, 6, 2.5, 12, 4, 9, 1, 7, 3, 10, 5, 8]   # default stock = N days of forecast (a mix)
PRESETS = {
    "Mixed week": {"budget_pct": 60, "cover": {}, "default": None},
    "Normal week": {"budget_pct": 100, "cover": {}, "default": 6.0},
    "Tight budget": {"budget_pct": 60, "cover": {"EGGS": 1.0, "BREAD/BAKERY": 0.5, "DAIRY": 15.0},
                     "default": None},
    "Sparse history": {"budget_pct": 75, "cover": {}, "default": 6.0, "widest_band": 0.8},
}
INPUT_COLUMNS = ["product", "Name", "Must-have", "On hand", "On order", "Unit cost (RM)", "Margin (RM)",
                 "Shelf life (days)", "Lead time (days)", "Review (days)", "Pack size"]
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
        mean = float(week["fc_wide"][prod].mean())
        cover = p["cover"].get(prod, p["default"] if p["default"] is not None else COVER_PATTERN[i % len(COVER_PATTERN)])
        if widest == prod:
            cover = p["widest_band"] * int(s["lead_time_days"])
        rows.append({
            "product": prod, "Name": f"{s['icon']} {s['display_name']}".strip(), "Must-have": bool(s["must_have"]),
            "On hand": float(round(mean * cover)), "On order": 0.0,
            "Unit cost (RM)": float(s["unit_cost_rm"]), "Margin (RM)": float(s["margin_rm"]),
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


def assess_products(week, sig, store, inputs, service=0.95, scale=1.0):
    """Layer 2: risk, category, priority and a plain-language explanation for every product."""
    rows, items = [], []
    for _, r in inputs.iterrows():
        prod = r["product"]
        daily = week["fc_wide"][prod].to_numpy() if prod in week["fc_wide"] else np.zeros(7)
        sigma, fallback = sigma_for(sig, store, prod, daily, scale)
        lead, rev, shelf = int(r["Lead time (days)"]), int(r["Review (days)"]), int(r["Shelf life (days)"])
        cost, margin, pack = float(r["Unit cost (RM)"]), float(r["Margin (RM)"]), int(r["Pack size"])
        on_hand, on_order, must = float(r["On hand"]), float(r["On order"]), bool(r["Must-have"])
        a = assess(daily, sigma, on_hand, on_order, lead, rev, service, cost, margin, pack, shelf)
        d = dead_stock(daily, sigma, on_hand, shelf, cost)
        w = a["window"]
        mu_w, sd_w = horizon_demand(daily, w), sigma * sqrt(w)
        avail = on_hand + on_order
        window_short = sd_w * _normal_loss((avail - mu_w) / sd_w)
        fc7 = a["demand_7d"]
        band_pct = Z90 * sigma * sqrt(7) / fc7 if fc7 > 0 else float("inf")

        hist_n = int(week["past"][week["past"]["product"] == prod]["y"].notna().sum())
        m_err, n_err, _ = _track_record(week["past"], prod, week["as_of"])
        anomaly, anomaly_why = _anomaly(week["past"], prod, week["as_of"], sigma / scale if scale else sigma)
        low_why = []
        if hist_n < 28:
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
               "demand_last7": float(week["last7"].get(prod, 0.0)), "window_short": window_short,
               "dead_flag": d["flag"], "perishable": d["perishable"], "days_of_cover": d["days_of_cover"],
               "expected_expire_units": d["expected_expire_units"], "expected_expire_rm": d["expected_expire_rm"],
               "dead_action": d["action"], "low_confidence": bool(low_why), "low_why": low_why,
               "anomaly": anomaly, "anomaly_why": anomaly_why, "model_err28": m_err, "naive_err28": n_err,
               "promo_days": int(week["promo_days"].get(prod, 0)), "holiday": week["holiday"]}
        row["category"], row["label"] = categorize(row)
        row["tier"], row["rm_at_risk"], row["act_by"] = priority(row)
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
    change = f"{fc7 / last7 - 1:+.0%} vs last 7 days' {last7:,.0f}" if last7 > 0 else "no sales in the last 7 days"
    out.append(("AI forecast", f"Expected to sell {fc7:,.0f} in the next 7 days ({change})."))
    drivers = []
    if row["promo_days"]:
        drivers.append(f"a promotion on {row['promo_days']} day(s)")
    if row["holiday"]:
        drivers.append("a public holiday")
    if drivers:
        out.append(("AI forecast", "The model takes into account " + " and ".join(drivers) + " this week."))
    if np.isfinite(row["band_pct"]):
        out.append(("Calculation", f"Likely range ±{row['band_pct']:.0%} over 7 days, from the model's measured error."))
    avail = row["on_hand"] + row["on_order"]
    rod = row["run_out_day"]
    lasts = "beyond 7 days" if rod is None or pd.isna(rod) else f"about {int(rod)} day(s)"
    out.append(("Calculation", f"Stock of {avail:,.0f} lasts {lasts}; delivery takes {row['lead_time']} day(s)."))
    out.append(("Calculation", f"{row['p_stockout']:.0%} chance of running out before the delivery arrives."))
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


def build_context(fc, sig, settings, store, as_of, inputs, budget_pct, scale=1.0, service=0.95):
    """Everything the pages need, computed once per run."""
    week = week_view(fc, store, as_of, scale)
    rows, items = assess_products(week, sig, store, inputs, service, scale)
    ideal_alloc, ideal_tot = allocate_budget(items, None)
    budget_rm = round(ideal_tot["ideal_rm"] * budget_pct / 100.0, 2)
    alloc, tot = allocate_budget(items, budget_rm)
    names = dict(zip(rows["product"], rows["name"])) if len(rows) else {}
    alloc["name"] = alloc["product"].map(names)
    # "With RM X more you'd add ..."
    extra = max(10.0, round(ideal_tot["ideal_rm"] * 0.10, -1))
    more_alloc, _ = allocate_budget(items, budget_rm + extra)
    more = (more_alloc.set_index("product")["qty"] - alloc.set_index("product")["qty"])
    more = [(names.get(p, p), q) for p, q in more.items() if q > 0]
    return {"week": week, "rows": rows, "items": items, "alloc": alloc, "totals": tot,
            "ideal_totals": ideal_tot, "budget_rm": budget_rm, "budget_pct": budget_pct,
            "more_rm": extra, "more": more, "store": store, "scale": scale, "service": service}


def sales_value_series(week, inputs, sig, store, scale=1.0, history_days=14):
    """Expected sales in RM/day for the week (forecast x placeholder price) with a 90% range
    (product errors assumed independent), plus actual RM/day for the previous days."""
    price = (inputs.set_index("product")["Unit cost (RM)"] + inputs.set_index("product")["Margin (RM)"])
    fw = week["fc_wide"]
    cols = [c for c in fw.columns if c in price.index]
    exp = (fw[cols] * price[cols]).sum(axis=1)
    var = sum((sigma_for(sig, store, c, fw[c], scale)[0] * price[c]) ** 2 for c in cols)
    band = Z90 * sqrt(var)
    fut = pd.DataFrame({"date": fw.index, "rm": exp.values, "lo": np.maximum(0, exp.values - band),
                        "hi": exp.values + band})
    past = week["past"]
    past = past[past["date"] >= week["as_of"] - pd.Timedelta(days=history_days)]
    past = past[past["product"].isin(cols)]
    hist = (past.assign(rm=past["y"] * scale * past["product"].map(price)).groupby("date")["rm"].sum()
            .reset_index())
    return fut, hist
