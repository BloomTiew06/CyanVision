"""Budget replay: does ordering with LARIS beat usual ordering rules at the same cash budget?

SIMULATED. Replays the held-out test period day by day for a sample of stores, using real sales as
demand. Every policy starts with the same stock, faces the same supplier lead times, shelf lives and
cash budget per order day, and only sees information available at the time (forecasts for t..t+6,
which use sales at least 7 days old, and its own past sales).

Policies, in three families:
  LARIS                     AI forecast + budget optimiser (inventory.allocate_budget logic)
  Forecast value            the same optimiser fed the 'same day last week' or 28-day-average forecast
  Allocation value          AI forecast, but the ideal order is cut pro-rata when cash is short
  Usual practice            'order last week's sales' (pro-rata cut), 'split cash by last month's sales
                            value', 'top up best sellers first' (no forecast; own sales history only)
"""
from collections import defaultdict, deque
from math import sqrt

import numpy as np
import pandas as pd
from scipy.stats import norm

from inventory import (GOODWILL_RM, allocate_budget, horizon_demand, overstock_cost, product_settings,
                       protection_window)

POLICIES = {
    "LARIS (AI forecast + optimiser)": ("forecast", "pred_model", "optimise"),
    "Optimiser + last-week forecast": ("forecast", "pred_naive7", "optimise"),
    "Optimiser + 28-day-average forecast": ("forecast", "pred_ma28", "optimise"),
    "AI forecast + pro-rata cut": ("forecast", "pred_model", "prorata"),
    "Usual: order last week's sales": ("usual", "lastweek", None),
    "Usual: split cash by sales value": ("usual", "split_value", None),
    "Usual: best sellers first": ("usual", "best_sellers", None),
}
LARIS = "LARIS (AI forecast + optimiser)"
USUAL = [p for p in POLICIES if p.startswith("Usual")]
SCENARIOS = {
    "base": {},
    "margins -30%": {"margin_f": 0.7},
    "margins +30%": {"margin_f": 1.3},
    "no must-have goodwill": {"goodwill": 0.0},
    "double must-have goodwill": {"goodwill": 6.0},
    "shelf lives -30%": {"shelf_f": 0.7},
    "shelf lives +30%": {"shelf_f": 1.3},
    "deliveries 1 day late": {"lead_add": 1},
}
ASSUMPTIONS = [
    "Historical sales are used as demand; past stockouts may hide some true demand (censored).",
    "Same starting stock for every policy: 28-day average sales x lead time, assumed fresh.",
    "Each product is ordered on its own review cycle and arrives after its lead time; unmet demand is lost.",
    "Stock is sold oldest first and expires shelf-life days after arrival; expired units are waste at cost.",
    "Cash per order day = a share (50/75/100%) of the order LARIS would place with no cash limit, "
    "computed in a separate reference replay; every policy gets the same cash on the same days.",
    "Costs, margins, shelf lives, lead times, pack sizes and must-have flags are PLACEHOLDER settings.",
    "Decisions use only forecasts for the next 7 days (built from sales at least 7 days old) and the "
    "policy's own past sales.",
]


# ---------------- fast allocator (pack size 1) ----------------
def _units(lam, mu, sd, pos, cost, cs, co):
    """Units with value per RM >= lam: value of unit j = cs - (cs + co) * P(D <= pos + j - 0.5)."""
    num = cs - lam * cost
    a = np.clip(num / (cs + co), 1e-12, 1 - 1e-12)
    j = np.floor(mu + sd * norm.ppf(a) - pos + 0.5)
    return np.where(num > 0, np.maximum(j, 0), 0)


