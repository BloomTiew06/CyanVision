"""Smoke tests for the LARIS prototype: decision core sanity plus every page renders headlessly."""
import os
from pathlib import Path

import numpy as np
import pytest

from inventory import (allocate_budget, assess, categorize, dead_stock, load_settings, make_item, priority,
                       product_settings)

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = load_settings(ROOT / "product_settings.csv")


def _items(rng, n=4):
    out = []
    for i in range(n):
        s = dict(product_settings(SETTINGS, ["EGGS", "DAIRY", "BEVERAGES", "BREAD/BAKERY"][i % 4]))
        s["pack_size"] = int(rng.choice([1, 6, 12]))
        s["unit_cost_rm"] = float(rng.uniform(1, 10))
        fc = rng.uniform(5, 60, 7)
        out.append(make_item(f"P{i}", fc, rng.uniform(1, 15), rng.uniform(0, 200), 0, s))
    return out


def test_budget_never_exceeded_and_packs_respected():
    rng = np.random.default_rng(0)
    for _ in range(50):
        items = _items(rng)
        budget = float(rng.uniform(0, 3000))
        alloc, tot = allocate_budget(items, budget)
        assert tot["spent_rm"] <= budget + 1e-6
        packs = np.array([it["pack_size"] for it in items])
        assert np.all(alloc["qty"].to_numpy() % packs == 0)
        assert np.all(alloc["qty"] <= alloc["ideal_qty"])


def test_bridge_only_when_critical():
    fc = [20] * 7
    for on_hand in (0, 10, 30, 60, 200):
        r = assess(fc, 5, on_hand, 0, 3, 7, 0.95, 5, 1, 1, 21)
        assert (r["bridge_qty"] > 0) == (r["status"] == "CRITICAL")


def test_dead_stock_flags_slow_not_fast():
    assert dead_stock([20] * 7, 5, 300, 10, 5)["flag"]          # 15 days of cover, 10-day shelf life
    assert not dead_stock([20] * 7, 5, 40, 10, 5)["flag"]       # 2 days of cover


def test_categorize_and_priority():
    row = {**assess([20] * 7, 5, 10, 0, 3, 7, 0.95, 5, 1, 1, 21), "lead_time": 3, "margin": 1.0,
           "must_have": True, "demand_last7": 140}
    code, label = categorize(row)
    tier, rm, act_by = priority(row)
    assert code == "STOCKOUT_IMMINENT" and "Runs out" in label
    assert tier == "Act today" and rm > 0 and act_by == 0
    row["low_confidence"] = True
    assert priority(row)[0] != "Act today"


PAGES = ["dashboard.py", "forecast.py", "alerts.py", "waste.py", "orders.py", "results.py", "settings.py"]


def test_pitch_scenario_and_budget_slider(monkeypatch):
    out = ROOT / "outputs_mock"
    if not (out / "metrics.json").exists():
        pytest.skip("run make_mock_data.py and pipeline.py --out outputs_mock first")
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("SHELFSIGNAL_OUT", str(out))
    monkeypatch.setenv("LARIS_PAGE", "settings.py")
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    at.run()
    at.button[0].click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.session_state["preset"] == "Tight budget"
    spent_tight = at.session_state["ctx"]["totals"]["spent_rm"]
    at.session_state["budget_pct"] = 100
    at.run()
    assert at.session_state["ctx"]["totals"]["spent_rm"] > spent_tight


@pytest.mark.parametrize("page", PAGES)
def test_page_renders(page, monkeypatch):
    out = ROOT / "outputs_mock"
    if not (out / "metrics.json").exists():
        pytest.skip("run make_mock_data.py and pipeline.py --out outputs_mock first")
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("SHELFSIGNAL_OUT", str(out))
    monkeypatch.setenv("LARIS_PAGE", page)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
