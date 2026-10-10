#!/usr/bin/env python3
"""
ShelfSignal offline pipeline.

Daily store x product sales  ->  7-day demand forecasts, accuracy against simple baselines,
forecast-error spread for safety stock, and a simulated replenishment comparison.
Everything is written to ./outputs so the app only reads files (fast, and the demo can't break).

Supported inputs (auto-detected from train.csv columns):
  - Kaggle "Store Sales - Time Series Forecasting" (Corporacion Favorita, Ecuador):
      train.csv [id, date, store_nbr, family, sales, onpromotion], holidays_events.csv (optional)
  - Kaggle "Store Item Demand Forecasting Challenge" (fallback):
      train.csv [date, store, item, sales]  (no promotions or holidays)

Usage:
  python pipeline.py --data data/store-sales --out outputs
  python pipeline.py --data data/store-sales --stores 1 2 3 --families "EGGS,DAIRY,POULTRY"
  python pipeline.py --data data/store-item --out outputs        (fallback dataset)

Leakage rules this follows:
  - Every feature for day t uses sales up to t-7 or earlier, plus things known in advance
    (calendar, national holidays, planned promotions). So each prediction is a valid
    forecast made up to 7 days ahead, and all 7 days can be forecast at once without recursion.
  - Chronological split: train < validation < test. The model never sees validation or test
    targets; forecast-error spread (sigma) comes from validation only; all reported accuracy
    and the simulation use the test period only.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from inventory import simulate

DEFAULT_FAMILIES = [
    "GROCERY I", "BEVERAGES", "DAIRY", "BREAD/BAKERY", "EGGS", "POULTRY",
    "PRODUCE", "MEATS", "FROZEN FOODS", "CLEANING", "PERSONAL CARE", "DELI",
]
FEATURES = [
    "store_code", "product_code", "dow", "dom", "month", "payday", "holiday",
    "promo", "promo_rm28", "lag7", "lag14", "lag21", "lag28",
    "rm7", "rm28", "dow4", "rstd28", "zero28",
]
Z_GRID = [0.84, 1.28, 1.645, 2.05, 2.33]   # ~80%, 90%, 95%, 98%, 99% cycle service level


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", required=True, help="folder containing train.csv")
    p.add_argument("--out", default="outputs")
    p.add_argument("--stores", type=int, nargs="*", default=None, help="store numbers to keep (default: all)")
    p.add_argument("--families", default=",".join(DEFAULT_FAMILIES),
                   help="comma-separated product families/items to keep ('ALL' for everything)")
    p.add_argument("--test-days", type=int, default=63, help="held-out test window (default 63 = 9 weeks)")
    p.add_argument("--val-days", type=int, default=42, help="validation window before test (default 42)")
    p.add_argument("--lead-time", type=int, default=3, help="supplier lead time for the simulation (days)")
    p.add_argument("--review", type=int, default=7, help="days between orders in the simulation")
    p.add_argument("--max-iter", type=int, default=300, help="boosting iterations")
    p.add_argument("--history-days", type=int, default=56, help="history exported for charts")
    p.add_argument("--settings", default=str(Path(__file__).parent / "product_settings.csv"),
                   help="per-product settings (lead time, shelf life, costs); defaults are placeholders")
    p.add_argument("--sim-stores", type=int, default=10,
                   help="stores in the budget replay, spread from smallest to largest (0 = skip)")
    p.add_argument("--sim-only", action="store_true",
                   help="rerun only the budget replay on existing outputs in --out (no retraining)")
    p.add_argument("--holdout-stores", type=int, default=10,
                   help="stores left out of a second training run and scored on the test period, as a test on "
                        "unseen shops (default 10; capped at a third of the stores; 0 = skip)")
    return p.parse_args()


def load(data_dir, stores, families):
    data_dir = Path(data_dir)
    train_path = data_dir / "train.csv"
    if not train_path.exists():
        sys.exit(f"Not found: {train_path}")
    cols = pd.read_csv(train_path, nrows=0).columns.tolist()
    holidays = set()
    if "family" in cols:  # Favorita
        df = pd.read_csv(train_path, usecols=["date", "store_nbr", "family", "sales", "onpromotion"],
                         parse_dates=["date"])
        df = df.rename(columns={"store_nbr": "store", "family": "product", "onpromotion": "promo"})
        source = "Kaggle Store Sales (Corporacion Favorita, Ecuador): daily sales by store x product family"
        hol_path = data_dir / "holidays_events.csv"
        if hol_path.exists():
            h = pd.read_csv(hol_path, parse_dates=["date"])
            mask = (h["locale"] == "National") & (~h["transferred"].astype(bool)) & (h["type"] != "Work Day")
            holidays = set(h.loc[mask, "date"])
    elif {"date", "store", "item", "sales"}.issubset(cols):  # Store Item Demand fallback
        df = pd.read_csv(train_path, usecols=["date", "store", "item", "sales"], parse_dates=["date"])
        df["product"] = "ITEM " + df["item"].astype(str)
        df = df.drop(columns="item")
        df["promo"] = 0.0
        source = "Kaggle Store Item Demand Forecasting Challenge: daily sales by store x item (no prices or promotions)"
    else:
        sys.exit(f"Unrecognised train.csv columns: {cols}")

    if (data_dir / "MOCK_DATA_DO_NOT_PRESENT.txt").exists():
        source = "MOCK DATA - generated for development only, not real results"

    available = sorted(df["product"].unique())
    if families and families.upper() != "ALL":
        wanted = [f.strip() for f in families.split(",") if f.strip()]
        if "ITEM 1" in available and not any(w in available for w in wanted):
            wanted = available[:12]  # Store Item data: default to the first 12 items
        missing = [w for w in wanted if w not in available]
        if missing:
            print(f"Warning: not in data and skipped: {missing}\nAvailable: {available}")
        df = df[df["product"].isin(wanted)]
    if stores:
        df = df[df["store"].isin(stores)]
    if df.empty:
        sys.exit("No rows left after filtering stores/products.")
    df["sales"] = df["sales"].clip(lower=0)
    return df, holidays, source


def suspect_zero_runs(S, min_run=5, min_median=5.0):
    """Days that are probably not real zero demand: runs of `min_run`+ consecutive zero sales in a
    series whose median daily sales is at least `min_median` (a stockout, a store not yet open, or
    missing data). Returns a boolean date x series array. These rows are kept as model inputs but
    excluded from training targets and from every evaluation."""
    out = np.zeros(S.shape, dtype=bool)
    med = S.median(skipna=True)
    for j, col in enumerate(S.columns):
        if not med[col] >= min_median:
            continue
        z = (S[col] == 0).to_numpy().astype(int)
        d = np.diff(np.concatenate(([0], z, [0])))
        for s, e in zip(np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]):
            if e - s >= min_run:
                out[s:e, j] = True
    return out


def build_long(df, holidays):
    df = df.copy()
    df["sid"] = df["store"].astype(str) + "|" + df["product"]
    S = df.pivot_table(index="date", columns="sid", values="sales", aggfunc="sum")
    P = df.pivot_table(index="date", columns="sid", values="promo", aggfunc="sum")
    full = pd.date_range(S.index.min(), S.index.max(), freq="D")
    S, P = S.reindex(full), P.reindex(full).reindex(columns=S.columns)
    open_day = S.notna().any(axis=1)  # chain-wide closures (e.g. 25 Dec) have no rows at all

    past = S.shift(7)
    feats = {
        "y": S, "promo": P.fillna(0),
        "lag7": S.shift(7), "lag14": S.shift(14), "lag21": S.shift(21), "lag28": S.shift(28),
        "rm7": past.rolling(7, min_periods=4).mean(),
        "rm28": past.rolling(28, min_periods=14).mean(),
        "rstd28": past.rolling(28, min_periods=14).std(),
        "zero28": (past == 0).astype(float).where(past.notna()).rolling(28, min_periods=14).mean(),
        "promo_rm28": P.shift(7).rolling(28, min_periods=14).mean(),
    }
    feats["dow4"] = (S.shift(7) + S.shift(14) + S.shift(21) + S.shift(28)) / 4

    dates, sids = S.index, S.columns
    n_d, n_s = S.shape
    long = pd.DataFrame({"date": np.repeat(dates.values, n_s), "sid": np.tile(sids.values, n_d)})
    for name, W in feats.items():
        long[name] = W.to_numpy(dtype=float).ravel()
    long["suspect_zero"] = suspect_zero_runs(S).ravel()
    long["open"] = np.repeat(open_day.values, n_s)
    parts = long["sid"].str.split("|", n=1, expand=True)
    long["store"], long["product"] = parts[0], parts[1]
    long["store_code"] = long["store"].astype("category").cat.codes
    long["product_code"] = long["product"].astype("category").cat.codes
    d = pd.DatetimeIndex(long["date"])
    long["dow"], long["dom"], long["month"] = d.dayofweek, d.day, d.month
    long["payday"] = ((d.day == 15) | d.is_month_end).astype(int)
    long["holiday"] = d.isin(list(holidays)).astype(int) if holidays else 0
    long = long[long["open"] & long["y"].notna() & long["lag28"].notna()].drop(columns="open")
    return long.reset_index(drop=True)


def wmape(y, p):
    y, p = np.asarray(y, float), np.asarray(p, float)
    return float(np.abs(y - p).sum() / max(y.sum(), 1e-9))


def scores(y, p):
    y, p = np.asarray(y, float), np.asarray(p, float)
    return {"MAE": float(np.abs(y - p).mean()), "WMAPE": wmape(y, p),
            "bias": float((p - y).sum() / max(y.sum(), 1e-9))}


def bootstrap_wape_diff(wk, a, b, n_boot=1000, seed=0):
    """WAPE(a) - WAPE(b) on 7-day totals with a 95% CI from resampling whole series.
    Negative = method a has lower error than method b."""
    per = wk.groupby(level=0).apply(lambda g: pd.Series({
        "y": g["y"].sum(), "ea": (g["y"] - g[a]).abs().sum(), "eb": (g["y"] - g[b]).abs().sum()}))
    y, ea, eb = per["y"].to_numpy(), per["ea"].to_numpy(), per["eb"].to_numpy()
    point = (ea.sum() - eb.sum()) / max(y.sum(), 1e-9)
    idx = np.random.default_rng(seed).integers(0, len(per), (n_boot, len(per)))
    boots = (ea[idx].sum(1) - eb[idx].sum(1)) / np.maximum(y[idx].sum(1), 1e-9)
    return {"diff": float(point), "ci95": [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))]}


QGRID = np.round(np.linspace(0.01, 0.99, 99), 2)


def lead_time_ratios(part, L, pred_col="pred_model"):
    """Relative error of L-day forecast totals, (actual - forecast) / forecast, for every series and
    start day whose whole L-day window lies inside `part` (suspect-zero days excluded)."""
    y = part.assign(y=part["y"].where(~part["suspect_zero"])).pivot(index="date", columns="sid", values="y")
    p = part.pivot(index="date", columns="sid", values=pred_col)
    full = pd.date_range(y.index.min(), y.index.max())
    yL = y.reindex(full).rolling(L, min_periods=L).sum().shift(-(L - 1))
    pL = p.reindex(full).reindex(columns=y.columns).rolling(L, min_periods=L).sum().shift(-(L - 1))
    r = pd.DataFrame({"yL": yL.stack(future_stack=True), "pL": pL.stack(future_stack=True)}).dropna()
    r = r[r["pL"] > 0].reset_index()
    r.columns = ["date", "sid", "yL", "pL"]
    r["ratio"] = (r["yL"] - r["pL"]) / r["pL"]
    r["product"] = r["sid"].str.split("|", n=1).str[1]
    return r


def uncertainty_table(va, horizons=range(1, 8)):
    """Split-conformal error quantiles of L-day totals from the VALIDATION period, per product
    (pooled over stores) and for all products together ('ALL')."""
    rows = []
    for L in horizons:
        r = lead_time_ratios(va, L)
        for prod, g in list(r.groupby("product")) + [("ALL", r)]:
            if len(g) < 20:
                continue
            q = np.quantile(g["ratio"], QGRID)
            rows.append({"product": prod, "L": L, "n": len(g), **{f"q{int(round(x * 100)):02d}": v
                                                                for x, v in zip(QGRID, q)}})
    return pd.DataFrame(rows)


def interval_coverage(te, sig, unc, horizons=(1, 3, 7), levels=(0.5, 0.8, 0.9, 0.95)):
    """Share of TEST L-day totals inside the forecast interval, for the conformal intervals
    (validation quantiles) and the normal sigma*sqrt(L) intervals, plus their mean relative width."""
    from scipy.stats import norm
    out = {"conformal": {}, "normal": {}, "width_conformal": {}, "width_normal": {}}
    for L in horizons:
        r = lead_time_ratios(te, L)
        if r.empty:
            continue
        u = unc[unc["L"] == L].set_index("product")
        s = r["sid"].map(sig["sigma_d"]).to_numpy() * np.sqrt(L)
        for lv in levels:
            lo_c, hi_c = f"q{int(round((1 - lv) / 2 * 100)):02d}", f"q{int(round((1 + lv) / 2 * 100)):02d}"
            prod = r["product"].where(r["product"].isin(u.index), "ALL")
            qlo, qhi = prod.map(u[lo_c]).to_numpy(), prod.map(u[hi_c]).to_numpy()
            inside_c = (r["yL"] >= r["pL"] * (1 + qlo)) & (r["yL"] <= r["pL"] * (1 + qhi))
            z = float(norm.ppf((1 + lv) / 2))
            inside_n = (r["yL"] - r["pL"]).abs() <= z * s
            key = f"L{L}_{int(lv * 100)}"
            out["conformal"][key] = float(inside_c.mean())
            out["normal"][key] = float(inside_n.mean())
            out["width_conformal"][key] = float(np.nanmean((qhi - qlo)))
            out["width_normal"][key] = float(np.nanmean(2 * z * s / r["pL"].to_numpy()))
    return out


STOCK_GRID = (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0)


def _conformal_cdf(x, qvals):
    """P(ratio <= x) from a product's validation quantile grid (QGRID), clipped to the grid's range."""
    return np.interp(x, qvals, QGRID, left=0.005, right=0.995)


def _alert_scores(y, alert):
    y, alert = np.asarray(y, bool), np.asarray(alert, bool)
    tp, fp = int((alert & y).sum()), int((alert & ~y).sum())
    fn, tn = int((~alert & y).sum()), int((~alert & ~y).sum())
    prec = tp / (tp + fp) if tp + fp else float("nan")
    rec = tp / (tp + fn) if tp + fn else float("nan")
    return {"precision": prec, "recall": rec, "false_alarm_rate": fp / (fp + tn) if fp + tn else float("nan"),
            "f1": 2 * prec * rec / (prec + rec) if tp else 0.0, "alerts": tp + fp, "false_alarms": fp,
            "missed": fn, "cases": len(y)}


def alert_cases(long, sig, unc, settings, val_start, test_start, end, grid=STOCK_GRID):
    """Backtest cases for stockout alerts: real future sales, simulated stock levels.

    For every series, start day t and stock level c x (training mean daily sales) x L (L = the
    product's lead time from settings): did actual sales over the next L days exceed the stock?
    Scores known at t: the model's P(stockout) (normal and conformal), a min-stock rule on the
    28-day average up to t-1, and a 'same days last week' rule. Suspect-zero windows are dropped."""
    from scipy.stats import norm
    from inventory import GOODWILL_RM, product_settings
    Y = long.pivot(index="date", columns="sid", values="y")
    full = pd.date_range(Y.index.min(), Y.index.max())
    Y = Y.reindex(full)
    P = long.pivot(index="date", columns="sid", values="pred_model").reindex(full)
    SUS = long.pivot(index="date", columns="sid", values="suspect_zero").reindex(full).fillna(True).astype(float)
    ma28 = Y.shift(1).rolling(28, min_periods=14).mean()
    tmean = long[(long["split"] == "train") & ~long["suspect_zero"]].groupby("sid")["y"].mean()
    prod_of = long.groupby("sid")["product"].first()
    st = {p: product_settings(settings, p) for p in prod_of.unique()}
    lead = prod_of.map(lambda p: int(st[p]["lead_time_days"]))
    out = []
    for L, sids in lead.groupby(lead).groups.items():
        sids = [s for s in sids if s in Y.columns]
        fwd = lambda M: M[sids].rolling(L, min_periods=L).sum().shift(-(L - 1))
        frame = pd.DataFrame({
            "yL": fwd(Y).stack(future_stack=True), "pL": fwd(P).stack(future_stack=True),
            "sus": fwd(SUS).stack(future_stack=True), "lw": fwd(Y.shift(7)).stack(future_stack=True),
            "ma": ma28[sids].stack(future_stack=True)}).reset_index()
        frame.columns = ["date", "sid", "yL", "pL", "sus", "lw", "ma"]
        frame = frame[(frame["sus"] == 0)].dropna(subset=["yL", "pL"])
        last = frame["date"] + pd.Timedelta(days=L - 1)
        frame["split"] = np.where((frame["date"] >= test_start) & (last <= end), "test",
                                  np.where((frame["date"] >= val_start) & (last < test_start), "val", ""))
        frame = frame[frame["split"] != ""]
        frame["L"] = L
        out.append(frame)
    base = pd.concat(out, ignore_index=True)
    base["product"] = base["sid"].map(prod_of)
    base["tmean"] = base["sid"].map(tmean)
    base = base[base["tmean"] > 0]
    cases = pd.concat([base.assign(c=c, stock=c * base["tmean"] * base["L"]) for c in grid], ignore_index=True)
    cases["stockout"] = cases["yL"] > cases["stock"]
    must = cases["product"].map(lambda p: bool(st[p]["must_have"]))
    cases["unit_loss"] = cases["product"].map(lambda p: float(st[p]["margin_rm"])) + GOODWILL_RM * must
    cases["real_loss_rm"] = np.maximum(0, cases["yL"] - cases["stock"]) * cases["unit_loss"]
    # Model probabilities: normal sigma*sqrt(L), and validation-error quantiles (conformal).
    sd = cases["sid"].map(sig["sigma_d"]).to_numpy() * np.sqrt(cases["L"].to_numpy())
    k = (cases["stock"] - cases["pL"]).to_numpy() / sd
    cases["p_normal"] = 1 - norm.cdf(k)
    cases["exp_short_normal"] = sd * (norm.pdf(k) - k * (1 - norm.cdf(k)))
    qcols = [f"q{int(round(x * 100)):02d}" for x in QGRID]
    cases["p_conformal"] = np.nan
    cases["exp_short_conformal"] = np.nan
    for (prod, L), g in cases.groupby(["product", "L"]):
        u = unc[(unc["L"] == L) & (unc["product"] == prod)]
        if u.empty:
            u = unc[(unc["L"] == L) & (unc["product"] == "ALL")]
        if u.empty:
            continue
        q = u[qcols].iloc[0].to_numpy(float)
        x = (g["stock"] / g["pL"] - 1).to_numpy()
        cases.loc[g.index, "p_conformal"] = 1 - _conformal_cdf(x, q)
        dem = g["pL"].to_numpy()[:, None] * (1 + q[None, :])
        cases.loc[g.index, "exp_short_conformal"] = np.maximum(0, dem - g["stock"].to_numpy()[:, None]).mean(1)
    cases["p_conformal"] = cases["p_conformal"].fillna(cases["p_normal"])
    cases["exp_short_conformal"] = cases["exp_short_conformal"].fillna(cases["exp_short_normal"])
    # Rule scores (higher = more alarming) and their usual alert thresholds.
    cases["score_minstock"] = cases["ma"] * cases["L"] / cases["stock"]
    cases["score_lastweek"] = cases["lw"] / cases["stock"]
    return cases


def evaluate_alerts(cases, min_stock_factor=1.2):
    """Choose the uncertainty model and the alert threshold on VALIDATION; report everything on TEST."""
    from sklearn.metrics import average_precision_score
    va, te = cases[cases["split"] == "val"], cases[cases["split"] == "test"]
    brier = {m: float(((va[f"p_{m}"] - va["stockout"]) ** 2).mean()) for m in ("normal", "conformal")}
    chosen = min(brier, key=brier.get)
    pcol = f"p_{chosen}"
    rule_alert = lambda d: (d["score_minstock"] > 1 / min_stock_factor).fillna(False)
    rule_rec_val = _alert_scores(va["stockout"], rule_alert(va))["recall"]
    taus = np.round(np.arange(0.05, 0.96, 0.01), 2)
    val_stats = {t: _alert_scores(va["stockout"], va[pcol] >= t) for t in taus}
    tau_match = max([t for t in taus if val_stats[t]["recall"] >= rule_rec_val] or [taus[0]])
    tau_f1 = max(taus, key=lambda t: val_stats[t]["f1"])
    rows = {
        f"LARIS, threshold {tau_match:.2f} (same recall as min-stock rule on validation)":
            _alert_scores(te["stockout"], te[pcol] >= tau_match),
        f"LARIS, threshold {tau_f1:.2f} (best F1 on validation)": _alert_scores(te["stockout"], te[pcol] >= tau_f1),
        f"Min-stock rule (stock < {min_stock_factor} x 28-day average x lead time)":
            _alert_scores(te["stockout"], rule_alert(te)),
        "Last-week rule (stock < same days last week)":
            _alert_scores(te["stockout"], (te["score_lastweek"] > 1).fillna(False)),
    }
    pr_auc = {"LARIS": float(average_precision_score(te["stockout"], te[pcol])),
              "Min-stock rule": float(average_precision_score(te["stockout"], te["score_minstock"].fillna(0))),
              "Last-week rule": float(average_precision_score(te["stockout"], te["score_lastweek"].fillna(0)))}
    bins = np.linspace(0, 1, 11)
    rel = te.assign(bin=pd.cut(te[pcol], bins, include_lowest=True)).groupby("bin", observed=True).agg(
        predicted=(pcol, "mean"), observed=("stockout", "mean"), cases=("stockout", "size")).reset_index(drop=True)
    # Prioritisation: share of the realised RM loss found in the top 20% of cases by each ranking.
    def capture(score):
        top = te.assign(s=score).sort_values("s", ascending=False).head(max(1, len(te) // 5))
        return float(top["real_loss_rm"].sum() / max(te["real_loss_rm"].sum(), 1e-9))
    rank_capture = {
        "LARIS (expected RM loss)": capture(te[f"exp_short_{chosen}"] * te["unit_loss"]),
        "Min-stock rule (shortfall vs 28-day average)":
            capture((te["ma"] * te["L"] - te["stock"]).clip(lower=0).fillna(0) * te["unit_loss"]),
        "Last-week rule (shortfall vs last week)":
            capture((te["lw"] - te["stock"]).clip(lower=0).fillna(0) * te["unit_loss"]),
    }
    return {
        "label": "MEASURED on real future sales with SIMULATED stock levels (the data has no stock records): "
                 "stock = c x training mean daily sales x lead time, c in " + ", ".join(f"{c:g}" for c in STOCK_GRID),
        "uncertainty_model": chosen, "validation_brier": brier,
        "test_brier": float(((te[pcol] - te["stockout"]) ** 2).mean()),
        "tau_act": float(tau_match), "tau_best_f1": float(tau_f1),
        "test": rows, "test_pr_auc": pr_auc, "test_rm_loss_captured_top20pct": rank_capture,
        "test_cases": int(len(te)), "test_stockout_rate": float(te["stockout"].mean()),
        "reliability": rel.to_dict(orient="records"),
        "notes": ["Thresholds and the uncertainty model were chosen on the validation period only.",
                  "A false alarm = alert where actual sales over the lead time did not exceed the stock.",
                  "Sales stand in for demand; past stockouts in the data may hide some true demand."],
    }


def pick_holdout_stores(tr, k):
    """k stores spread evenly across the range of training sales volume (small to large)."""
    vol = tr.groupby("store")["y"].sum().sort_values()
    k = min(k, len(vol) // 3)
    if k <= 0:
        return []
    pos = np.linspace(0, len(vol) - 1, k + 2)[1:-1].round().astype(int)
    return list(vol.index[np.unique(pos)])


def unseen_store_test(model_params, tr, te, methods, holdout, test_start):
    """Retrain without the holdout stores, then score those stores' test period: the closest proxy we
    have for a shop the model has never seen."""
    from sklearn.ensemble import HistGradientBoostingRegressor
    m2 = HistGradientBoostingRegressor(**model_params)
    fit_rows = tr[~tr["store"].isin(holdout) & ~tr["suspect_zero"]]
    m2.fit(fit_rows[FEATURES], fit_rows["y"])
    t = te[te["store"].isin(holdout)].copy()
    t["pred_unseen"] = np.clip(m2.predict(t[FEATURES]), 0, None)
    cols = {"Model, these stores never seen in training": "pred_unseen", **methods}
    daily = {m: wmape(t["y"], t[c].fillna(0)) for m, c in cols.items()}
    t["week"] = (t["date"] - test_start).dt.days // 7
    fw = t.groupby("week")["date"].nunique()
    wk = t[t["week"].isin(fw[fw == 7].index)].groupby(["sid", "week"])[["y"] + list(cols.values())].sum()
    weekly = {m: wmape(wk["y"], wk[c]) for m, c in cols.items()}
    ci = {m: bootstrap_wape_diff(wk, "pred_unseen", c) for m, c in methods.items() if c != "pred_model"}
    return {
        "label": "MEASURED: a second model trained without these stores, scored on their test period",
        "stores": [str(s) for s in holdout], "n_series": int(t["sid"].nunique()),
        "daily_wape": daily, "weekly_wape": weekly, "unseen_model_vs_baselines_7day_ci": ci,
    }


def run_budget_sim(fc, sig, settings_path, n_stores, out):
    """SIMULATED budget replay (budget_sim.py); writes budget_sim.csv and returns the summary."""
    import time
    from budget_sim import pick_stores, simulate_budget
    from inventory import load_settings
    t0 = time.time()
    stores = pick_stores(fc, n_stores)
    print(f"Budget replay (SIMULATED) on stores {stores}...")
    df, summary = simulate_budget(fc, sig, load_settings(settings_path), stores)
    df.to_csv(out / "budget_sim.csv", index=False)
    summary["runtime_seconds"] = round(time.time() - t0, 1)
    for pct, pols in summary["totals_by_budget"].items():
        print(f"  Budget {pct} of the ideal order (sum over stores; lost margin + waste, RM):")
        for pol, r in pols.items():
            print(f"    {pol:<40} {r['lost_margin_plus_waste_rm']:>14,.0f}   must-have units short "
                  f"{r['must_have_short_units']:>12,.0f}")
    print(f"  Conclusion holds in every sensitivity scenario: {summary['conclusion_holds_in_all_scenarios']} "
          f"({summary['runtime_seconds']} s)")
    return summary


def sim_only(a):
    out = Path(a.out)
    fc = pd.read_parquet(out / "forecasts.parquet")
    fc["date"] = pd.to_datetime(fc["date"])
    fc["store"] = fc["store"].astype(str)
    sig = pd.read_csv(out / "sigma.csv", dtype={"store": str})
    metrics = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
    metrics["budget_simulation"] = run_budget_sim(fc, sig, a.settings, a.sim_stores, out)
    (out / "metrics.json").write_text(
        json.dumps(metrics, indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
        encoding="utf-8")


def main():
    a = parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.sim_only:
        return sim_only(a)
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.inspection import permutation_importance

    print("Loading...")
    df, holidays, source = load(a.data, a.stores, a.families)
    long = build_long(df, holidays)
    end = long["date"].max()
    test_start = end - pd.Timedelta(days=a.test_days - 1)
    val_start = test_start - pd.Timedelta(days=a.val_days)
    long["split"] = np.where(long["date"] >= test_start, "test",
                             np.where(long["date"] >= val_start, "val", "train"))
    tr, va, te = (long[long["split"] == s] for s in ("train", "val", "test"))
    print(f"Series: {long['sid'].nunique()}  rows: train {len(tr):,}  val {len(va):,}  test {len(te):,}")
    print(f"Train to {tr['date'].max().date()}, val {va['date'].min().date()}..{va['date'].max().date()}, "
          f"test {te['date'].min().date()}..{te['date'].max().date()}")

    n_products = long["product_code"].nunique()
    n_stores = long["store_code"].nunique()
    cat_idx = [i for i, f in enumerate(FEATURES)
               if (f == "store_code" and n_stores < 250) or (f == "product_code" and n_products < 250)]
    model_params = dict(
        loss="poisson", max_iter=a.max_iter, learning_rate=0.06, max_leaf_nodes=63,
        min_samples_leaf=40, l2_regularization=1.0, categorical_features=cat_idx or None,
        early_stopping=False, random_state=0)
    model = HistGradientBoostingRegressor(**model_params)
    n_suspect = int(long["suspect_zero"].sum())
    print(f"Suspect zero-sales days (excluded from training targets and evaluation): {n_suspect:,} "
          f"in {long.loc[long['suspect_zero'], 'sid'].nunique()} series")
    print("Training...")
    trf = tr[~tr["suspect_zero"]]
    model.fit(trf[FEATURES], trf["y"])
    long["pred_model"] = np.clip(model.predict(long[FEATURES]), 0, None)
    long["pred_naive7"] = long["lag7"]
    long["pred_ma28"] = long["rm28"]
    long["pred_dow4"] = long["dow4"]

    te_all = long[long["split"] == "test"].copy()
    te = te_all[~te_all["suspect_zero"]].copy()
    va = long[(long["split"] == "val") & ~long["suspect_zero"]].copy()
    methods = {"Model (gradient boosting)": "pred_model",
               "Seasonal naive (same day last week)": "pred_naive7",
               "28-day moving average": "pred_ma28",
               "Same weekday, 4-week mean": "pred_dow4"}
    daily = {m: scores(te["y"], te[c].fillna(0)) for m, c in methods.items()}

    te["week"] = (te["date"] - test_start).dt.days // 7
    full_weeks = te.groupby("week")["date"].nunique()
    full_weeks = full_weeks[full_weeks == 7].index
    wk = te[te["week"].isin(full_weeks)].groupby(["sid", "week"])[["y"] + list(methods.values())].sum()
    weekly = {m: scores(wk["y"], wk[c]) for m, c in methods.items()}
    boot = {m: bootstrap_wape_diff(wk, "pred_model", c) for m, c in methods.items() if c != "pred_model"}

    # Error by volume tier (series split into thirds by mean test sales): where does the model help?
    vol = te.groupby("sid")["y"].mean()
    tier = pd.qcut(vol.rank(method="first"), 3, labels=["low volume", "mid volume", "high volume"])
    te["tier"] = te["sid"].map(tier)
    by_tier = {str(t): {m: wmape(g["y"], g[c].fillna(0)) for m, c in methods.items()}
               for t, g in te.groupby("tier", observed=True)}

    unseen = None
    holdout = pick_holdout_stores(tr, a.holdout_stores)
    if holdout:
        print(f"Unseen-store test: retraining without stores {holdout}...")
        unseen = unseen_store_test(model_params, tr, te, methods, holdout, test_start)

    fam_rows = []
    for prod, g in te.groupby("product"):
        r = {"product": prod, "test_units": float(g["y"].sum())}
        for m, c in methods.items():
            r[f"WMAPE {m}"] = wmape(g["y"], g[c].fillna(0))
        fam_rows.append(r)
    per_product = pd.DataFrame(fam_rows).sort_values("test_units", ascending=False)
    per_product.to_csv(out / "per_product_metrics.csv", index=False)

    # Daily error spread per series, from VALIDATION only (used for safety stock).
    res = (va["y"] - va["pred_model"]).groupby(va["sid"]).std(ddof=1).rename("sigma_d")
    sig = va.groupby("sid").agg(store=("store", "first"), product=("product", "first"),
                                mean_daily_val=("y", "mean")).join(res)
    ratio = (sig["sigma_d"] / sig["mean_daily_val"].replace(0, np.nan)).median()
    sig["sigma_d"] = sig["sigma_d"].fillna(sig["mean_daily_val"] * (ratio if np.isfinite(ratio) else 0.5))
    sig["sigma_d"] = sig["sigma_d"].clip(lower=0.5)
    sig.reset_index().to_csv(out / "sigma.csv", index=False)

    # Is the uncertainty band honest? Share of TEST days whose actual sales fell inside the
    # 90% band (forecast +/- 1.645 x validation sigma). Close to 90% = well calibrated.
    s_te = te["sid"].map(sig["sigma_d"])
    band_coverage_90 = float(((te["y"] - te["pred_model"]).abs() <= 1.645 * s_te).mean())

    # Lead-time uncertainty: error quantiles of L-day totals from VALIDATION (split conformal),
    # checked on TEST against the simpler sigma * sqrt(L) normal band.
    print("Estimating lead-time uncertainty...")
    unc = uncertainty_table(long[long["split"] == "val"])
    unc.to_csv(out / "uncertainty.csv", index=False)
    coverage = interval_coverage(te_all, sig, unc)

    print("Backtesting stockout alerts (real sales, simulated stock levels)...")
    from inventory import load_settings
    cases = alert_cases(long, sig, unc, load_settings(a.settings), val_start, test_start, end)
    alert_bt = evaluate_alerts(cases)
    pd.DataFrame(alert_bt["test"]).T.rename_axis("method").to_csv(out / "alert_eval.csv")

    # Simulation on the TEST window: same order-up-to rule, only the forecast differs.
    print("Simulating replenishment policies...")
    hist_all = long.set_index(["sid", "date"])["y"]
    sim_rows = []
    for sid, g in te_all.sort_values("date").groupby("sid"):
        if g["y"].sum() <= 0 or sid not in sig.index:
            continue
        history = hist_all.loc[sid]
        history = history[history.index < test_start].tail(56).to_numpy()
        for z in Z_GRID:
            for pol in ("baseline", "model"):
                r = simulate(g["y"].to_numpy(), g["pred_model"].to_numpy(), history,
                             sig.loc[sid, "sigma_d"], a.lead_time, a.review, z, pol)
                r.update({"sid": sid, "z": z, "policy": pol})
                sim_rows.append(r)
    sim = pd.DataFrame(sim_rows)
    frontier = (sim.groupby(["policy", "z"])
                   .agg(demand=("demand", "sum"), sold=("sold", "sum"), lost=("lost", "sum"),
                        stockout_days=("stockout_days", "sum"), days_of_cover=("days_of_cover", "median"))
                   .reset_index())
    frontier["fill_rate"] = frontier["sold"] / frontier["demand"]
    frontier.to_csv(out / "sim_frontier.csv", index=False)

    # Fair comparison: stock each policy needs to reach the SAME fill rate (not the same z,
    # because the two policies estimate uncertainty differently).
    headline = None
    b = frontier[frontier["policy"] == "baseline"].sort_values("fill_rate")
    m = frontier[frontier["policy"] == "model"].sort_values("fill_rate")
    lo = max(b["fill_rate"].min(), m["fill_rate"].min())
    hi = min(b["fill_rate"].max(), m["fill_rate"].max())
    if lo <= hi:
        target = float(np.clip(b.loc[np.isclose(b["z"], 1.645), "fill_rate"].iloc[0], lo, hi))
        cover_b = float(np.interp(target, b["fill_rate"], b["days_of_cover"]))
        cover_m = float(np.interp(target, m["fill_rate"], m["days_of_cover"]))
        headline = {
            "matched_fill_rate": target,
            "baseline_days_of_cover": cover_b,
            "model_days_of_cover": cover_m,
            "stock_change_pct": float(cover_m / cover_b - 1),
        }

    sample = va.sample(min(20000, len(va)), random_state=0)
    imp = permutation_importance(model, sample[FEATURES], sample["y"], n_repeats=3,
                                 random_state=0, scoring="neg_mean_absolute_error")
    pd.DataFrame({"feature": FEATURES, "importance": imp.importances_mean}) \
        .sort_values("importance", ascending=False).to_csv(out / "importance.csv", index=False)

    # Model what-if driver effects for the explanation cards: the same model, re-run with one known
    # driver switched off. pred_model - pred_no_X = what the model attributes to X on that day.
    keep = long[long["date"] >= test_start - pd.Timedelta(days=a.history_days)].copy()
    for name in ("promo", "holiday", "payday"):
        X = keep[FEATURES].copy()
        X[name] = 0
        keep[f"pred_no_{name}"] = np.clip(model.predict(X), 0, None)
    keep[["date", "sid", "store", "product", "y", "promo", "holiday", "payday", "split", "suspect_zero",
          "pred_model", "pred_naive7", "pred_ma28", "pred_dow4", "pred_no_promo", "pred_no_holiday",
          "pred_no_payday"]].to_parquet(out / "forecasts.parquet", index=False)

    metrics = {
        "data_source": source,
        "splits": {"train_end": str(tr["date"].max().date()),
                   "val": [str(val_start.date()), str((test_start - pd.Timedelta(days=1)).date())],
                   "test": [str(test_start.date()), str(end.date())]},
        "n_series": int(long["sid"].nunique()),
        "test_daily": daily,
        "test_weekly_totals": weekly,
        "model_vs_baselines_7day_ci": {
            "label": "MEASURED: WAPE(model) - WAPE(baseline) on 7-day totals, 95% CI from resampling series; "
                     "negative = model more accurate",
            **boot},
        "test_by_volume_tier": by_tier,
        **({"unseen_stores": unseen} if unseen else {}),
        "alert_backtest": alert_bt,
        **({"budget_simulation": run_budget_sim(keep, sig.reset_index(), a.settings, a.sim_stores, out)}
           if a.sim_stores > 0 else {}),
        "band_coverage_90": band_coverage_90,
        "lead_time_interval_coverage": {
            "label": "MEASURED on the test period: share of actual L-day sales inside the forecast interval "
                     "(key L{days}_{level}); conformal = validation error quantiles, normal = sigma*sqrt(L)",
            **coverage},
        "data_quality": {
            "suspect_zero_days": n_suspect,
            "series_with_suspect_zeros": int(long.loc[long["suspect_zero"], "sid"].nunique()),
            "rule": "5+ consecutive zero-sales days in a series whose median is >= 5 per day "
                    "(possible stockout, closure or missing data); excluded from training targets and evaluation",
        },
        "simulation": {
            "label": "SIMULATED on historical test-period sales; not measured savings",
            "lead_time_days": a.lead_time, "review_days": a.review,
            "headline_matched_fill_rate": headline,
            "assumptions": [
                "Historical sales are used as demand; past stockouts mean true demand may be higher (censored).",
                "Fixed lead time; orders arrive at the start of day t + lead time.",
                "Weekly ordering; no minimum order quantities, pack sizes or shelf-life limits.",
                "Both policies use the same order-up-to rule; only the demand forecast and its error spread differ.",
            ],
        },
    }
    (out / "metrics.json").write_text(
        json.dumps(metrics, indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
        encoding="utf-8")

    print("\nHeld-out test accuracy (daily):")
    for mth, s in daily.items():
        print(f"  {mth:<38} WMAPE {s['WMAPE']:.3f}  MAE {s['MAE']:.2f}  bias {s['bias']:+.3f}")
    print("Held-out test accuracy (7-day totals, what ordering depends on):")
    for mth, s in weekly.items():
        print(f"  {mth:<38} WMAPE {s['WMAPE']:.3f}")
    print("Model minus baseline, 7-day WMAPE (95% CI; negative = model better):")
    for mth, bt in boot.items():
        print(f"  vs {mth:<35} {bt['diff']:+.3f}  [{bt['ci95'][0]:+.3f}, {bt['ci95'][1]:+.3f}]")
    if unseen:
        print(f"Unseen stores {unseen['stores']} (model retrained without them), 7-day WMAPE:")
        for mth, v in unseen["weekly_wape"].items():
            print(f"  {mth:<45} {v:.3f}")
    print(f"Uncertainty band check: {band_coverage_90:.1%} of test days fell inside the 90% band "
          "(near 90% = honest band; much lower = band too narrow, raise safety stock)")
    for L in (1, 3, 7):
        k = f"L{L}_90"
        if k in coverage["conformal"]:
            print(f"  {L}-day totals inside the 90% interval: conformal {coverage['conformal'][k]:.1%}, "
                  f"normal {coverage['normal'][k]:.1%}")
    print(f"Stockout alert backtest on test ({alert_bt['test_cases']:,} cases, real sales, simulated stock; "
          f"uncertainty model chosen on validation: {alert_bt['uncertainty_model']}):")
    for mth, s in alert_bt["test"].items():
        print(f"  {mth[:62]:<62} precision {s['precision']:.2f}  recall {s['recall']:.2f}  "
              f"false-alarm rate {s['false_alarm_rate']:.3f}")
    if headline:
        chg = headline["stock_change_pct"]
        print(f"\nSIMULATED: to reach the same {headline['matched_fill_rate']:.1%} fill rate, the model policy holds "
              f"{headline['model_days_of_cover']:.2f} days of stock vs {headline['baseline_days_of_cover']:.2f} "
              f"for the baseline ({abs(chg):.0%} {'less' if chg < 0 else 'more'}).")
    else:
        print("\nSIMULATED: the two policies' fill rates don't overlap; compare the frontier chart instead.")
    print(f"\nData source: {source}")
    print(f"Wrote outputs to {out.resolve()}")


if __name__ == "__main__":
    main()
