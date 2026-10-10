"""Unit tests for the LARIS decision layer (inventory.py)."""
from itertools import product as cartesian
from pathlib import Path

import numpy as np
import pytest
from scipy.stats import norm

from inventory import (GOODWILL_RM, _pack_values, allocate_budget, categorize, dead_stock, load_settings,
                       priority, product_settings, protection_window)

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = load_settings(ROOT / "product_settings.csv")
FAMILIES = ["GROCERY I", "BEVERAGES", "DAIRY", "BREAD/BAKERY", "EGGS", "POULTRY", "PRODUCE", "MEATS",
            "FROZEN FOODS", "CLEANING", "PERSONAL CARE", "DELI"]


def item(name, mu=50.0, sd=10.0, position=0.0, cost=5.0, margin=1.25, over=0.1, pack=1, must=False, dead=False):
    return {"product": name, "mu_window": mu, "sd_window": sd, "position": position, "unit_cost": cost,
            "margin": margin, "overstock_cost": over, "pack_size": pack, "must_have": must, "dead": dead}


def total_value(items, qty, goodwill=GOODWILL_RM):
    """Sum of the positive pack values actually bought (the greedy's objective)."""
    v = 0.0
    for it, q in zip(items, qty):
        cs = it["margin"] + goodwill * it["must_have"]
        pv = _pack_values(it["mu_window"], it["sd_window"], it["position"], it["pack_size"], cs, it["overstock_cost"])
        v += pv[:int(q // it["pack_size"])].sum()
    return v


def brute_force(items, budget, goodwill=GOODWILL_RM):
    vals = []
    for it in items:
        cs = it["margin"] + goodwill * it["must_have"]
        vals.append(_pack_values(it["mu_window"], it["sd_window"], it["position"], it["pack_size"], cs,
                                 it["overstock_cost"]))
    best = 0.0
    for counts in cartesian(*[range(len(v) + 1) for v in vals]):
        cost = sum(c * it["pack_size"] * it["unit_cost"] for c, it in zip(counts, items))
        if cost <= budget + 1e-9:
            best = max(best, sum(v[:c].sum() for c, v in zip(counts, vals)))
    return best


# ---------------- settings ----------------
def test_settings_cover_every_default_family_with_placeholder_rules():
    for fam in FAMILIES:
        assert fam in SETTINGS.index
    assert set(SETTINGS.index[SETTINGS["must_have"]]) == {"EGGS", "BREAD/BAKERY", "GROCERY I"}
    ratio = SETTINGS["margin_rm"] / SETTINGS["unit_cost_rm"]
    assert ratio.between(0.2, 0.3).all()
    assert (SETTINGS["pack_size"] >= 1).all()
    assert product_settings(SETTINGS, "ITEM 7")["settings_source"] == "DEFAULT"


def test_protection_window_matches_spec_for_every_placeholder_row():
    for _, s in SETTINGS.iterrows():
        L, R, S = s["lead_time_days"], s["review_days"], s["shelf_life_days"]
        assert protection_window(L, R, S) == min(L + R, S) or S >= L + R


# ---------------- budget allocation ----------------
def test_budget_never_exceeded_200_random_cases():
    rng = np.random.default_rng(42)
    for _ in range(200):
        items = [item(f"P{i}", mu=rng.uniform(5, 300), sd=rng.uniform(1, 40), position=rng.uniform(0, 200),
                      cost=rng.uniform(0.5, 12), margin=rng.uniform(0.2, 3), over=rng.uniform(0.01, 5),
                      pack=int(rng.choice([1, 6, 12, 24])), must=bool(rng.random() < 0.3))
                 for i in range(int(rng.integers(1, 8)))]
        budget = float(rng.uniform(0, 4000))
        alloc, tot = allocate_budget(items, budget)
        assert tot["spent_rm"] <= budget + 1e-6
        assert (alloc["qty"] <= alloc["ideal_qty"]).all()
        for it, q in zip(items, alloc["qty"]):
            assert q % it["pack_size"] == 0


def test_greedy_equals_brute_force_with_equal_pack_costs():
    rng = np.random.default_rng(7)
    for _ in range(25):
        items = [item(f"P{i}", mu=rng.uniform(5, 20), sd=rng.uniform(1, 5), position=rng.uniform(0, 5),
                      cost=2.0, margin=rng.uniform(0.3, 2), over=rng.uniform(0.05, 2), pack=1,
                      must=bool(rng.random() < 0.3)) for i in range(3)]
        budget = float(rng.integers(0, 60))
        alloc, _ = allocate_budget(items, budget, protect_must_have=False)   # pure value maximisation
        assert total_value(items, alloc["qty"]) == pytest.approx(brute_force(items, budget), abs=1e-9)


def test_greedy_within_one_pack_of_brute_force_with_unequal_costs():
    rng = np.random.default_rng(11)
    for _ in range(25):
        items = [item(f"P{i}", mu=rng.uniform(5, 20), sd=rng.uniform(1, 5), position=0.0,
                      cost=float(rng.uniform(1, 6)), margin=rng.uniform(0.3, 2), over=rng.uniform(0.05, 2),
                      pack=int(rng.choice([1, 2, 3]))) for i in range(3)]
        budget = float(rng.uniform(0, 80))
        alloc, _ = allocate_budget(items, budget)
        max_pack = max(_pack_values(it["mu_window"], it["sd_window"], it["position"], it["pack_size"],
                                    it["margin"], it["overstock_cost"]).max(initial=0) for it in items)
        assert total_value(items, alloc["qty"]) >= brute_force(items, budget) - max_pack - 1e-9


def test_must_have_items_are_cut_last():
    """Under a tight budget the must-have item is filled up to its expected demand before the other
    item gets anything; the other item is the one cut."""
    a = item("must", must=True, margin=1.0)
    b = item("normal", must=False, margin=3.0)        # higher margin, so pure value would favour it
    budget = 50 * 5.0                                  # cash for the must-have's expected demand only
    alloc, _ = allocate_budget([a, b], budget)
    assert alloc.loc[0, "qty"] == 50 and alloc.loc[1, "qty"] == 0
    assert alloc.loc[1, "cut_reason"].startswith("Budget")
    pure, _ = allocate_budget([a, b], budget, protect_must_have=False)
    assert pure.loc[1, "qty"] > 0                      # without protection the high-margin item wins cash


def test_no_budget_limit_gives_the_newsvendor_critical_fractile():
    for pack, must in [(1, False), (1, True), (6, False)]:
        it = item("x", mu=120, sd=25, position=30, margin=1.25, over=5.0, pack=pack, must=must)
        alloc, _ = allocate_budget([it], None)
        cs = it["margin"] + GOODWILL_RM * must
        y_star = norm.ppf(cs / (cs + it["overstock_cost"]), it["mu_window"], it["sd_window"])
        assert abs(it["position"] + alloc.loc[0, "qty"] - y_star) <= pack + 0.5


def test_dead_stock_is_never_ordered():
    alloc, _ = allocate_budget([item("d", position=0, dead=True)], 1000)
    assert alloc.loc[0, "qty"] == 0 and alloc.loc[0, "cut_reason"].startswith("Dead stock")


# ---------------- dead stock ----------------
def test_dead_stock_rules():
    assert dead_stock([20] * 7, 5, 300, 10, 5)["flag"]            # 15 days cover vs 10-day shelf life
    assert not dead_stock([20] * 7, 5, 40, 10, 5)["flag"]         # fast seller
    assert dead_stock([10] * 7, 3, 400, 730, 5)["flag"]           # long-life, 40 days of cover
    assert not dead_stock([10] * 7, 3, 200, 730, 5)["flag"]       # long-life, 20 days of cover
    assert dead_stock([20] * 7, 5, 300, 10, 5)["expected_expire_units"] > 0


# ---------------- categories and priority ----------------
def _row(**kw):
    base = {"p_stockout": 0.0, "tau_act": 0.5, "status": "OK", "dead_flag": False, "perishable": True,
            "demand_7d": 100.0, "demand_last7": 100.0, "lead_time": 3, "margin": 1.0, "must_have": False,
            "expected_short": 5.0, "window_short": 8.0, "expected_expire_rm": 40.0, "run_out_day": 2,
            "on_hand": 10.0, "unit_cost": 5.0}
    return {**base, **kw}


@pytest.mark.parametrize("kw, code, tier", [
    ({"p_stockout": 0.9}, "STOCKOUT_IMMINENT", "Act today"),
    ({"dead_flag": True}, "EXPIRY_RISK", "This order"),
    ({"status": "ORDER"}, "REORDER_NEEDED", "This order"),
    ({"demand_7d": 150.0}, "DEMAND_SURGE", "This order"),
    ({"dead_flag": True, "perishable": False}, "OVERSTOCK", "Watch"),
    ({"anomaly": True}, "SALES_ANOMALY", "Watch"),
    ({"low_confidence": True}, "LOW_CONFIDENCE", "Watch"),
    ({}, "ROUTINE", "OK"),
])
def test_categories_and_tiers(kw, code, tier):
    r = _row(**kw)
    assert categorize(r)[0] == code
    assert priority(r)[0] == tier


def test_low_confidence_never_reaches_act_today():
    assert priority(_row(p_stockout=0.99, low_confidence=True))[0] == "This order"


def test_must_have_raises_rm_at_risk():
    assert priority(_row(p_stockout=0.9, must_have=True))[1] > priority(_row(p_stockout=0.9))[1]
