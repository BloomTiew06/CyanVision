"""ShelfSignal demo app.  Run:  streamlit run app.py

Reads precomputed files from ./outputs (made by pipeline.py), so it starts instantly and
never depends on a live download. "Today" is a date inside the held-out test period, so the
demo can reveal what actually happened next (a replay, labelled as one).
"""
import json
import os
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st
from scipy.stats import norm

from inventory import assess, rank

st.set_page_config(page_title="ShelfSignal", layout="wide")
OUT = Path(os.environ.get("SHELFSIGNAL_OUT", Path(__file__).parent / "outputs"))
COVER_PATTERN = [1.5, 6, 2.5, 12, 4, 9, 1, 7, 3, 10, 5, 8]  # default stock = N days of forecast, to give a mix


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


if not (OUT / "metrics.json").exists():
    st.error(f"No pipeline outputs in {OUT}. Run:  python pipeline.py --data <folder with train.csv> --out outputs")
    st.stop()
metrics, fc, sig, frontier, imp, per = load_outputs(str(OUT))
is_mock = "MOCK" in metrics["data_source"]

# ---------------- sidebar ----------------
st.sidebar.header("Settings")
store = st.sidebar.selectbox("Store", sorted(fc["store"].unique(), key=lambda s: (len(s), s)))
test = fc[fc["split"] == "test"]
test_end = test["date"].max()
days = sorted(d for d in test["date"].unique() if d + pd.Timedelta(days=6) <= test_end)
as_of = st.sidebar.select_slider("Pretend today is", options=days, value=days[len(days) // 2],
                                 format_func=lambda d: pd.Timestamp(d).strftime("%a %d %b %Y"))
as_of = pd.Timestamp(as_of)
service = st.sidebar.select_slider("Service level target", options=[0.90, 0.95, 0.98, 0.99], value=0.95,
                                   format_func=lambda v: f"{v:.0%}")
default_lead = st.sidebar.number_input("Default supplier lead time (days)", 1, 14, 3)
reveal = st.sidebar.toggle("Reveal what actually happened", value=False,
                           help="Replay mode: show real sales for the 7 forecast days.")

# ---------------- header ----------------
if is_mock:
    st.error("MOCK DATA: generated for development only. Do not present these numbers.")
st.title("ShelfSignal")
st.markdown("**Cukup stok?** Which products will run out before your next delivery, and how much should you "
            "order today?")
st.markdown("**S** Sales forecast &nbsp;·&nbsp; **T** Time to run out &nbsp;·&nbsp; **O** Order now "
            "&nbsp;·&nbsp; **K** Keep score")
st.caption(f"Model trained and tested on: {metrics['data_source']}. This is not Malaysian sales data. "
           "Stock levels, lead times and RM values are your inputs. Dates are a replay of the held-out test period.")

win_end = as_of + pd.Timedelta(days=6)
sub = fc[fc["store"] == store]
window = sub[(sub["date"] >= as_of) & (sub["date"] <= win_end)]
products = sorted(window["product"].unique())
fc_wide = window.pivot_table(index="date", columns="product", values="pred_model").reindex(
    pd.date_range(as_of, win_end)).fillna(0)
last7 = sub[(sub["date"] >= as_of - pd.Timedelta(days=7)) & (sub["date"] < as_of)].groupby("product")["y"].sum()
promo_days = window.assign(p=window["promo"] > 0).groupby("product")["p"].sum()
holiday_in_window = bool(window["holiday"].max()) if len(window) else False

# ---------------- inputs ----------------
defaults = []
for i, prod in enumerate(products):
    daily_mean = float(fc_wide[prod].mean()) if prod in fc_wide else 0.0
    defaults.append({"Product": prod,
                     "On hand": round(daily_mean * COVER_PATTERN[i % len(COVER_PATTERN)]),
                     "On order": 0, "Lead time (days)": int(default_lead),
                     "Unit cost (RM)": 5.00, "Unit margin (RM)": 1.50, "Pack size": 1})
with st.expander("Your stock and supplier inputs (edit any cell)", expanded=False):
    st.caption("Defaults are placeholders that create a mix of situations; enter your own numbers.")
    inputs = st.data_editor(pd.DataFrame(defaults), key=f"inputs-{store}-{as_of.date()}-{default_lead}",
                            disabled=["Product"], hide_index=True, width="stretch")

rows = []
for _, r in inputs.iterrows():
    prod = r["Product"]
    sid = f"{store}|{prod}"
    daily = fc_wide[prod].to_numpy() if prod in fc_wide else np.zeros(7)
    sigma = float(sig.loc[sid, "sigma_d"]) if sid in sig.index else max(1.0, float(np.mean(daily)) * 0.3)
    res = assess(daily, sigma, r["On hand"], r["On order"], r["Lead time (days)"], 7, service,
                 r["Unit cost (RM)"], r["Unit margin (RM)"], r["Pack size"])
    prev = float(last7.get(prod, 0.0))
    change = f"{res['demand_7d'] / prev - 1:+.0%} vs last 7 days" if prev > 0 else "no recent sales"
    why = [f"7-day forecast {res['demand_7d']:,.0f} ({change})"]
    if promo_days.get(prod, 0):
        why.append(f"promotion planned on {int(promo_days[prod])} day(s)")
    if holiday_in_window:
        why.append("public holiday in window")
    cover = "past 7 days" if res["run_out_day"] is None else f"~{res['run_out_day']} day(s)"
    why.append(f"stock lasts {cover}; delivery takes {int(r['Lead time (days)'])}")
    res.update({"Product": prod, "Why": "; ".join(why), "sigma": sigma,
                "On hand": r["On hand"], "Lead time": int(r["Lead time (days)"])})
    rows.append(res)
table = rank(rows)

crit = table[table["status"] == "CRITICAL"]
order = table[table["status"] == "ORDER"]

# ---------------- T: time to run out ----------------
st.subheader("T · Time to run out")
if len(crit):
    st.error(f"**{len(crit)} product(s) will run out before an order placed today can arrive:** "
             f"{', '.join(crit['Product'])}. Order now and expedite, transfer stock, or offer a substitute.")
elif len(order):
    st.warning(f"**{len(order)} product(s) need an order today** to stay above your {service:.0%} service target.")
else:
    st.success("All products are covered until the next order cycle.")
t1c, t2c = st.columns(2)
t1c.metric("Run out before delivery", len(crit))
t2c.metric("Margin at risk before delivery", f"RM {table['margin_at_risk'].sum():,.0f}")

# ---------------- O: order now ----------------
st.subheader("O · Order now")
o1c, o2c = st.columns(2)
o1c.metric("Products to order today", len(crit) + len(order))
o2c.metric("Recommended order value", f"RM {table['order_value'].sum():,.0f}")
st.caption("Ranked by urgency, then ringgit at risk. Order quantity = forecast for lead time + 7 days "
           f"+ safety stock at your {service:.0%} service level, minus stock you already have.")

show = table.assign(
    **{"Runs out": table["run_out_day"].map(lambda d: "beyond 7 days" if pd.isna(d) else f"day {int(d)}")}
)[["status", "Product", "Runs out", "p_stockout", "order_qty", "order_value", "margin_at_risk", "Why"]]
show["p_stockout"] = (show["p_stockout"] * 100).round(0)
st.dataframe(
    show, hide_index=True, width="stretch",
    column_config={
        "status": st.column_config.TextColumn("Status"),
        "p_stockout": st.column_config.ProgressColumn("Chance of stockout before delivery", min_value=0,
                                                      max_value=100, format="%.0f%%"),
        "order_qty": st.column_config.NumberColumn("Order qty", format="%d"),
        "order_value": st.column_config.NumberColumn("Order value (RM)", format="%.0f"),
        "margin_at_risk": st.column_config.NumberColumn("Margin at risk (RM)", format="%.0f"),
    })

# ---------------- S: sales forecast ----------------
st.subheader("S · Sales forecast: why this recommendation")
pick = st.selectbox("Product", table["Product"].tolist())
prow = table[table["Product"] == pick].iloc[0]
hist = sub[(sub["product"] == pick) & (sub["date"] >= as_of - pd.Timedelta(days=28)) & (sub["date"] < as_of)]
fut = window[window["product"] == pick].sort_values("date")
zb = float(norm.ppf(service))
band = fut.assign(lo=(fut["pred_model"] - zb * prow["sigma"]).clip(lower=0),
                  hi=fut["pred_model"] + zb * prow["sigma"])
layers = [
    alt.Chart(hist).mark_line(color="#555").encode(x="date:T", y=alt.Y("y:Q", title="units per day")),
    alt.Chart(band).mark_area(opacity=0.2).encode(x="date:T", y="lo:Q", y2="hi:Q"),
    alt.Chart(fut).mark_line(point=True).encode(x="date:T", y="pred_model:Q",
                                                tooltip=["date:T", alt.Tooltip("pred_model:Q", format=",.0f")]),
    alt.Chart(fut).mark_line(strokeDash=[4, 4], color="#999").encode(x="date:T", y="pred_naive7:Q"),
]
if reveal:
    layers.append(alt.Chart(fut).mark_point(color="#d62728", size=60, filled=True).encode(x="date:T", y="y:Q"))
left, right = st.columns([3, 2])
left.altair_chart(alt.layer(*layers).properties(height=280), width="stretch")
left.caption("Grey: last 28 days of sales. Blue: model forecast with uncertainty band. Dashed: same day last week."
             + (" Red: what actually sold (replay)." if reveal else ""))
proj = pd.DataFrame({"date": pd.date_range(as_of, win_end),
                     "stock": prow["On hand"] - np.cumsum(fc_wide[pick].to_numpy())})
delivery = as_of + pd.Timedelta(days=int(prow["Lead time"]))
right.altair_chart(
    (alt.Chart(proj).mark_line(point=True).encode(x="date:T", y=alt.Y("stock:Q", title="projected stock"))
     + alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color="#d62728").encode(y="y:Q")
     + alt.Chart(pd.DataFrame({"date": [delivery]})).mark_rule(strokeDash=[3, 3]).encode(x="date:T"))
    .properties(height=280), width="stretch")
