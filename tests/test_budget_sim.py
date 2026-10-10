"""Tests for the budget replay (budget_sim.py)."""
from pathlib import Path

import numpy as np
import pandas as pd

from budget_sim import LARIS, POLICIES, allocate_fast, replay, simulate_budget
from inventory import allocate_budget, load_settings

ROOT = Path(__file__).resolve().parents[1]


def test_fast_allocator_matches_exact_greedy():
    rng = np.random.default_rng(3)
    for _ in range(100):
        n = int(rng.integers(1, 7))
        mu, sd, pos = rng.uniform(5, 400, n), rng.uniform(1, 60, n), rng.uniform(0, 150, n)
        cost, margin, co = rng.uniform(1, 9, n), rng.uniform(0.2, 3, n), rng.uniform(0.02, 6, n)
        must = rng.random(n) < 0.3
        cs = margin + 3.0 * must
        budget = float(rng.uniform(0, 3000))
        items = [{"product": i, "mu_window": mu[i], "sd_window": sd[i], "position": pos[i], "unit_cost": cost[i],
                  "margin": margin[i], "overstock_cost": co[i], "pack_size": 1, "must_have": bool(must[i])}
                 for i in range(n)]
        exact = allocate_budget(items, budget)[0]["qty"].to_numpy()
        fast = allocate_fast(mu, sd, pos, cost, cs, co, must, budget)
        assert (fast * cost).sum() <= budget + 1e-6
        assert np.abs(fast - exact).max() <= 1
        assert np.array_equal(allocate_fast(mu, sd, pos, cost, cs, co, must),
                              allocate_budget(items, None)[0]["qty"].to_numpy())


def _toy_frame(days=35, test_days=21):
    dates = pd.date_range("2017-01-01", periods=days)
    rng = np.random.default_rng(0)
    rows = []
    for prod, lvl in (("EGGS", 40), ("DAIRY", 25), ("BEVERAGES", 60)):
        y = rng.poisson(lvl, days).astype(float)
        for d, v in zip(dates, y):
            rows.append({"date": d, "store": "1", "product": prod, "y": v, "pred_model": lvl,
                         "pred_naive7": lvl * 1.1, "pred_ma28": lvl * 0.95,
                         "split": "test" if d >= dates[-test_days] else "val"})
    fc = pd.DataFrame(rows)
    sig = pd.DataFrame({"store": "1", "product": ["EGGS", "DAIRY", "BEVERAGES"], "sigma_d": [6.0, 5.0, 8.0]})
    return fc, sig


def test_replay_respects_budget_and_conserves_units():
    fc, sig = _toy_frame()
    df, summary = simulate_budget(fc, sig, load_settings(ROOT / "product_settings.csv"), ["1"])
    base = df[df["scenario"] == "base"]
    assert len(base) == 3 * len(POLICIES)
    assert (df["spent_rm"] <= df["budget_rm"] + 1e-6).all()
    assert np.allclose(df["sold_units"] + df["lost_units"], df["demand_units"])
    full = base[(base["budget_pct"] == 1.0) & (base["policy"] == LARIS)]
    assert full["fill_rate"].iloc[0] > base[(base["budget_pct"] == 0.5) & (base["policy"] == LARIS)]["fill_rate"].iloc[0]
    assert summary["label"].startswith("SIMULATED")
