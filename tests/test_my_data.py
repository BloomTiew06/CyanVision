"""Malaysian data in LARIS: public holidays per state, the current planning week, PriceCatcher prices, and no
development wording on any page."""
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import calendar_my as cal
import laris_core as core
from inventory import load_settings

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs_mock"
needs_outputs = pytest.mark.skipif(not (OUT / "metrics.json").exists(),
                                   reason="run make_mock_data.py and pipeline.py --out outputs_mock first")


def _fc():
    fc = pd.read_parquet(OUT / "forecasts.parquet")
    fc["date"], fc["store"] = pd.to_datetime(fc["date"]), fc["store"].astype(str)
    test = fc[fc["split"] == "test"]
    days = sorted(d for d in test["date"].unique() if d + pd.Timedelta(days=6) <= test["date"].max())
    return fc, pd.Timestamp(days[len(days) // 2])


def test_holidays_follow_the_state():
    sel, sar = cal.load_holidays("Selangor"), cal.load_holidays("Sarawak")
    assert pd.Timestamp("2026-11-08") in set(sel["date"])          # Deepavali: not a holiday in Sarawak
    assert pd.Timestamp("2026-11-08") not in set(sar["date"])
    assert pd.Timestamp("2026-12-11") in set(sel["date"])          # Sultan of Selangor's birthday
    assert pd.Timestamp("2026-06-01") in set(sar["date"])          # Gawai Dayak
    raya = sel[sel["date"] == "2026-03-21"]
    assert len(raya) == 1 and bool(raya["major_festival"].iloc[0])
    assert cal.load_holidays("Selangor", path=ROOT / "missing.csv").empty


@needs_outputs
def test_planning_week_is_the_current_week_and_weekdays_are_kept():
    fc, default = _fc()
    for today in ("2026-10-12", "2026-10-15", "2027-02-01"):
        off = cal.week_offset(default, pd.Timestamp(today))
        assert off % 7 == 0
        as_of = default + pd.Timedelta(days=off)
        assert pd.Timestamp(today) <= as_of <= pd.Timestamp(today) + pd.Timedelta(days=6)
    shifted = cal.apply_calendar(fc, off, cal.load_holidays("Selangor"), as_of)
    assert (shifted["date"].dt.dayofweek.values == fc["date"].dt.dayofweek.values).all()
    assert (shifted["y"].values[:50] == fc["y"].values[:50]).all() or shifted["y"].isna().equals(fc["y"].isna())


@needs_outputs
def test_malaysian_holiday_is_in_the_week_with_the_models_effect():
    fc, default = _fc()
    off = cal.week_offset(default, pd.Timestamp("2026-11-04"))
    as_of = default + pd.Timedelta(days=off)
    shifted = cal.apply_calendar(fc, off, cal.load_holidays("Selangor"), as_of)
    store = sorted(shifted["store"].unique())[0]
    week = core.week_view(shifted, store, as_of)
    assert week["holiday"] and any("Deepavali" in n for n in week["holiday_names"])
    day = shifted[(shifted["date"] == "2026-11-08")]
    assert (day["holiday"] == 1).all()
    diff = (day["pred_model"] - day["pred_no_holiday"]).round(9)   # the model's holiday effect on that day
    assert ((np.sign(diff) == np.sign(day["eff_holiday"].round(9))) | (diff == 0)).all()
    other = shifted[(shifted["date"] == "2026-11-05")]
    assert (other["holiday"] == 0).all() and np.allclose(other["pred_model"], other["pred_no_holiday"])


@needs_outputs
def test_pricecatcher_prices_fill_the_default_products(tmp_path):
    prices = core.load_market_prices("Selangor")
    assert len(prices) == 9 and prices["price_rm"].gt(0).all()
    fc, as_of = _fc()
    store = sorted(fc["store"].unique())[0]
    sig = pd.read_csv(OUT / "sigma.csv", dtype={"store": str}).set_index("sid")
    settings = load_settings(ROOT / "product_settings.csv")
    week = core.week_view(fc, store, as_of)
    inputs, _ = core.default_inputs(week, settings, sig, store, prices=prices)
    eggs = inputs.set_index("product").loc["EGGS"]
    p = float(prices.set_index("family").loc["EGGS", "price_rm"])
    assert "Eggs, grade B" in eggs["Name"]
    assert eggs["Unit cost (RM)"] == pytest.approx(round(p * core.COST_SHARE, 2))
    assert eggs["Unit cost (RM)"] + eggs["Margin (RM)"] == pytest.approx(p)
    bread = inputs.set_index("product").loc["BREAD/BAKERY"]     # no PriceCatcher price: the default stays
    assert bread["Unit cost (RM)"] == core.DEFAULT_PRODUCTS["BREAD/BAKERY"][1]
    assert core.load_market_prices("Selangor", path=tmp_path / "none.csv").empty
    old, _ = core.default_inputs(week, settings, sig, store)           # callers without prices still work
    assert old.set_index("product").loc["EGGS", "Unit cost (RM)"] == core.DEFAULT_PRODUCTS["EGGS"][1]


BANNED = re.compile(r"\b(demo|prototype|hackathon|mock|sample|replay|placeholder|illustrative|pitch)", re.I)


def _visible_text(at):
    parts = []
    for kind in ("markdown", "caption", "title", "header", "subheader", "info", "warning", "error", "success",
                 "toast"):
        parts += [str(getattr(e, "value", "")) for e in getattr(at, kind, [])]
    parts += [str(getattr(e, "label", "")) for kind in ("button", "expander", "selectbox", "text_input", "checkbox",
                                                         "tabs", "radio") for e in getattr(at, kind, [])]
    text = " ".join(parts)
    text = re.sub(r"<(style|script)\b.*?</\1>", " ", text, flags=re.S | re.I)
    return re.sub(r"<[^>]+>", " ", text)


@needs_outputs
@pytest.mark.parametrize("page,tool", [("home.py", None), ("products.py", None), ("orders.py", None),
                                       ("settings.py", None), ("product.py", None)]
                         + [("laris.py", t) for t in "LARIS"])
def test_no_development_wording_on_any_page(page, tool, monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("SHELFSIGNAL_OUT", str(OUT))
    monkeypatch.setenv("LARIS_PAGE", page)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    if tool:
        at.session_state["tool"] = tool
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    found = sorted({m.group(0).lower() for m in BANNED.finditer(_visible_text(at))})
    assert not found, f"{page} {tool or ''}: {found}"
