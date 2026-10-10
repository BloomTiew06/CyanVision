#!/usr/bin/env python3
"""
MOCK data in the Kaggle Store Sales (Favorita) file format, so the app can be built and
tested before the real download finishes. It writes a marker file, and the pipeline and app
then label every result as MOCK. Never present these numbers.

    python make_mock_data.py            ->  data_mock/train.csv, holidays_events.csv, MOCK marker
"""
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline import DEFAULT_FAMILIES

rng = np.random.default_rng(42)
out = Path("data_mock")
out.mkdir(exist_ok=True)
dates = pd.date_range("2015-01-01", "2017-08-15", freq="D")
dates = dates[~((dates.month == 12) & (dates.day == 25))]  # chain closed on Christmas, like the real data
holidays = pd.to_datetime(["2015-11-02", "2016-11-02", "2016-04-16", "2017-04-14", "2016-12-31", "2017-01-02"])
base = {f: rng.uniform(20, 600) for f in DEFAULT_FAMILIES}
dow_effect = np.array([0.95, 0.9, 0.92, 0.97, 1.05, 1.25, 1.2])

rows = []
for store in (1, 2, 3):
    scale = rng.uniform(0.6, 1.4)
    for fam in DEFAULT_FAMILIES:
        n = len(dates)
        trend = np.linspace(0.9, 1.15, n)
        promo = (rng.random(n) < 0.15).astype(int) * rng.integers(1, 20, n)
        lam = base[fam] * scale * trend * dow_effect[dates.dayofweek]
        lam *= np.where((dates.day == 15) | dates.is_month_end, 1.12, 1.0)
        lam *= np.where(dates.isin(holidays), 1.3, 1.0)
        lam *= 1 + 0.02 * promo
        sales = rng.poisson(lam * rng.lognormal(0, 0.12, n)).astype(float)
        rows.append(pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "store_nbr": store,
                                  "family": fam, "sales": sales, "onpromotion": promo}))
df = pd.concat(rows, ignore_index=True)
df.insert(0, "id", range(len(df)))
df.to_csv(out / "train.csv", index=False)
pd.DataFrame({"date": holidays.strftime("%Y-%m-%d"), "type": "Holiday", "locale": "National",
              "locale_name": "Ecuador", "description": "mock holiday", "transferred": False}) \
    .to_csv(out / "holidays_events.csv", index=False)
(out / "MOCK_DATA_DO_NOT_PRESENT.txt").write_text("Generated mock data. Do not present results from it.\n")
print(f"Wrote {len(df):,} mock rows to {out.resolve()}")
