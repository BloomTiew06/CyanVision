"""ShelfSignal decision layer: stockout risk, reorder quantity and policy simulation.

Pure functions with no data loading, so the app and the pipeline share them and
they can be tested on their own.

Assumptions (state these in the pitch):
- Forecast errors are roughly normal and independent from day to day, so the
  spread over n days is sigma_daily * sqrt(n).
- Lead time is fixed (what the user enters). Orders arrive at the start of day t + L.
- Stock on order is assumed to arrive within the lead time.
- Ordering is periodic: one order every `review` days (default weekly).
"""
from math import ceil, sqrt

import numpy as np
import pandas as pd
from scipy.stats import norm


def horizon_demand(daily_fc, days):
    """Forecast demand over `days`. Beyond the forecast length, extend with the mean daily forecast."""
    fc = np.asarray(daily_fc, dtype=float)
    days = int(days)
    if len(fc) == 0 or days <= 0:
        return 0.0
    if days <= len(fc):
        return float(fc[:days].sum())
    return float(fc.sum() + fc.mean() * (days - len(fc)))


def run_out_day(daily_fc, available):
    """First forecast day (1-based) on which cumulative demand exceeds available stock; None if it lasts."""
    cum = np.cumsum(np.asarray(daily_fc, dtype=float))
    over = np.nonzero(cum > available)[0]
    return int(over[0]) + 1 if len(over) else None


def _normal_loss(k):
    """Standard normal loss function E[(Z - k)+]."""
    return float(norm.pdf(k) - k * (1 - norm.cdf(k)))


def protection_window(lead_time, review, shelf_life=None):
    """Days an order placed today must cover: lead time + review cycle, but never more cover
    than the shelf life at the moment the delivery lands (L + min(R, S))."""
    lead, rev = max(1, int(lead_time)), max(1, int(review))
    if shelf_life is None or pd.isna(shelf_life):
        return lead + rev
    return lead + min(rev, max(1, int(shelf_life)))


def overstock_cost(unit_cost, shelf_life, window, holding_rate=0.02, buffer_days=3):
    """Cost of one unit left over at the end of the window: its full cost if it would expire
    (shelf life within window + buffer), otherwise a small holding cost."""
    if shelf_life is not None and not pd.isna(shelf_life) and int(shelf_life) <= int(window) + buffer_days:
        return float(unit_cost)
    return float(unit_cost) * holding_rate


def assess(daily_fc, sigma_d, on_hand, on_order=0.0, lead_time=3, review=7,
           service_level=0.95, unit_cost=0.0, unit_margin=0.0, pack_size=1, shelf_life=None):
    """Risk and reorder recommendation for one product.

    Returns stockout probability before an order placed today can arrive, expected units short,
    the order-up-to quantity for the protection window at the chosen service level, and a status:
      CRITICAL - stock runs out before an order placed today arrives: expedite, transfer or substitute
      ORDER    - stock + on order is below the order-up-to level: order today
      OK       - no order needed this cycle
    When CRITICAL, bridge_qty is the expected shortfall before the order lands (rounded up to packs),
    to buy from a wholesaler today.
    """
    z = float(norm.ppf(service_level))
    lead = max(1, int(lead_time))
    avail = float(on_hand) + float(on_order)
    sigma_d = max(float(sigma_d), 1e-9)

    d_lead = horizon_demand(daily_fc, lead)
    sd_lead = sigma_d * sqrt(lead)
    k = (avail - d_lead) / sd_lead
    p_stockout = float(1 - norm.cdf(k))
    exp_short = float(sd_lead * _normal_loss(k))

    cover = protection_window(lead, review, shelf_life)
    safety = z * sigma_d * sqrt(cover)
    target = horizon_demand(daily_fc, cover) + safety
    qty = max(0.0, target - avail)
    pack = max(1, int(pack_size))
    qty = float(ceil(qty / pack) * pack) if qty > 0 else 0.0

    rod = run_out_day(daily_fc, avail)
    if rod is not None and rod <= lead:
        status = "CRITICAL"
    elif qty > 0:
        status = "ORDER"
    else:
        status = "OK"
    bridge = float(max(1, ceil(exp_short / pack)) * pack) if status == "CRITICAL" else 0.0
    return {
        "status": status,
        "run_out_day": rod,
        "p_stockout": p_stockout,
        "demand_lead": d_lead,
        "demand_7d": horizon_demand(daily_fc, 7),
        "window": cover,
        "safety_stock": safety,
        "order_up_to": target,
        "order_qty": qty,
        "order_value": qty * float(unit_cost),
        "expected_short": exp_short,
        "margin_at_risk": exp_short * float(unit_margin),
        "bridge_qty": bridge,
        "bridge_value": bridge * float(unit_cost),
    }


