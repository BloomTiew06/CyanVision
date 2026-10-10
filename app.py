"""LARIS demo app.  Run:  streamlit run app.py

Reads precomputed files from ./outputs (made by pipeline.py), so it starts instantly and never
depends on a live download. "This week" is a date inside the held-out test period, so the demo can
reveal what actually happened next (a replay, labelled as one). Pages live in views/; the shared
context (forecasts, risks, allocation) is computed here once per run by laris_core.
"""
import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st

import laris_core as core
import laris_ui as ui
from inventory import load_settings

st.set_page_config(page_title="LARIS", page_icon="🛒", layout="wide")
ROOT = Path(__file__).parent
OUT = Path(os.environ.get("SHELFSIGNAL_OUT", ROOT / "outputs"))
st.markdown(ui.CSS, unsafe_allow_html=True)


@st.cache_data
def load_outputs(out_dir):
    out = Path(out_dir)
    metrics = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
    fc = pd.read_parquet(out / "forecasts.parquet")
    fc["date"] = pd.to_datetime(fc["date"])
    fc["store"] = fc["store"].astype(str)
    sig = pd.read_csv(out / "sigma.csv", dtype={"store": str}).set_index("sid")
    frontier = pd.read_csv(out / "sim_frontier.csv")
    imp = pd.read_csv(out / "importance.csv")
    per = pd.read_csv(out / "per_product_metrics.csv")
    return metrics, fc, sig, frontier, imp, per


@st.cache_data
def load_product_settings(path):
    return load_settings(path)


if not (OUT / "metrics.json").exists():
    st.error(f"No pipeline outputs in {OUT}. Run:  python pipeline.py --data <folder with train.csv> --out outputs")
    st.stop()
metrics, fc, sig, frontier, imp, per = load_outputs(str(OUT))
settings = load_product_settings(str(ROOT / "product_settings.csv"))
is_mock = "MOCK" in metrics["data_source"]

PAGES = [
    ("views/dashboard.py", "Dashboard", ":material/dashboard:", "", "", "Here's what needs your attention before the next delivery."),
    ("views/forecast.py", "Sales forecast", ":material/monitoring:", "L", "Lihat ke depan",
     "AI predictions for the next 7 days, with likely ranges."),
    ("views/alerts.py", "Risk alerts", ":material/notifications:", "A", "Amaran stok habis",
     "Problems spotted early, by type, ranked by what they could cost you."),
    ("views/waste.py", "Waste reduction", ":material/eco:", "R", "Rendahkan pembaziran",
     "Stock that won't sell before it expires, or that ties up cash."),
    ("views/orders.py", "Budget & orders", ":material/shopping_cart:", "I", "Ikut bajet",
     "The best order list for your cash, with must-have items protected first."),
    ("views/results.py", "Results", ":material/fact_check:", "S", "Semak hasil",
     "How well LARIS predicts and decides, measured and simulated, labelled."),
    ("views/settings.py", "Settings", ":material/settings:", "", "", "Your shop, stock and placeholder settings."),
]
want = os.environ.get("LARIS_PAGE", "")
pages = [st.Page(path, title=title, icon=icon, default=(path.endswith(want) if want else i == 0))
         for i, (path, title, icon, *_rest) in enumerate(PAGES)]
meta = {p[1]: p for p in PAGES}

# ---------------- shared state (mirrored so it survives page changes) ----------------
ss = st.session_state
ss.setdefault("preset", "Mixed week")
ss.setdefault("scale", 1.0)
ss.setdefault("service", 0.95)
ss.setdefault("budget_pct", 60)
ss.setdefault("shop_name", "Kedai Maju")
ss.setdefault("shop_place", "Shah Alam")
ss.setdefault("owner", "Encik Hafiz")

with st.sidebar:
    st.markdown(ui.brand(), unsafe_allow_html=True)
pg = st.navigation(pages)

stores = sorted(fc["store"].unique(), key=lambda s: (len(s), s))
test = fc[fc["split"] == "test"]
test_end = test["date"].max()
days = sorted(pd.Timestamp(d) for d in test["date"].unique() if pd.Timestamp(d) + pd.Timedelta(days=6) <= test_end)
with st.sidebar:
    store = st.selectbox("Sales data from store", stores, key="store")
    st.markdown(ui.shop_card(ss["shop_name"], ss["shop_place"]), unsafe_allow_html=True)

_, title, _, letter, malay, subtitle = meta[pg.title]
head, pick = st.columns([3, 1.2])
head.markdown(ui.page_header(letter, malay, title, subtitle), unsafe_allow_html=True)
as_of = pick.selectbox("This week (replay)", days, index=len(days) // 2, key="as_of",
                       format_func=lambda d: f"{d:%d %b} – {d + pd.Timedelta(days=6):%d %b %Y}")
if is_mock:
    st.error("MOCK DATA: generated for development only. Do not present these numbers.")
if ss["scale"] != 1.0:
    st.caption(f"Shop size ×{ss['scale']:g} (PLACEHOLDER): forecasts and ranges are scaled from Favorita store "
               "volumes for illustration; linear scaling understates uncertainty at small volumes.")

key = (store, str(as_of), ss["scale"], ss["preset"])
if ss.get("inputs_key") != key:
    week0 = core.week_view(fc, store, as_of, ss["scale"])
    ss["inputs"], ss["widest"] = core.default_inputs(week0, settings, sig, store, ss["preset"])
    if ss.get("inputs_key") is None or ss.get("inputs_key")[3] != ss["preset"]:
        ss["budget_pct"] = core.PRESETS[ss["preset"]]["budget_pct"]
    ss["inputs_key"] = key

ss["ctx"] = {**core.build_context(fc, sig, settings, store, as_of, ss["inputs"], ss["budget_pct"],
                                  ss["scale"], ss["service"]),
             "metrics": metrics, "fc": fc, "sig": sig, "frontier": frontier, "imp": imp, "per": per,
             "settings": settings, "is_mock": is_mock, "inputs": ss["inputs"], "widest": ss.get("widest")}
pg.run()

st.divider()
st.caption(f"Forecasts come from a machine-learning model trained and tested on {metrics['data_source']}. "
           "This is not Malaysian sales data. Stock, prices, costs, shelf life, lead times and budget are your "
           "inputs (PLACEHOLDER defaults). Dates are a replay of the held-out test period. Advice only: LARIS "
           "never places orders.")
