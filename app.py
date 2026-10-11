"""LARIS app.  Run:  streamlit run app.py

Reads precomputed files from ./outputs (made by pipeline.py), so it starts instantly and never retrains or
downloads anything. calendar_my moves the forecast weeks onto the current week and applies the Malaysian public
holidays of the shop's state; laris_core.load_market_prices supplies PriceCatcher prices for the default products.

This file owns the shared state and builds the ONE planning context (laris_core.build_context) every page reads:
products (ss.inputs), planning week, global budget, budget strategy and the owner's order adjustments. Pages live
in views/ and never recompute forecasts or allocations themselves.
"""
import json
import os
from math import ceil
from pathlib import Path

import pandas as pd
import streamlit as st

import calendar_my as cal
import laris_core as core
import laris_ui as ui
import planning
import store
from inventory import load_settings

st.set_page_config(page_title="LARIS", page_icon="🛒", layout="wide", initial_sidebar_state="collapsed")
ROOT = Path(__file__).parent
OUT = Path(os.environ.get("SHELFSIGNAL_OUT", ROOT / "outputs"))
ss = st.session_state
ss["theme"] = store.get("prefs", {}).get("theme", "dark")   # light/dark, switched from the top bar
st.markdown(ui.css(), unsafe_allow_html=True)
st.html(ui.theme_script(ss["theme"]), unsafe_allow_javascript=True)


@st.cache_data
def load_outputs(out_dir, stamp=None):
    """stamp = metrics.json modification time, so a pipeline rerun refreshes the cache."""
    out = Path(out_dir)
    metrics = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
    fc = pd.read_parquet(out / "forecasts.parquet")
    fc["date"] = pd.to_datetime(fc["date"])
    fc["store"] = fc["store"].astype(str)
    sig = pd.read_csv(out / "sigma.csv", dtype={"store": str}).set_index("sid")
    unc = pd.read_csv(out / "uncertainty.csv") if (out / "uncertainty.csv").exists() else None
    return metrics, fc, sig, unc


@st.cache_data
def load_product_settings(path):
    return load_settings(path)


@st.cache_data
def malaysian_calendar(out_dir, stamp, offset, state, start):
    """Forecasts moved onto the current weeks with the state's public holidays applied (cached per week and state)."""
    _, fc_raw, _, _ = load_outputs(out_dir, stamp)
    return cal.apply_calendar(fc_raw, offset, cal.load_holidays(state), start)


@st.cache_data
def market_prices(state, stamp):
    return core.load_market_prices(state)


if not (OUT / "metrics.json").exists():
    st.error(f"LARIS can't find its forecast files in {OUT}. Run:  python pipeline.py --data <folder with "
             "train.csv> --out outputs")
    st.stop()
try:
    metrics, fc, sig, unc = load_outputs(str(OUT), (OUT / "metrics.json").stat().st_mtime)
    settings = load_product_settings(str(ROOT / "product_settings.csv"))
except (OSError, ValueError, KeyError) as e:
    st.error(f"LARIS couldn't read its forecast files in {OUT} ({e}). Rerun pipeline.py to regenerate them.")
    st.stop()

# path, menu title, icon, eyebrow, headline, subtitle (pages with a headline get the shared header)
PAGES = [
    ("views/home.py", "Home", ":material/home:", "", "", ""),
    ("views/laris.py", "LARIS", ":material/grid_view:", "", "", ""),
    ("views/products.py", "Products", ":material/inventory_2:", "MANAGE", "Products",
     "Your products, stock, prices and recent sales. Edit them, then update the plan."),
    ("views/orders.py", "Orders", ":material/local_shipping:", "MANAGE", "Orders",
     "Check this week's order, share it with your supplier and record what arrives."),
    ("views/settings.py", "Settings", ":material/settings:", "MANAGE", "Settings",
     "Your shop, supplier, alerts, local events, the assistant and your product list."),
    ("views/product.py", "Product detail", ":material/insights:", "", "", ""),
]
want = os.environ.get("LARIS_PAGE", "")
pages = [st.Page(path, title=title, icon=icon, default=(path.endswith("/" + want) if want else i == 0),
                 visibility="hidden" if path.endswith("/product.py") else "visible")
         for i, (path, title, icon, *_rest) in enumerate(PAGES)]
meta = {p[1]: p for p in PAGES}
st.logo(str(ROOT / "assets" / ("laris_logo_light.svg" if ss["theme"] == "light" else "laris_logo.svg")), size="large")
pg = st.navigation(pages, position="top")

if ss.get("goto"):
    st.switch_page(ss.pop("goto"))
ui.restore_snapshot(core.INPUT_COLUMNS)   # work in progress saved just before a light/dark switch

# ---------------- shared state ----------------
# Shop and owner details live in the saved preferences (Settings edits them), so they survive restarts.
prefs = store.get("prefs", {})
PROFILE = {"shop_name": "Kedai Maju", "shop_place": "Shah Alam", "owner": "Hafiz", "title": "Encik",
           "supplier_name": "", "supplier_phone": ""}
