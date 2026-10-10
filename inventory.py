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


def assess(daily_fc, sigma_d, on_hand, on_order=0.0, lead_time=3, review=7,
           service_level=0.95, unit_cost=0.0, unit_margin=0.0, pack_size=1):
    """Risk and reorder recommendation for one product.

    Returns stockout probability before an order placed today can arrive, expected units short,
    the order-up-to quantity for (lead time + review period) at the chosen service level, and a status:
      CRITICAL - stock runs out before an order placed today arrives: expedite, transfer or substitute
      ORDER    - stock + on order is below the order-up-to level: order today
      OK       - no order needed this cycle
    """
    z = float(norm.ppf(service_level))
    lead = max(1, int(lead_time))
    avail = float(on_hand) + float(on_order)
    sigma_d = max(float(sigma_d), 1e-9)

    d_lead = horizon_demand(daily_fc, lead)
    sd_lead = sigma_d * sqrt(lead)
    k = (avail - d_lead) / sd_lead
    p_stockout = float(1 - norm.cdf(k))
    exp_short = float(sd_lead * (norm.pdf(k) - k * (1 - norm.cdf(k))))

    cover = lead + int(review)
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
    return {
        "status": status,
        "run_out_day": rod,
        "p_stockout": p_stockout,
        "demand_lead": d_lead,
        "demand_7d": horizon_demand(daily_fc, 7),
        "safety_stock": safety,
        "order_up_to": target,
        "order_qty": qty,
        "order_value": qty * float(unit_cost),
        "expected_short": exp_short,
        "margin_at_risk": exp_short * float(unit_margin),
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