STATUS_RANK = {"CRITICAL": 0, "ORDER": 1, "OK": 2}


def rank(rows):
    """Sort assessed products: CRITICAL first, then by ringgit margin at risk, then stockout probability."""
    df = pd.DataFrame(rows)
    df["_r"] = df["status"].map(STATUS_RANK)
    df = df.sort_values(["_r", "margin_at_risk", "p_stockout"], ascending=[True, False, False])
    return df.drop(columns="_r").reset_index(drop=True)


def simulate(actual, forecast, history, sigma_d, lead_time=3, review=7, z=1.645,
             policy="model", start_stock=None):
    """Replay one product day by day over a past window, using historical sales as demand.

    policy="model":    order-up-to level = model forecast over (L + R) + z * sigma_d * sqrt(L + R),
                       where sigma_d is the model's daily error spread from the validation period.
    policy="baseline": order-up-to level = 28-day average sales x (L + R) + z * 28-day sales std * sqrt(L + R).
                       This is the textbook non-ML policy; only the forecast differs between the two.

    Caveat: historical sales were themselves capped by any past stockouts (censored demand).
    """
    actual = np.asarray(actual, dtype=float)
    forecast = np.asarray(forecast, dtype=float)
    hist = list(np.asarray(history, dtype=float))
    lead, rev = max(1, int(lead_time)), max(1, int(review))
    cover = lead + rev
    T = len(actual)
    if start_stock is None:
        start_stock = float(np.mean(hist[-28:])) * cover if hist else 0.0
    on_hand = float(start_stock)
    pipeline = {}
    sold_total = lost_total = 0.0
    stockout_days = 0
    inv = []
    for t in range(T):
        on_hand += pipeline.pop(t, 0.0)
        if t % rev == 0:
            on_order = sum(pipeline.values())
            if policy == "model":
                window = forecast[t:t + min(cover, 7)]
                need = horizon_demand(window, cover)
                spread = sigma_d
            else:
                recent = np.asarray(hist[-28:])
                need = float(recent.mean()) * cover if len(recent) else 0.0
                spread = float(recent.std(ddof=1)) if len(recent) > 1 else 0.0
            target = need + z * spread * sqrt(cover)
            qty = max(0.0, target - on_hand - on_order)
            if qty > 0:
                pipeline[t + lead] = pipeline.get(t + lead, 0.0) + qty
        demand = actual[t]
        sold = min(on_hand, demand)
        lost = demand - sold
        on_hand -= sold
        sold_total += sold
        lost_total += lost
        stockout_days += int(lost > 1e-9)
        inv.append(on_hand)
        hist.append(demand)
    demand_total = float(actual.sum())
    mean_demand = demand_total / T if T else 0.0
    avg_inv = float(np.mean(inv)) if inv else 0.0
    return {
        "demand": demand_total,
        "sold": sold_total,
        "lost": lost_total,
        "stockout_days": stockout_days,
        "avg_inventory": avg_inv,
        "days_of_cover": avg_inv / mean_demand if mean_demand > 0 else np.nan,
        "days": T,
    }


# ---------------------------------------------------------------------------------------------
# LARIS additions: product settings, dead stock (R), budget allocation (I), risk categories and
# priority. All pure functions; costs, margins and shelf lives come from the shop's settings
# (product_settings.csv holds PLACEHOLDER defaults).
# ---------------------------------------------------------------------------------------------
SETTINGS_COLUMNS = ["product", "unit_cost_rm", "margin_rm", "shelf_life_days", "lead_time_days",
                    "review_days", "pack_size", "must_have"]
PERISHABLE_MAX_SHELF = 60    # shelf life (days) at or below this counts as perishable
LONG_LIFE_MAX_COVER = 28     # long-life stock covering more days than this is flagged
GOODWILL_RM = 3.0            # extra shortage cost per unit for must-have items (placeholder)


