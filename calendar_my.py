"""Malaysian calendar for the forecasts: public holidays per state, paydays, and the current planning week.

The model is trained on daily grocery sales from Corporacion Favorita (2013-2017). forecasts.parquet holds a
calendar-neutral forecast (pred_base) plus the model's own holiday and payday effects (eff_holiday, eff_payday), so
the app can move the forecast weeks onto today's dates (whole weeks, so weekday patterns stay) and apply the
holidays of the shop's state from data_my/malaysia_public_holidays.csv. No Streamlit imports, so it is testable.
"""
import os
from datetime import datetime
from math import ceil
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

HOLIDAYS_CSV = Path(__file__).parent / "data_my" / "malaysia_public_holidays.csv"
STATES = ["Johor", "Kedah", "Kelantan", "Kuala Lumpur", "Labuan", "Melaka", "Negeri Sembilan", "Pahang", "Perak",
          "Perlis", "Pulau Pinang", "Putrajaya", "Sabah", "Sarawak", "Selangor", "Terengganu"]
DEFAULT_STATE = "Selangor"
EFFECT_COLUMNS = {"pred_base", "eff_holiday", "eff_payday"}


def today(tz="Asia/Kuala_Lumpur"):
    """Today's date in Malaysia; LARIS_TODAY=YYYY-MM-DD overrides it (tests, fixed screenshots)."""
    if os.environ.get("LARIS_TODAY"):
        return pd.Timestamp(os.environ["LARIS_TODAY"]).normalize()
    return pd.Timestamp(datetime.now(ZoneInfo(tz)).date())


def load_holidays(state, path=HOLIDAYS_CSV):
    """One row per holiday date in `state`: date, name (names joined when two fall on one day), major_festival."""
    if not Path(path).exists():
        return pd.DataFrame(columns=["date", "name", "major_festival"])
    h = pd.read_csv(path, parse_dates=["date"])
    h = h[h["locale_name"] == state]
    return (h.groupby("date").agg(name=("description", " / ".join), major_festival=("major_festival", "max"))
            .reset_index().sort_values("date").reset_index(drop=True))


def week_offset(default_as_of, now):
    """Days (a multiple of 7) that move `default_as_of` to the first day on or after `now` with the same weekday."""
    return 7 * ceil((pd.Timestamp(now) - pd.Timestamp(default_as_of)).days / 7)


def is_payday(dates):
    """Mid-month and month-end paydays, the same rule the model was trained with."""
    d = pd.DatetimeIndex(dates)
    return ((d.day == 15) | d.is_month_end).astype(int)


def apply_calendar(fc, offset_days, holidays, start):
    """Shift every date by `offset_days` and, from `start` (a shifted date) on, rebuild the forecast with the
    Malaysian holiday dates in `holidays` and the payday rule. pred_no_* columns are rebuilt to match, so the
    what-if effects on screen are the model's holiday, payday and promotion effects on these dates.
    Forecast files without the effect columns get the holiday flags and no holiday or payday effect."""
    out = fc.copy()
    out["date"] = out["date"] + pd.Timedelta(days=int(offset_days))
    names = dict(zip(pd.to_datetime(holidays["date"]), holidays["name"])) if len(holidays) else {}
    out["holiday_name"] = out["date"].map(names).fillna("")
    ahead = out["date"] >= pd.Timestamp(start)
    f = out.loc[ahead]
    hol = (f["holiday_name"] != "").astype(int)
    pay = pd.Series(is_payday(f["date"]), index=f.index)
    out.loc[ahead, "holiday"], out.loc[ahead, "payday"] = hol, pay
    if EFFECT_COLUMNS <= set(out.columns):
        promo_eff = f["pred_model"] - f["pred_no_promo"]
        base, eh, ep = f["pred_base"], f["eff_holiday"], f["eff_payday"]
        clip = lambda s: np.clip(s, 0, None)
        out.loc[ahead, "pred_model"] = clip(base + eh * hol + ep * pay + promo_eff)
        out.loc[ahead, "pred_no_holiday"] = clip(base + ep * pay + promo_eff)
        out.loc[ahead, "pred_no_payday"] = clip(base + eh * hol + promo_eff)
        out.loc[ahead, "pred_no_promo"] = clip(base + eh * hol + ep * pay)
    else:
        for name in ("holiday", "payday"):
            if f"pred_no_{name}" in out:
                out.loc[ahead, f"pred_no_{name}"] = out.loc[ahead, "pred_model"]
    return out


def upcoming(holidays, start, days=14):
    """Holidays from `start` for `days` days, as a DataFrame (date, name, major_festival)."""
    if not len(holidays):
        return holidays
    start = pd.Timestamp(start)
    return holidays[(holidays["date"] >= start) & (holidays["date"] < start + pd.Timedelta(days=days))]