def allocate_fast(mu, sd, pos, cost, cs, co, must, budget=None, protect=True):
    """Same greedy as inventory.allocate_budget for pack size 1, solved with a price threshold
    (bisection) instead of pack by pack, so the replay stays fast at supermarket volumes."""
    mu, sd, pos, cost, cs, co = (np.asarray(x, float) for x in (mu, sd, pos, cost, cs, co))
    must = np.asarray(must, bool)
    sd = np.maximum(sd, 1e-9)
    ideal = _units(1e-12, mu, sd, pos, cost, cs, co)
    if budget is None:
        return ideal
    prot = np.where(np.asarray(must, bool) & protect, np.clip(np.floor(mu - pos + 0.5), 0, ideal), 0)
    budget = float(budget)

    def solve(lo_q, hi_q, cash):
        """All units with value per RM above a threshold, the threshold set so the cash fits."""
        spend = lambda lam: (np.clip(_units(lam, mu, sd, pos, cost, cs, co), lo_q, hi_q) * cost).sum()
        if spend(0.0) <= cash:
            return hi_q.copy()
        lo, hi = 0.0, float(np.max(cs / cost)) + 1.0
        for _ in range(60):
            mid = (lo + hi) / 2
            lo, hi = (lo, mid) if spend(mid) <= cash else (mid, hi)
        q = np.clip(_units(hi, mu, sd, pos, cost, cs, co), lo_q, hi_q)
        # Units at the threshold tie (deep stock that is almost sure to sell has the same value per RM):
        # spend the rest on them in bulk, must-haves first, instead of one unit at a time.
        tied = np.clip(_units(lo, mu, sd, pos, cost, cs, co), lo_q, hi_q) - q
        left = cash - (q * cost).sum()
        for i in sorted(np.nonzero(tied > 0)[0], key=lambda i: (not must[i], i)):
            take = min(tied[i], np.floor(left / cost[i] + 1e-9))
            q[i] += take
            left -= take * cost[i]
        return q

    def fill(q, hi_q, cash):
        """Spend what's left of `cash` on the best next units that still fit (as the pack-by-pack greedy does)."""
        left = cash - (q * cost).sum()
        while True:
            val = (cs - (cs + co) * norm.cdf((pos + q + 0.5 - mu) / sd)) / cost
            ok = (q < hi_q) & (cost <= left + 1e-9) & (val > 0)
            if not ok.any():
                return q
            i = int(np.argmax(np.where(ok, val, -np.inf)))
            q[i] += 1
            left -= cost[i]

    if (prot * cost).sum() >= budget:                # not even the protected units fit
        q = fill(solve(np.zeros_like(ideal), prot, budget), prot, budget)
    else:
        q = solve(prot, ideal, budget)
    return fill(q, ideal, budget)


# ---------------- data preparation ----------------
def pick_stores(fc, k):
    """k stores spread evenly from the smallest to the largest by test-period sales."""
    vol = fc[fc["split"] == "test"].groupby("store")["y"].sum().sort_values()
    if k >= len(vol):
        return list(vol.index)
    pos = np.unique(np.linspace(0, len(vol) - 1, k).round().astype(int))
    return list(vol.index[pos])


def prepare_store(fc, sig, settings, store):
    sub = fc[fc["store"] == store]
    test = sub[sub["split"] == "test"]
    start, end = test["date"].min(), test["date"].max()
    days = pd.date_range(start, end)
    prods = sorted(sub["product"].unique())
    piv = lambda d, col, idx: d.pivot_table(index="date", columns="product", values=col).reindex(
        index=idx, columns=prods)
    y = piv(test, "y", days).fillna(0).to_numpy().T
    fcs = {c: piv(test, c, days).fillna(0).to_numpy().T for c in ("pred_model", "pred_naive7", "pred_ma28")}
    hist_days = pd.date_range(start - pd.Timedelta(days=28), start - pd.Timedelta(days=1))
    hist = piv(sub, "y", hist_days).fillna(0).to_numpy().T
    val = sub[sub["split"] == "val"]
    sigmas = {}
    for c in fcs:
        r = (val["y"] - val[c]).groupby(val["product"]).std(ddof=1).reindex(prods)
        sigmas[c] = np.maximum(r.fillna(r.median() if r.notna().any() else 1.0).to_numpy(), 0.5)
    sid_sig = sig[sig["store"].astype(str) == str(store)].set_index("product")["sigma_d"].reindex(prods)
    sigmas["pred_model"] = np.maximum(sid_sig.fillna(pd.Series(sigmas["pred_model"], index=prods)).to_numpy(), 0.5)
    s = [product_settings(settings, p) for p in prods]
    col = lambda k, f=float: np.array([f(x[k]) for x in s])
    return {"store": store, "products": prods, "y": y, "fc": fcs, "sigma": sigmas, "hist": hist,
            "cost": col("unit_cost_rm"), "margin": col("margin_rm"), "shelf": col("shelf_life_days", int),
            "lead": col("lead_time_days", int), "review": col("review_days", int), "pack": col("pack_size", int),
            "must": col("must_have", bool), "start": str(start.date()), "end": str(end.date())}


# ---------------- replay ----------------
def _round_packs(q, pack):
    return np.floor(np.maximum(q, 0) / pack) * pack


def _cash_split(need, weight, cost, cash):
    """Split cash in proportion to weight, never above need; leftover is re-split (water-filling)."""
    q = np.zeros_like(need)
    active = need > 0
    for _ in range(len(need) + 1):
        if not active.any() or cash <= 1e-9:
            break
        w = np.where(active, np.maximum(weight, 1e-9), 0)
        share = cash * w / w.sum()
        add = np.minimum(share / cost, need - q)
        q += np.where(active, add, 0)
        cash -= (np.where(active, add, 0) * cost).sum()
        active &= q < need - 1e-9
    return q