def load_settings(path="product_settings.csv"):
    """Per-product settings indexed by product. Must contain a DEFAULT row used as fallback."""
    s = pd.read_csv(path, encoding="utf-8")
    missing = [c for c in SETTINGS_COLUMNS if c not in s.columns]
    if missing:
        raise ValueError(f"{path}: missing columns {missing}")
    s["product"] = s["product"].astype(str).str.strip()
    if "DEFAULT" not in set(s["product"]):
        raise ValueError(f"{path}: needs a DEFAULT row")
    for c in ("unit_cost_rm", "margin_rm"):
        s[c] = s[c].astype(float)
    for c in ("shelf_life_days", "lead_time_days", "review_days", "pack_size"):
        s[c] = s[c].astype(int)
    s["must_have"] = s["must_have"].astype(str).str.strip().str.lower().isin(["true", "1", "yes", "y"])
    if "display_name" not in s:
        s["display_name"] = s["product"]
    if "icon" not in s:
        s["icon"] = ""
    s["display_name"] = s["display_name"].fillna(s["product"]).astype(str)
    s["icon"] = s["icon"].fillna("").astype(str)
    return s.set_index("product")


def product_settings(settings, product):
    """Settings for one product, falling back to the DEFAULT row."""
    src = product if product in settings.index else "DEFAULT"
    row = settings.loc[src].to_dict()
    row["product"] = product
    row["settings_source"] = "product" if src == product else "DEFAULT"
    if src == "DEFAULT":
        row["display_name"] = str(product)
    return row


def dead_stock(daily_fc, sigma_d, on_hand, shelf_life_days, unit_cost):
    """Stock that won't sell before it expires (perishables) or ties up cash (long-life).

    Expected units still unsold at expiry = E[(on_hand - D_S)+], D_S = demand over the shelf life
    (normal approximation). Assumes the stock on hand is fresh (stock age isn't known).
    """
    fc = np.asarray(daily_fc, dtype=float)
    mean_d = float(fc.mean()) if len(fc) else 0.0
    shelf = max(1, int(shelf_life_days))
    on_hand = max(0.0, float(on_hand))
    if mean_d > 0:
        cover = on_hand / mean_d
    else:
        cover = float("inf") if on_hand > 0 else 0.0
    mu = horizon_demand(fc, shelf)
    sd = max(float(sigma_d), 1e-9) * sqrt(shelf)
    k = (on_hand - mu) / sd
    left = max(0.0, (on_hand - mu) + sd * _normal_loss(k))
    perishable = shelf <= PERISHABLE_MAX_SHELF
    flag = on_hand > 0 and (cover > shelf if perishable else cover > LONG_LIFE_MAX_COVER)
    if flag and perishable:
        action = "Skip the reorder; move it to the front or discount it"
    elif flag:
        action = f"Skip the reorder; cash tied up for about {cover / 7:.0f} weeks"
    else:
        action = ""
    return {
        "days_of_cover": cover,
        "demand_shelf_life": mu,
        "expected_expire_units": left if perishable else 0.0,
        "expected_expire_rm": (left if perishable else 0.0) * float(unit_cost),
        "perishable": perishable,
        "flag": bool(flag),
        "action": action,
    }


def make_item(product, daily_fc, sigma_d, on_hand, on_order, s, must_have=None, dead=False):
    """Allocator input for one product, using its own protection window and costs."""
    lead, rev, shelf = int(s["lead_time_days"]), int(s["review_days"]), int(s["shelf_life_days"])
    w = protection_window(lead, rev, shelf)
    fc = np.asarray(daily_fc, dtype=float)[:7]
    cost = float(s["unit_cost_rm"])
    return {
        "product": product,
        "mu_window": max(0.0, horizon_demand(fc, w)),
        "sd_window": max(float(sigma_d), 1e-9) * sqrt(w),
        "position": float(on_hand) + float(on_order),
        "unit_cost": cost,
        "margin": float(s["margin_rm"]),
        "overstock_cost": overstock_cost(cost, shelf, w),
        "pack_size": max(1, int(s["pack_size"])),
        "must_have": bool(s["must_have"] if must_have is None else must_have),
        "dead": bool(dead),
        "window": w,
    }


def _pack_values(mu, sd, position, pack, cs, co):
    """Expected value of each successive pack, from the first while it stays positive.

    Value of one unit at stock level y = cs * P(D > y) - co * P(D <= y) (y + 0.5 for continuity).
    These values fall as stock rises, so the positive packs form a prefix.
    """
    if cs <= 0:
        return np.zeros(0)
    y_star = mu + sd * float(norm.ppf(cs / (cs + co)))
    n_units = int(max(0, ceil(y_star - position)) + pack)
    if n_units <= 0:
        return np.zeros(0)
    j = np.arange(1, n_units + 1)
    F = norm.cdf((position + j - 0.5 - mu) / sd)
    unit_v = cs - (cs + co) * F
    n_packs = n_units // pack
    pv = unit_v[:n_packs * pack].reshape(n_packs, pack).sum(axis=1)
    return pv[pv > 0]