right.caption("Projected stock if you don't order. Dashed line: when an order placed today would arrive.")
st.info(f"**{prow['status']}: {pick}.** {prow['Why']}. Recommended order: **{prow['order_qty']:,.0f} units** "
        f"(order-up-to {prow['order_up_to']:,.0f} = forecast for lead time + 7 days + safety stock "
        f"{prow['safety_stock']:,.0f} at {service:.0%} service).")

# ---------------- K: keep score ----------------
st.subheader("K · Keep score: does it work?")
t1, t2, t3 = st.tabs(["Model accuracy (measured)", "Simulation (what-if)", "Data and limits"])
with t1:
    s = metrics["splits"]
    st.caption(f"Held-out test period {s['test'][0]} to {s['test'][1]}; the model never saw these dates. "
               "WMAPE = total absolute error / total sales (lower is better).")
    acc = pd.DataFrame([{"Method": m, "Daily WMAPE": v["WMAPE"],
                         "7-day total WMAPE": metrics["test_weekly_totals"][m]["WMAPE"],
                         "Daily MAE": v["MAE"], "Bias": v["bias"]}
                        for m, v in metrics["test_daily"].items()])
    st.dataframe(acc.style.format({"Daily WMAPE": "{:.1%}", "7-day total WMAPE": "{:.1%}",
                                   "Daily MAE": "{:,.1f}", "Bias": "{:+.1%}"}),
                 hide_index=True, width="stretch")
    if "band_coverage_90" in metrics:
        st.markdown(f"**Is the uncertainty band honest?** {metrics['band_coverage_90']:.0%} of test days fell inside "
                    "the 90% band (about 90% means the safety stock is sized realistically).")
    a, b = st.columns(2)
    a.markdown("**Accuracy by product (test WMAPE)**")
    a.dataframe(per.set_index("product").drop(columns="test_units").style.format("{:.1%}"),
                width="stretch")
    b.markdown("**What the model relies on (permutation importance)**")
    b.altair_chart(alt.Chart(imp.head(10)).mark_bar().encode(
        x=alt.X("importance:Q", title="increase in error when shuffled"), y=alt.Y("feature:N", sort="-x")),
        width="stretch")