def replay(st, policy, budgets=None, margin_f=1.0, goodwill=GOODWILL_RM, shelf_f=1.0, lead_add=0):
    """Replay one store under one policy. budgets: {day index: RM} (None = no cash limit).
    Returns (totals dict, {day index: ideal order value}) - the second is used as the cash reference."""
    kind, src, alloc = POLICIES[policy]
    P, T = st["y"].shape
    cost, pack, must = st["cost"], st["pack"], st["must"]
    margin = st["margin"] * margin_f
    shelf = np.maximum(1, np.round(st["shelf"] * shelf_f)).astype(int)
    lead, review = st["lead"], st["review"]
    window = np.array([protection_window(lead[i], review[i], shelf[i]) for i in range(P)])
    co = np.array([overstock_cost(cost[i], shelf[i], window[i]) for i in range(P)])
    cs = margin + goodwill * must
    H = st["hist"].shape[1]
    sold_hist = np.concatenate([st["hist"], np.zeros((P, T))], axis=1)
    start = np.mean(st["hist"], axis=1) * lead
    lots = [deque([[float(start[i]), int(shelf[i])]]) for i in range(P)]
    arrivals = defaultdict(list)
    on_order = np.zeros(P)
    sold = np.zeros(P); lost = np.zeros(P); waste = np.zeros(P); stockout_days = np.zeros(P)
    spent = 0.0
    ideal_value = {}
    for t in range(T):
        for i, q in arrivals.pop(t, []):
            lots[i].append([q, t + int(shelf[i])])
            on_order[i] -= q
        for i in range(P):
            while lots[i] and lots[i][0][1] <= t:
                waste[i] += lots[i].popleft()[0]
        due = np.nonzero(t % review == 0)[0]
        if len(due):
            on_hand = np.array([sum(l[0] for l in lots[i]) for i in due])
            pos = on_hand + on_order[due]
            cash = None if budgets is None else budgets.get(t, 0.0)
            if kind == "forecast":
                f = st["fc"][src][due, t:t + 7]
                mu = np.array([horizon_demand(f[j], window[i]) for j, i in enumerate(due)])
                sd = st["sigma"][src][due] * np.sqrt(window[due])
                if (pack[due] == 1).all():
                    ideal = allocate_fast(mu, sd, pos, cost[due], cs[due], co[due], must[due])
                else:
                    items = [{"product": i, "mu_window": mu[j], "sd_window": sd[j], "position": pos[j],
                              "unit_cost": cost[i], "margin": margin[i] + 0.0, "overstock_cost": co[i],
                              "pack_size": pack[i], "must_have": bool(must[i])} for j, i in enumerate(due)]
                    ideal = allocate_budget(items, None, goodwill)[0]["qty"].to_numpy()
                ideal_value[t] = float((ideal * cost[due]).sum())
                if cash is None or (ideal * cost[due]).sum() <= cash:
                    q = ideal
                elif alloc == "prorata":
                    q = _round_packs(ideal * cash / (ideal * cost[due]).sum(), pack[due])
                elif (pack[due] == 1).all():
                    q = allocate_fast(mu, sd, pos, cost[due], cs[due], co[due], must[due], cash)
                else:
                    q = allocate_budget(items, cash, goodwill)[0]["qty"].to_numpy()
            else:
                past = sold_hist[due, H + t - 28:H + t]
                avg = past.mean(axis=1)
                if src == "lastweek":
                    need = np.array([sold_hist[i, H + t - review[i]:H + t].sum() for i in due])
                    need = np.maximum(need, 0)
                    q = need if cash is None or (need * cost[due]).sum() <= cash else \
                        need * cash / max((need * cost[due]).sum(), 1e-9)
                else:
                    need = np.maximum(avg * (lead[due] + review[due]) - pos, 0)
                    if cash is None or (need * cost[due]).sum() <= cash:
                        q = need
                    elif src == "split_value":
                        q = _cash_split(need, past.sum(axis=1) * (cost[due] + margin[due]), cost[due], cash)
                    else:
                        q, left = np.zeros_like(need), cash
                        for j in np.argsort(-past.sum(axis=1)):
                            q[j] = min(need[j], left / cost[due][j])
                            left -= q[j] * cost[due][j]
                q = _round_packs(q, pack[due])
            if cash is not None:
                assert (q * cost[due]).sum() <= cash + 1e-6, "policy overspent its budget"
            for j, i in enumerate(due):
                if q[j] > 0:
                    arrivals[t + int(lead[i]) + lead_add].append((i, float(q[j])))
                    on_order[i] += q[j]
                    spent += q[j] * cost[i]
        for i in range(P):
            need_d = st["y"][i, t]
            rem = need_d
            while rem > 1e-9 and lots[i]:
                take = min(rem, lots[i][0][0])
                lots[i][0][0] -= take
                rem -= take
                if lots[i][0][0] <= 1e-9:
                    lots[i].popleft()
            sold[i] += need_d - rem
            lost[i] += rem
            stockout_days[i] += rem > 1e-6
            sold_hist[i, H + t] = need_d - rem
    demand = st["y"].sum(axis=1)
    assert np.allclose(sold + lost, demand), "units not conserved"
    ending = np.array([sum(l[0] for l in lots[i]) for i in range(P)])
    totals = {
        "demand_units": float(demand.sum()), "sold_units": float(sold.sum()), "lost_units": float(lost.sum()),
        "fill_rate": float(sold.sum() / max(demand.sum(), 1e-9)),
        "lost_margin_rm": float((lost * margin).sum()), "waste_rm": float((waste * cost).sum()),
        "must_have_short_units": float(lost[must].sum()), "stockout_days": float(stockout_days.sum()),
        "spent_rm": spent, "ending_stock_rm": float((ending * cost).sum()),
    }
    return totals, ideal_value