def allocate_budget(items, budget=None, goodwill_rm=GOODWILL_RM):
    """Best order list for the cash available (LARIS 'I').

    Greedy by expected value per ringgit, one pack at a time: shortage cost = margin (+ goodwill for
    must-haves), overstock cost per item. Packs that don't fit the remaining budget are skipped
    and cheaper packs of other products are still considered. budget=None gives the unconstrained
    ideal order (the newsvendor critical fractile, in packs).
    Returns (per-product DataFrame, totals dict).
    """
    df = pd.DataFrame(items).reset_index(drop=True)
    n = len(df)
    cs = df["margin"].to_numpy(float) + goodwill_rm * df["must_have"].to_numpy(bool)
    co = df["overstock_cost"].to_numpy(float)
    pack = df["pack_size"].to_numpy(int)
    pack_cost = pack * df["unit_cost"].to_numpy(float)
    dead = df["dead"].to_numpy(bool) if "dead" in df else np.zeros(n, bool)

    vals, prods, ks = [], [], []
    n_ideal = np.zeros(n, int)
    for i in range(n):
        pv = _pack_values(float(df.at[i, "mu_window"]), float(df.at[i, "sd_window"]),
                          float(df.at[i, "position"]), int(pack[i]), float(cs[i]), float(co[i]))
        n_ideal[i] = len(pv)
        if dead[i] or len(pv) == 0:
            continue
        vals.append(pv)
        prods.append(np.full(len(pv), i))
        ks.append(np.arange(len(pv)))
    taken_packs = np.zeros(n, int)
    if vals:
        v = np.concatenate(vals)
        p = np.concatenate(prods)
        k = np.concatenate(ks)
        ratio = v / pack_cost[p]
        order = np.lexsort((k, p, ~df["must_have"].to_numpy(bool)[p], -ratio))
        p = p[order]
        cost = pack_cost[p]
        if budget is None:
            np.add.at(taken_packs, p, 1)
        else:
            remaining = float(budget)
            taken = np.zeros(len(p), bool)
            blocked = np.zeros(n, bool)
            while True:
                alive = np.nonzero(~taken & ~blocked[p])[0]
                if len(alive) == 0:
                    break
                cum = np.cumsum(cost[alive])
                fit = cum <= remaining + 1e-9
                if fit.all():
                    taken[alive] = True
                    remaining -= float(cum[-1])
                    break
                first = int(np.argmin(fit))
                if first > 0:
                    taken[alive[:first]] = True
                    remaining -= float(cum[first - 1])
                blocked[p[alive[first]]] = True
            np.add.at(taken_packs, p[taken], 1)

    qty = taken_packs * pack
    ideal = np.where(dead, 0, n_ideal) * pack
    unit_cost = df["unit_cost"].to_numpy(float)
    y = df["position"].to_numpy(float) + qty
    mu, sd = df["mu_window"].to_numpy(float), df["sd_window"].to_numpy(float)
    kz = (y - mu) / sd
    short = sd * (norm.pdf(kz) - kz * (1 - norm.cdf(kz)))
    left = np.maximum(0.0, (y - mu) + short)
    expires = co >= unit_cost - 1e-9
    reasons = []
    for i in range(n):
        if dead[i]:
            reasons.append("Dead stock: skip reorder")
        elif ideal[i] == 0:
            reasons.append("Enough stock")
        elif qty[i] < ideal[i]:
            reasons.append("Budget: lower value per RM")
        else:
            reasons.append("")
    out = pd.DataFrame({
        "product": df["product"],
        "must_have": df["must_have"].astype(bool),
        "qty": qty.astype(float),
        "ideal_qty": ideal.astype(float),
        "spend_rm": qty * unit_cost,
        "ideal_rm": ideal * unit_cost,
        "exp_short_units": short,
        "exp_leftover_units": left,
        "exp_lost_margin_rm": short * df["margin"].to_numpy(float),
        "exp_waste_rm": np.where(expires, left * unit_cost, 0.0),
        "cut_reason": reasons,
    })
    ideal_rm = float(out["ideal_rm"].sum())
    spent = float(out["spend_rm"].sum())
    budget_rm = ideal_rm if budget is None else float(budget)
    totals = {
        "budget_rm": budget_rm,
        "spent_rm": spent,
        "ideal_rm": ideal_rm,
        "unspent_rm": budget_rm - spent,
        "exp_lost_margin_rm": float(out["exp_lost_margin_rm"].sum()),
        "exp_waste_rm": float(out["exp_waste_rm"].sum()),
        "must_have_short_units": float(out.loc[out["must_have"], "exp_short_units"].sum()),
    }
    return out, totals


