"""Checks for the pipeline's evaluation helpers (no model training needed)."""
import numpy as np
import pandas as pd

from pipeline import bootstrap_wape_diff, evaluate_alerts, lead_time_ratios, suspect_zero_runs


def test_evaluate_alerts_picks_threshold_on_validation_and_scores_test():
    rng = np.random.default_rng(0)
    n = 4000
    p = rng.uniform(0, 1, n)
    out = rng.uniform(0, 1, n) < p                     # perfectly calibrated probabilities
    cases = pd.DataFrame({
        "split": np.where(np.arange(n) < n // 2, "val", "test"), "stockout": out,
        "p_normal": p, "p_conformal": np.clip(p + 0.3, 0, 1),   # conformal deliberately miscalibrated
        "exp_short_normal": p, "exp_short_conformal": p, "unit_loss": 1.0, "real_loss_rm": out * 1.0,
        "score_minstock": rng.uniform(0, 2, n), "score_lastweek": rng.uniform(0, 2, n),
        "ma": 1.0, "lw": 1.0, "L": 1, "stock": 1.0})
    res = evaluate_alerts(cases)
    assert res["uncertainty_model"] == "normal"        # lower validation Brier score wins
    assert 0 < res["tau_act"] < 1
    laris = next(v for k, v in res["test"].items() if "best F1" in k)
    rule = next(v for k, v in res["test"].items() if k.startswith("Min-stock"))
    assert laris["precision"] > rule["precision"]      # informative score beats a random rule


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
