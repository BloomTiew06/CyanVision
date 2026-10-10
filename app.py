"""LARIS: inventory intelligence for minimarts.  Run:  streamlit run app.py

Reads precomputed files from ./outputs (made by pipeline.py), so it starts instantly and never retrains or
downloads anything. The planning week is a date inside the held-out test period of the imported sales history.

This file owns the shared state and builds the ONE planning context (laris_core.build_context) every page reads:
products (ss.inputs), planning week, global budget, budget strategy and the owner's order adjustments. Pages live
in views/ and never recompute forecasts or allocations themselves.
"""
import inspect
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

st.set_page_config(page_title="LARIS · Inventory intelligence", page_icon=str(Path(__file__).parent / "assets" / "laris_logo.svg"),
                   layout="wide", initial_sidebar_state="collapsed")
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


@st.cache_data
def default_week(_fc, _settings, stamp=None):
    """The default planning week, chosen by a stated rule (laris_core.demo_week): the median-volume store and the Wednesday
    with the largest predicted rise in must-have demand. stamp = metrics.json time, so a rerun of the pipeline refreshes it."""
    store_id, day, _ = core.demo_week(_fc, _settings)
    return str(store_id), (pd.Timestamp(day) if day is not None else None)


if not (OUT / "metrics.json").exists():
    st.error(f"LARIS can't find its forecast files in {OUT}. Run:  python pipeline.py --data <folder with "
             "train.csv> --out outputs.")
    st.stop()
try:
    metrics, fc, sig, unc = load_outputs(str(OUT), (OUT / "metrics.json").stat().st_mtime)
    settings = load_product_settings(str(ROOT / "product_settings.csv"))
except (OSError, ValueError, KeyError) as e:
    st.error(f"LARIS couldn't read its forecast files in {OUT} ({e}). Rerun pipeline.py to regenerate them.")
    st.stop()
is_dev_data = "MOCK" in metrics.get("data_source", "")

# path, menu title, icon, eyebrow, headline, subtitle (pages with a headline get the shared header)
PAGES = [
    ("views/home.py", "Home", ":material/home:", "", "", ""),
    ("views/laris.py", "LARIS", ":material/grid_view:", "", "", ""),
    ("views/products.py", "Products", ":material/inventory_2:", "MANAGE", "Products",
     "Your catalogue, stock levels and prices. Find a product, edit it, or record a stock count."),
    ("views/proof.py", "Proof", ":material/verified:", "MODEL PERFORMANCE", "How well LARIS works",
     "How accurate the forecast is, how good the alerts are, and whether ordering this way loses less, measured on "
     "weeks the model had not seen."),
    ("views/insights.py", "Insights", ":material/bar_chart:", "MANAGE", "Insights",
     "What has happened: sales, gross profit, trends and best sellers."),
    ("views/settings.py", "Settings", ":material/settings:", "MANAGE", "Settings",
     "Your shop, supplier, budget, local events, the assistant, display and data."),
    ("views/product.py", "Product detail", ":material/insights:", "", "", ""),
]
want = os.environ.get("LARIS_PAGE", "")
# st.Page(visibility=...) only exists in newer Streamlit; on older versions the product page's nav link is hidden by
# CSS instead (laris_ui.CSS, url path "product").
_hide = {"visibility": "hidden"} if "visibility" in inspect.signature(st.Page).parameters else {}
pages = [st.Page(path, title=title, icon=icon, default=(path.endswith("/" + want) if want else i == 0),
                 **(_hide if path.endswith("/product.py") else {}))
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
ss["motion"] = prefs.get("motion", "system")
if ss["motion"] == "always":
    st.markdown(ui.force_motion_css(), unsafe_allow_html=True)
for k, v in {"service": 0.95, "scale": 1.0, "preset": "Mixed week", "strategy": "essentials", "order_adj": {},
             "budget_rm": None, "inputs_dirty": False, "tool": "L"}.items():
    ss.setdefault(k, v)
stores = sorted(fc["store"].unique(), key=lambda s: (len(s), s))
test = fc[fc["split"] == "test"]
days = sorted(pd.Timestamp(d) for d in test["date"].unique()
              if pd.Timestamp(d) + pd.Timedelta(days=6) <= test["date"].max())
ss["_days"], ss["_stores"] = days, stores
ss["_default_week"] = default_week(fc, settings, (OUT / "metrics.json").stat().st_mtime)
# A new session opens on the default "tight-budget week" (PITCH_PLAN.md) unless LARIS_DEFAULT_WEEK=0.
if "as_of" not in ss and os.environ.get("LARIS_DEFAULT_WEEK", "1") != "0" and ss["_default_week"][1] in days:
    ss.update(store=ss["_default_week"][0], as_of=ss["_default_week"][1], preset="Tight budget")
if ss.get("as_of") not in days:
    ss["as_of"] = days[len(days) // 2]
if ss.get("store") not in stores:
    ss["store"] = stores[0]
store_id, as_of = ss["store"], ss["as_of"]

# Products: load the default stock for this week, unless the owner has edited their list (then keep it).
key = (store_id, str(as_of))
if ss.get("inputs_key") != key:
    if ss.get("inputs_dirty") and "inputs" in ss:
        ss["flash"] = ss.get("flash", []) + ["You changed the planning week; your edited product list was kept. "
                                             "Use Settings › Data & planning › Restore default stock levels to reload it."]
    else:
        week0 = core.week_view(fc, store_id, as_of, ss["scale"])
        ss["inputs"], ss["widest"] = core.default_inputs(week0, settings, sig, store_id, ss["preset"])
    ss["order_adj"] = {}
    ss["inputs_key"] = key

build = lambda budget: core.build_context(
    fc, sig, settings, store_id, as_of, ss["inputs"], budget, ss["scale"], ss["service"], unc,
    metrics.get("alert_backtest"), protect_must_have=ss["strategy"] == "essentials", adjust=ss["order_adj"])
if ss["budget_rm"] is None:   # first visit: the preset's share of the full recommended order (100% = covers it all)
    ideal, pct = build(None)["ideal_rm"], core.PRESETS.get(ss["preset"], {}).get("budget_pct", 100)
    ss["budget_rm"] = float(ceil(ideal / 50) * 50) if pct >= 100 else float(round(ideal * pct / 100 / 10) * 10)

ctx = build(ss["budget_rm"])
ss["ctx"] = {**ctx, "metrics": metrics, "fc": fc, "sig": sig, "settings": settings, "is_mock": is_dev_data,
             "inputs": ss["inputs"], "ref": planning.order_ref(store_id, as_of), "shop": ss["shop_name"],
             "out_dir": str(OUT), "default_week": ss["_default_week"]}

# ---------------- slim context bar: shop and planning week ----------------
st.markdown(
    f'<div class="lr-contextbar"><span><b>{escape(ss["shop_name"])}</b> · {escape(ss["shop_place"])}</span>'
    f'<span>Planning week {as_of:%d %b} – {as_of + pd.Timedelta(days=6):%d %b}</span></div>', unsafe_allow_html=True)
for msg in ss.pop("flash", []):
    st.toast(msg)
_, _, _, eyebrow, headline, subtitle = meta[pg.title]
if headline:
    st.markdown(ui.page_header(eyebrow, headline, subtitle), unsafe_allow_html=True)
pg.run()

st.divider()
st.caption("Forecasts by the LARIS AI model; RM impacts are estimates. LARIS never sends messages or places orders "
           "by itself. Model, data and accuracy: see Proof.")
