"""Checks for the pipeline's evaluation helpers (no model training needed)."""
import numpy as np
import pandas as pd

from pipeline import bootstrap_wape_diff, lead_time_ratios, suspect_zero_runs


def test_suspect_zero_runs_flags_long_runs_in_busy_series_only():
    dates = pd.date_range("2017-01-01", periods=30)
    busy = np.full(30, 20.0)
    busy[10:16] = 0          # 6-day zero run in a busy series -> flagged
    busy[20:22] = 0          # 2-day run -> not flagged
    quiet = np.zeros(30)     # a quiet series (median 0) is never flagged
    S = pd.DataFrame({"1|A": busy, "1|B": quiet}, index=dates)
    m = suspect_zero_runs(S)
    assert m[10:16, 0].all() and not m[20:22, 0].any()
    assert not m[:, 1].any()


def test_bootstrap_diff_negative_when_a_is_better():
    idx = pd.MultiIndex.from_product([[f"s{i}" for i in range(20)], range(3)], names=["sid", "week"])
    rng = np.random.default_rng(1)
    y = rng.uniform(50, 100, len(idx))
    wk = pd.DataFrame({"y": y, "good": y * 1.02, "bad": y * 1.3}, index=idx)
    out = bootstrap_wape_diff(wk, "good", "bad", n_boot=200)
    assert out["diff"] < 0 and out["ci95"][1] < 0


def test_lead_time_ratios_windows_stay_inside_the_part():
    dates = pd.date_range("2017-01-01", periods=10)
    part = pd.DataFrame({"date": np.tile(dates, 2), "sid": np.repeat(["1|A", "1|B"], 10),
                         "y": 10.0, "pred_model": 8.0, "suspect_zero": False})
    r = lead_time_ratios(part, 3)
    assert len(r) == 2 * 8                      # 8 full 3-day windows per series
    assert np.allclose(r["ratio"], 0.25)
