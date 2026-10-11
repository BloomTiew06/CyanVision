#!/usr/bin/env python
"""Malaysian retail prices from PriceCatcher -> data_my/pricecatcher_prices.csv

PriceCatcher (KPDN and DOSM, https://data.gov.my/data-catalogue/pricecatcher, CC BY 4.0) records daily item prices
at individual premises across Malaysia. This script downloads the item and premise lookups and the latest two
monthly files into data/pricecatcher/ (git-ignored), keeps small shops (kedai runcit, pasar mini, kedai serbaneka)
and writes the median price of each item in data_my/pricecatcher_map.csv for every state over the latest 30 days.

Fallback when a state has fewer than MIN_OBS observations: small shops nationwide, then all premise types
nationwide. The 'basis' column says which one was used.

Run:  python make_my_prices.py            (downloads only files it doesn't have yet)
      python make_my_prices.py --refresh  (downloads the latest months again)
"""
import argparse
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
RAW = ROOT / "data" / "pricecatcher"
BASE = "https://storage.data.gov.my/pricecatcher/"
SMALL_SHOPS = ["Kedai Runcit", "Pasar Mini", "Kedai Serbaneka"]
MIN_OBS = 10
WINDOW_DAYS = 30
STATE_NAMES = {"W.P. Kuala Lumpur": "Kuala Lumpur", "W.P. Labuan": "Labuan", "W.P. Putrajaya": "Putrajaya"}


def fetch(name, refresh=False):
    path = RAW / name
    if path.exists() and not refresh:
        return path
    RAW.mkdir(parents=True, exist_ok=True)
    try:
        urllib.request.urlretrieve(BASE + name, path)
    except Exception:
        path.unlink(missing_ok=True)
        return None
    return path


def latest_months(refresh, n=2):
    """The newest n monthly files that exist, looking back from this month."""
    month, found = pd.Timestamp.today().to_period("M"), []
    for _ in range(6):
        p = fetch(f"pricecatcher_{month}.parquet", refresh)
        if p is not None:
            found.append(p)
            if len(found) == n:
                break
        month -= 1
    if not found:
        raise SystemExit("No PriceCatcher monthly file could be downloaded.")
    return found


def build(refresh=False):
    items = pd.read_parquet(fetch("lookup_item.parquet", refresh))
    premises = pd.read_parquet(fetch("lookup_premise.parquet", refresh))
    prices = pd.concat([pd.read_parquet(p) for p in latest_months(refresh)], ignore_index=True)
    prices["date"] = pd.to_datetime(prices["date"])
    end = prices["date"].max()
    prices = prices[prices["date"] > end - pd.Timedelta(days=WINDOW_DAYS)]

    wanted = pd.read_csv(ROOT / "data_my" / "pricecatcher_map.csv")
    prices = prices[prices["item_code"].isin(wanted["item_code"])].merge(
        premises[["premise_code", "premise_type", "state"]], on="premise_code")
    prices["state"] = prices["state"].replace(STATE_NAMES)
    small = prices[prices["premise_type"].isin(SMALL_SHOPS)]

    rows = []
    for _, w in wanted.iterrows():
        code = w["item_code"]
        info = items.loc[items["item_code"] == code].iloc[0]
        s_item, a_item = small[small["item_code"] == code], prices[prices["item_code"] == code]
        for state in sorted(premises["state"].dropna().replace(STATE_NAMES).unique()):
            s_state = s_item[s_item["state"] == state]["price"]
            if len(s_state) >= MIN_OBS:
                obs, basis = s_state, f"small shops in {state}"
            elif len(s_item) >= MIN_OBS:
                obs, basis = s_item["price"], "small shops, Malaysia"
            else:
                obs, basis = a_item["price"], "all premise types, Malaysia"
            rows.append({"family": w["family"], "item_code": int(code), "item": info["item"], "unit": info["unit"],
                         "display_name": w["display_name"], "state": state,
                         "price_rm": round(float(obs.median()), 2) if len(obs) else None, "n_obs": int(len(obs)),
                         "basis": basis, "period_start": f"{prices['date'].min():%Y-%m-%d}",
                         "period_end": f"{end:%Y-%m-%d}"})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refresh", action="store_true", help="download the latest files again")
    df = build(ap.parse_args().refresh)
    out = ROOT / "data_my" / "pricecatcher_prices.csv"
    df.to_csv(out, index=False)
    print(f"Wrote {out} ({len(df)} rows, {df['family'].nunique()} items x {df['state'].nunique()} states, "
          f"{df['period_start'].iloc[0]} to {df['period_end'].iloc[0]})")
    print(df["basis"].str.replace(r" in .*", " in own state", regex=True).value_counts().to_string())
    print(df[df["state"] == "Selangor"][["display_name", "price_rm", "n_obs", "basis"]].to_string(index=False))
