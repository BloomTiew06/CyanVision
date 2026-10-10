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


def main():
    a = parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
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
    model = HistGradientBoostingRegressor(
        loss="poisson", max_iter=a.max_iter, learning_rate=0.06, max_leaf_nodes=63,
        min_samples_leaf=40, l2_regularization=1.0, categorical_features=cat_idx or None,
        early_stopping=False, random_state=0)
    print("Training...")
    model.fit(tr[FEATURES], tr["y"])
    long["pred_model"] = np.clip(model.predict(long[FEATURES]), 0, None)
    long["pred_naive7"] = long["lag7"]
    long["pred_ma28"] = long["rm28"]

    te = long[long["split"] == "test"].copy()
    va = long[long["split"] == "val"].copy()
    methods = {"Model (gradient boosting)": "pred_model",
               "Seasonal naive (same day last week)": "pred_naive7",
               "28-day moving average": "pred_ma28"}
    daily = {m: scores(te["y"], te[c].fillna(0)) for m, c in methods.items()}

    te["week"] = (te["date"] - test_start).dt.days // 7
    full_weeks = te.groupby("week")["date"].nunique()
    full_weeks = full_weeks[full_weeks == 7].index
    wk = te[te["week"].isin(full_weeks)].groupby(["sid", "week"])[["y"] + list(methods.values())].sum()
    weekly = {m: scores(wk["y"], wk[c]) for m, c in methods.items()}

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

    # Simulation on the TEST window: same order-up-to rule, only the forecast differs.
    print("Simulating replenishment policies...")
    hist_all = long.set_index(["sid", "date"])["y"]
    sim_rows = []
    for sid, g in te.sort_values("date").groupby("sid"):
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

    keep = long[long["date"] >= test_start - pd.Timedelta(days=a.history_days)]
    keep[["date", "sid", "store", "product", "y", "promo", "holiday", "split",
          "pred_model", "pred_naive7", "pred_ma28"]].to_parquet(out / "forecasts.parquet", index=False)

    metrics = {
        "data_source": source,
        "splits": {"train_end": str(tr["date"].max().date()),
                   "val": [str(val_start.date()), str((test_start - pd.Timedelta(days=1)).date())],
                   "test": [str(test_start.date()), str(end.date())]},
        "n_series": int(long["sid"].nunique()),
        "test_daily": daily,
        "test_weekly_totals": weekly,
        "band_coverage_90": band_coverage_90,
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
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    print("\nHeld-out test accuracy (daily):")
    for mth, s in daily.items():
        print(f"  {mth:<38} WMAPE {s['WMAPE']:.3f}  MAE {s['MAE']:.2f}  bias {s['bias']:+.3f}")
    print("Held-out test accuracy (7-day totals, what ordering depends on):")
    for mth, s in weekly.items():
        print(f"  {mth:<38} WMAPE {s['WMAPE']:.3f}")
    print(f"Uncertainty band check: {band_coverage_90:.1%} of test days fell inside the 90% band "
          "(near 90% = honest band; much lower = band too narrow, raise safety stock)")
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