with t2:
    sim = metrics["simulation"]
    st.warning(f"{sim['label']}. Lead time {sim['lead_time_days']} days, ordering every {sim['review_days']} days.")
    h = sim.get("headline_matched_fill_rate")
    if h:
        chg = h["stock_change_pct"]
        st.markdown(f"To reach the same **{h['matched_fill_rate']:.1%} fill rate**, the forecast-based policy held "
                    f"**{h['model_days_of_cover']:.2f} days** of stock vs **{h['baseline_days_of_cover']:.2f}** for "
                    f"the moving-average policy ({abs(chg):.0%} {'less' if chg < 0 else 'more'}).")
    fr = frontier.assign(policy=frontier["policy"].map({"model": "Forecast-based (ShelfSignal)",
                                                        "baseline": "28-day average + safety stock"}))
    st.altair_chart(alt.Chart(fr).mark_line(point=True).encode(
        x=alt.X("days_of_cover:Q", title="average stock held (days of demand)", scale=alt.Scale(zero=False)),
        y=alt.Y("fill_rate:Q", title="fill rate (share of demand served)", axis=alt.Axis(format="%"),
                scale=alt.Scale(zero=False)),
        color=alt.Color("policy:N", title=None,
                        scale=alt.Scale(domain=["Forecast-based (ShelfSignal)", "28-day average + safety stock"],
                                        range=["#1f6fd1", "#9a9a9a"]),
                        legend=alt.Legend(orient="bottom", labelLimit=400)),
        tooltip=["policy", "z", "fill_rate", "days_of_cover"]),
        width="stretch")
    st.caption("Each point is one service-level setting. Up and to the left is better: more demand served with less stock.")
    st.markdown("**Assumptions**\n" + "\n".join(f"- {x}" for x in sim["assumptions"]))
with t3:
    st.markdown(f"""
- **Training and test data:** {metrics['data_source']}. Not Malaysian. Results show the method works on real
  retail data; they are not a claim about any Malaysian shop.
- **Splits:** train to {metrics['splits']['train_end']}, validation {metrics['splits']['val'][0]} to
  {metrics['splits']['val'][1]} (used only for forecast-error spread), test {metrics['splits']['test'][0]} to
  {metrics['splits']['test'][1]}.
- **Leakage control:** every feature uses sales from 7+ days earlier, plus calendar, holidays and planned promotions.
- **Not in the data:** inventory, stockouts, prices, supplier lead times. These come from your inputs; the simulation
  uses historical sales as demand.
- **To use with a real shop:** export daily sales per product from the POS as date, store, item, sales, and rerun
  `pipeline.py`.
""")