# Risk categories (Categorize) and priority tiers (Prioritize). Thresholds are business rules;
# TAU_ACT is a placeholder until it is chosen on the validation period (alert backtest).
TAU_ACT = 0.5
SURGE_RATIO = 1.3
CATEGORIES = {
    "STOCKOUT_IMMINENT": ("Habis sebelum lori sampai", "Runs out before delivery"),
    "EXPIRY_RISK": ("Risiko luput", "Expiry risk"),
    "REORDER_NEEDED": ("Perlu dipesan", "Needs this order"),
    "DEMAND_SURGE": ("Permintaan melonjak", "Demand surge ahead"),
    "SALES_ANOMALY": ("Jualan luar biasa", "Unusual recent sales"),
    "OVERSTOCK": ("Stok berlebihan", "Cash tied up"),
    "LOW_CONFIDENCE": ("Data tidak cukup", "Not enough reliable data"),
    "ROUTINE": ("Pesanan biasa", "Routine"),
}
TIER_RANK = {"Act today": 0, "This order": 1, "Watch": 2, "OK": 3}


def _is_day(x):
    return x is not None and not pd.isna(x)


def risk_flags(row):
    """Every risk category that applies to one assessed product. `row` holds the assess() and
    dead_stock() outputs plus lead_time, demand_last7, and optional anomaly / low_confidence flags."""
    flags = []
    rod, lead = row.get("run_out_day"), int(row.get("lead_time", 1))
    if (_is_day(rod) and rod <= lead) or row.get("p_stockout", 0) >= TAU_ACT:
        flags.append("STOCKOUT_IMMINENT")
    if row.get("dead_flag") and row.get("perishable"):
        flags.append("EXPIRY_RISK")
    if row.get("status") == "ORDER" and "STOCKOUT_IMMINENT" not in flags:
        flags.append("REORDER_NEEDED")
    last7 = float(row.get("demand_last7", 0) or 0)
    if last7 > 0 and row.get("demand_7d", 0) >= SURGE_RATIO * last7:
        flags.append("DEMAND_SURGE")
    if row.get("anomaly"):
        flags.append("SALES_ANOMALY")
    if row.get("dead_flag") and not row.get("perishable"):
        flags.append("OVERSTOCK")
    if row.get("low_confidence"):
        flags.append("LOW_CONFIDENCE")
    return flags or ["ROUTINE"]


def categorize(row):
    """Primary category code and its 'BM / EN' label (precedence = order of CATEGORIES)."""
    flags = risk_flags(row)
    main = [c for c in CATEGORIES if c in flags and c != "LOW_CONFIDENCE"]
    code = main[0] if main else "LOW_CONFIDENCE"
    bm, en = CATEGORIES[code]
    return code, f"{bm} / {en}"


def priority(row, goodwill_rm=GOODWILL_RM, holding_rate=0.02):
    """(tier, RM at risk if nothing is done, act-by day) for one assessed product.

    RM at risk: stockout = expected units short before delivery x (margin + goodwill if must-have);
    reorder or surge = expected units short over the protection window x the same; expiry = expected
    RM expiring; overstock = cash tied up x holding rate. Low-confidence products never reach
    'Act today'.
    """
    code, _ = categorize(row)
    margin = float(row.get("margin", 0)) + (goodwill_rm if row.get("must_have") else 0.0)
    if code == "STOCKOUT_IMMINENT":
        rm, tier = float(row.get("expected_short", 0)) * margin, "Act today"
    elif code == "EXPIRY_RISK":
        rm, tier = float(row.get("expected_expire_rm", 0)), "This order"
    elif code in ("REORDER_NEEDED", "DEMAND_SURGE"):
        rm, tier = float(row.get("window_short", 0)) * margin, "This order"
    elif code == "OVERSTOCK":
        rm, tier = float(row.get("on_hand", 0)) * float(row.get("unit_cost", 0)) * holding_rate, "Watch"
    elif code in ("SALES_ANOMALY", "LOW_CONFIDENCE"):
        rm, tier = float(row.get("expected_short", 0)) * margin, "Watch"
    else:
        rm, tier = 0.0, "OK"
    if row.get("low_confidence") and tier == "Act today":
        tier = "This order"
    rod, lead = row.get("run_out_day"), int(row.get("lead_time", 1))
    act_by = max(0, int(rod) - lead) if _is_day(rod) else None
    return tier, rm, act_by