def simulate_budget(fc, sig, settings, stores, budget_pcts=(0.5, 0.75, 1.0)):
    """Run every policy, budget level and sensitivity scenario. Returns (rows DataFrame, summary dict)."""
    rows = []
    prepared = {s: prepare_store(fc, sig, settings, s) for s in stores}
    for scen, kw in SCENARIOS.items():
        policies = list(POLICIES) if scen == "base" else [LARIS] + USUAL
        pcts = budget_pcts if scen == "base" else (0.75,)
        for s, st in prepared.items():
            _, ref = replay(st, LARIS, None, **kw)
            for pct in pcts:
                budgets = {t: pct * v for t, v in ref.items()}
                for pol in policies:
                    tot, _ = replay(st, pol, budgets, **kw)
                    rows.append({"scenario": scen, "store": str(s), "budget_pct": pct, "policy": pol,
                                 "budget_rm": float(sum(budgets.values())), **tot})
    df = pd.DataFrame(rows)
    df["lost_margin_plus_waste_rm"] = df["lost_margin_rm"] + df["waste_rm"]
    return df, summarise(df, prepared)


def summarise(df, prepared):
    base = df[df["scenario"] == "base"]
    agg = (base.groupby(["budget_pct", "policy"])[["lost_margin_rm", "waste_rm", "lost_margin_plus_waste_rm",
                                                   "must_have_short_units", "stockout_days", "spent_rm",
                                                   "ending_stock_rm", "demand_units", "sold_units"]].sum())
    agg["fill_rate"] = agg["sold_units"] / agg["demand_units"]

    def wins(d, other):
        a = d[d["policy"] == LARIS].set_index("store")["lost_margin_plus_waste_rm"]
        b = d[d["policy"] == other].set_index("store")["lost_margin_plus_waste_rm"]
        return float((a < b).mean())

    win = {f"{int(p * 100)}%": {o: wins(base[base["budget_pct"] == p], o) for o in POLICIES if o != LARIS}
           for p in sorted(base["budget_pct"].unique())}
    sens = {}
    for scen, d in df[df["budget_pct"] == 0.75].groupby("scenario"):
        tot = d.groupby("policy")["lost_margin_plus_waste_rm"].sum()
        sens[scen] = {"laris_lowest_vs_usual": bool(all(tot[LARIS] <= tot[u] for u in USUAL if u in tot)),
                      "win_rate_vs_usual": {u: wins(d, u) for u in USUAL if u in tot.index}}
    first = next(iter(prepared.values()))
    return {
        "label": "SIMULATED: replay of real held-out sales for a sample of stores; not measured savings",
        "stores": [str(s) for s in prepared], "period": [first["start"], first["end"]],
        "assumptions": ASSUMPTIONS,
        "totals_by_budget": {f"{int(p * 100)}%": {pol: {k: float(v) for k, v in r.items()}
                                                  for pol, r in agg.loc[p].iterrows()}
                             for p in sorted(base["budget_pct"].unique())},
        "laris_win_rate_by_store": win,
        "sensitivity_75pct": sens,
        "conclusion_holds_in_all_scenarios": bool(all(v["laris_lowest_vs_usual"] for v in sens.values())),
    }
