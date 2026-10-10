"""LARIS demo app.  Run:  streamlit run app.py

Reads precomputed files from ./outputs (made by pipeline.py), so it starts instantly and never retrains or
downloads anything. The planning week is a date inside the held-out test period (a replay, labelled as one).

This file owns the shared state and builds the ONE planning context (laris_core.build_context) every page reads:
products (ss.inputs), planning week, global budget, budget strategy and the owner's order adjustments. Pages live
in views/ and never recompute forecasts or allocations themselves.
"""
import json
import os
from html import escape
from math import ceil
from pathlib import Path

import pandas as pd
import streamlit as st

import laris_core as core
import laris_ui as ui
import planning
import store
from inventory import load_settings

st.set_page_config(page_title="LARIS", page_icon="🛒", layout="wide", initial_sidebar_state="collapsed")
ROOT = Path(__file__).parent
OUT = Path(os.environ.get("SHELFSIGNAL_OUT", ROOT / "outputs"))
st.markdown(ui.CSS, unsafe_allow_html=True)


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


if not (OUT / "metrics.json").exists():
    st.error(f"LARIS can't find its forecast files in {OUT}. Run:  python pipeline.py --data <folder with "
             "train.csv> --out outputs   (or make_mock_data.py first for a quick demo).")
    st.stop()
try:
    metrics, fc, sig, unc = load_outputs(str(OUT), (OUT / "metrics.json").stat().st_mtime)
    settings = load_product_settings(str(ROOT / "product_settings.csv"))
except (OSError, ValueError, KeyError) as e:
    st.error(f"LARIS couldn't read its forecast files in {OUT} ({e}). Rerun pipeline.py to regenerate them.")
    st.stop()
is_mock = "MOCK" in metrics.get("data_source", "")

# path, menu title, icon, eyebrow, headline, subtitle (pages with a headline get the shared header)
PAGES = [
    ("views/home.py", "Home", ":material/home:", "", "", ""),
    ("views/laris.py", "LARIS", ":material/grid_view:", "", "", ""),
    ("views/products.py", "Products", ":material/inventory_2:", "MANAGE", "Products",
     "Your products, stock, prices and recent sales. Edit them, then update the plan."),
    ("views/orders.py", "Orders", ":material/local_shipping:", "MANAGE", "Orders",
     "Check this week's order, share it with your supplier and record what arrives."),
    ("views/settings.py", "Settings", ":material/settings:", "MANAGE", "Settings",
     "Your shop, supplier, alerts, local events, the assistant and the sample data."),
    ("views/product.py", "Product detail", ":material/insights:", "", "", ""),
]
want = os.environ.get("LARIS_PAGE", "")
pages = [st.Page(path, title=title, icon=icon, default=(path.endswith("/" + want) if want else i == 0),
                 visibility="hidden" if path.endswith("/product.py") else "visible")
         for i, (path, title, icon, *_rest) in enumerate(PAGES)]
meta = {p[1]: p for p in PAGES}
st.logo(str(ROOT / "assets" / "laris_logo.svg"), size="large")
pg = st.navigation(pages, position="top")

ss = st.session_state
if ss.get("goto"):
    st.switch_page(ss.pop("goto"))

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
stores = sorted(fc["store"].unique(), key=lambda s: (len(s), s))
test = fc[fc["split"] == "test"]
days = sorted(pd.Timestamp(d) for d in test["date"].unique()
              if pd.Timestamp(d) + pd.Timedelta(days=6) <= test["date"].max())
if ss.get("as_of") not in days:
    ss["as_of"] = days[len(days) // 2]
if ss.get("store") not in stores:
    ss["store"] = stores[0]
ss["_days"], ss["_stores"] = days, stores
store_id, as_of = ss["store"], ss["as_of"]

# Products: load the sample shop for this week, unless the owner has edited their list (then keep it).
key = (store_id, str(as_of))
if ss.get("inputs_key") != key:
    if ss.get("inputs_dirty") and "inputs" in ss:
        ss["flash"] = ss.get("flash", []) + ["You changed the sample week or store; your edited product list was "
                                             "kept. Use Settings › Sample data › Reset to load this week's sample stock."]
    else:
        week0 = core.week_view(fc, store_id, as_of, ss["scale"])
        ss["inputs"], ss["widest"] = core.default_inputs(week0, settings, sig, store_id, ss["preset"])
    ss["order_adj"] = {}
    ss["inputs_key"] = key

build = lambda budget: core.build_context(
    fc, sig, settings, store_id, as_of, ss["inputs"], budget, ss["scale"], ss["service"], unc,
    metrics.get("alert_backtest"), protect_must_have=ss["strategy"] == "essentials", adjust=ss["order_adj"])
if ss["budget_rm"] is None:   # first visit: a round budget that covers the full recommended order
    ss["budget_rm"] = float(ceil(build(None)["ideal_rm"] / 50) * 50)


def _set_budget():
    ss["budget_rm"] = max(0.0, float(ss["budget_w"] or 0))


# ---------------- top bar: shop + planning week | budget ----------------
shop_col, budget_col = st.columns([4, 1.3], vertical_alignment="bottom")
ss["budget_w"] = ss["budget_rm"]
budget_col.number_input("Budget (RM)", min_value=0.0, step=10.0, format="%.0f", key="budget_w", on_change=_set_budget,
                        help="Cash available for this week's order. Every page uses this amount.")
ctx = build(ss["budget_rm"])
ss["ctx"] = {**ctx, "metrics": metrics, "fc": fc, "sig": sig, "settings": settings, "is_mock": is_mock,
             "inputs": ss["inputs"], "ref": planning.order_ref(store_id, as_of), "shop": ss["shop_name"]}
shop_col.markdown(
    f'<div class="lr-shopline"><b>{escape(ss["shop_name"])} · {escape(ss["shop_place"])}</b> '
    f'{ui.label("SAMPLE SHOP", "placeholder")}<br><span>Planning week {as_of:%d %b} – '
    f'{as_of + pd.Timedelta(days=6):%d %b %Y} (replay) · change it in Settings</span></div>', unsafe_allow_html=True)

if is_mock:
    st.error("MOCK DATA: generated for development only. Do not present these numbers.")
for msg in ss.pop("flash", []):
    st.toast(msg)
_, _, _, eyebrow, headline, subtitle = meta[pg.title]
if headline:
    st.markdown(ui.page_header(eyebrow, headline, subtitle), unsafe_allow_html=True)
pg.run()

st.divider()
st.caption("**About these numbers.** Product names, prices, stock and weekly sales are an illustrative sample shop. "
           f"Each product's daily sales pattern and forecast come from a machine-learning model trained on "
           f"{metrics.get('data_source', 'sample data')}, scaled to the shop's weekly sales; this is not Malaysian sales "
           "data and the model has not learned Malaysian paydays, festivals or local events. RM impacts are estimates, "
           "replay comparisons are simulations, and LARIS never sends messages or places orders by itself.")