for k, v in PROFILE.items():
    ss[k] = prefs.get(k, v)
for k, v in {"service": 0.95, "scale": 1.0, "preset": "Mixed week", "strategy": "essentials", "order_adj": {},
             "budget_rm": None, "inputs_dirty": False, "tool": "L"}.items():
    ss.setdefault(k, v)
ss["state"] = prefs.get("state", cal.DEFAULT_STATE)
stores = sorted(fc["store"].unique(), key=lambda s: (len(s), s))
test = fc[fc["split"] == "test"]
days = sorted(pd.Timestamp(d) for d in test["date"].unique()
              if pd.Timestamp(d) + pd.Timedelta(days=6) <= test["date"].max())
# The planning week is the current week: the forecast weeks move onto today's dates by whole weeks (weekday
# patterns stay) and the public holidays of the shop's state are applied (calendar_my).
offset = cal.week_offset(days[len(days) // 2], cal.today())
ss["as_of"] = days[len(days) // 2] + pd.Timedelta(days=offset)
fc = malaysian_calendar(str(OUT), (OUT / "metrics.json").stat().st_mtime, offset, ss["state"], ss["as_of"])
if ss.get("store") not in stores:
    ss["store"] = stores[0]
ss["_stores"] = stores
store_id, as_of = ss["store"], ss["as_of"]
prices = market_prices(ss["state"], core.PRICES_CSV.stat().st_mtime if core.PRICES_CSV.exists() else None)

# Products: the default product list for this week, unless the owner has edited their list (then keep it).
key = (store_id, str(as_of), ss["state"])
if ss.get("inputs_key") != key:
    if ss.get("inputs_dirty") and "inputs" in ss:
        ss["flash"] = ss.get("flash", []) + ["A new planning week started; your product list was kept. "
                                             "Settings › Product list restores the default list."]
    else:
        week0 = core.week_view(fc, store_id, as_of, ss["scale"])
        ss["inputs"], ss["widest"] = core.default_inputs(week0, settings, sig, store_id, ss["preset"], prices)
    if ss.get("inputs_key") is not None:   # a different week/store: old order changes no longer apply
        ss["order_adj"] = {}
    ss["inputs_key"] = key

build = lambda budget: core.build_context(
    fc, sig, settings, store_id, as_of, ss["inputs"], budget, ss["scale"], ss["service"], unc,
    metrics.get("alert_backtest"), protect_must_have=ss["strategy"] == "essentials", adjust=ss["order_adj"])
if ss["budget_rm"] is None:   # first visit: a round budget that covers the full recommended order
    ss["budget_rm"] = float(ceil(build(None)["ideal_rm"] / 50) * 50)
ctx = build(ss["budget_rm"])
# plain description of the training data and the price source, for the page footer, Products and Settings
source = metrics.get("data_source", "")
if "FAVORITA" in source.upper():
    source = "daily grocery sales from Corporación Favorita stores, 2013–2017 (public Kaggle dataset)"
elif "STORE ITEM" in source.upper():
    source = "five years of daily store-item sales (public Kaggle dataset)"
else:
    source = "generated daily sales data"
price_info = None
if len(prices):
    p0 = prices.iloc[0]
    price_info = {"n": len(prices), "start": pd.Timestamp(p0["period_start"]), "end": pd.Timestamp(p0["period_end"]),
                  "own_state": int(prices["basis"].str.contains(" in ").sum()), "state": ss["state"]}
ss["ctx"] = {**ctx, "metrics": metrics, "fc": fc, "sig": sig, "settings": settings, "data_source": source,
             "inputs": ss["inputs"], "ref": planning.order_ref(store_id, as_of), "shop": ss["shop_name"],
             "state": ss["state"], "price_info": price_info,
             "upcoming_holidays": cal.upcoming(cal.load_holidays(ss["state"]), as_of, 14)}
ui.topbar(ss["shop_name"], ss["shop_place"])
for msg in ss.pop("flash", []):
    st.toast(msg)
_, _, _, eyebrow, headline, subtitle = meta[pg.title]
if pg.title == "Home":
    pg.run()
else:   # every other page sits on one glass card so its content stands off the background
    with st.container(key="glass_page"):
        if headline:
            st.markdown(ui.page_header(eyebrow, headline, subtitle), unsafe_allow_html=True)
        pg.run()

st.divider()
prices_txt = (f"Market prices: KPDN PriceCatcher, median at small shops ({price_info['start']:%d %b} – "
              f"{price_info['end']:%d %b %Y}; data.gov.my, CC BY 4.0); costs are estimated until you enter your "
              "supplier's price. " if price_info else "")
st.caption(f"**About these numbers.** Forecasts come from a machine-learning model trained on {source}, scaled to "
           f"your recent sales, with the public holidays of {ss['state']}. Seasonal patterns such as Ramadan and "
           f"festive build-up are not learned from Malaysian sales. {prices_txt}Stock, sales and lead times are your "
           "entries. RM impacts are estimates, the savings comparison is a back-test on past sales, and LARIS never "
           "sends messages or places orders by itself.")
