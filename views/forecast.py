import altair as alt
import numpy as np
import pandas as pd
import streamlit as st
from scipy.stats import norm

ctx = st.session_state["ctx"]
rows, week = ctx["rows"], ctx["week"]

tbl = rows.assign(
    trend=np.where(rows["demand_last7"] <= 0, "–",
                   np.where(rows["demand_7d"] > rows["demand_last7"] * 1.05, "↗ up",
                            np.where(rows["demand_7d"] < rows["demand_last7"] * 0.95, "↘ down", "→ flat"))),
    range_pct=rows["band_pct"].replace(np.inf, np.nan) * 100,
    model_err=rows["model_err28"].astype(float) * 100, naive_err=rows["naive_err28"].astype(float) * 100)
view = st.segmented_control("Show", ["All", "Top sellers", "High risk"], default="All", key="fc_filter")
if view == "Top sellers":
    tbl = tbl.sort_values("demand_7d", ascending=False).head(5)
elif view == "High risk":
    tbl = tbl[tbl["tier"].isin(["Act today", "This order"])]
st.dataframe(
    tbl[["name", "demand_7d", "range_pct", "demand_last7", "trend", "model_err", "naive_err"]],
    hide_index=True, use_container_width=True,
    column_config={
        "name": st.column_config.TextColumn("Product"),
        "demand_7d": st.column_config.NumberColumn("Forecast, next 7 days", format="%.0f"),
        "range_pct": st.column_config.NumberColumn("Likely range (±%)", format="%.0f%%"),
        "demand_last7": st.column_config.NumberColumn("Sold, last 7 days", format="%.0f"),
        "trend": st.column_config.TextColumn("Trend"),
        "model_err": st.column_config.NumberColumn("Model error, last 28 d", format="%.0f%%"),
        "naive_err": st.column_config.NumberColumn("'Same day last week' error", format="%.0f%%"),
    })
st.caption("Forecasts are AI model predictions made without seeing these days' sales (features use sales at least "
           "7 days old). Range = 90% band from the model's measured error. Errors = WAPE on the 28 days before "
           "this week (lower is better).")

st.markdown("**Why this forecast: one product in detail**")
names = rows.set_index("name")["product"].to_dict()
default = rows.loc[rows["product"] == ctx.get("widest"), "name"]
default_name = default.iloc[0] if len(default) else rows["name"].iloc[0]
c1, c2 = st.columns([3, 1])
pick_name = c1.selectbox("Product", list(names), index=list(names).index(default_name), key="fc_product")
reveal = c2.toggle("Reveal what actually happened", value=False, key="reveal",
                   help="Replay mode: show real sales for the 7 forecast days.")
pick = names[pick_name]
prow = rows[rows["product"] == pick].iloc[0]
scale = ctx["scale"]
sub = week["sub"]
hist = sub[(sub["product"] == pick) & (sub["date"] >= week["as_of"] - pd.Timedelta(days=28))
           & (sub["date"] < week["as_of"])].assign(y=lambda d: d["y"] * scale)
fut = week["window"][week["window"]["product"] == pick].sort_values("date").assign(
    pred=lambda d: d["pred_model"] * scale, naive=lambda d: d["pred_naive7"] * scale, y=lambda d: d["y"] * scale)
zb = float(norm.ppf(0.95))
band = fut.assign(lo=(fut["pred"] - zb * prow["sigma"]).clip(lower=0), hi=fut["pred"] + zb * prow["sigma"])
layers = [
    alt.Chart(hist).mark_line(color="#8A968F").encode(x=alt.X("date:T", title=None), y=alt.Y("y:Q", title="units per day")),
    alt.Chart(band).mark_area(opacity=0.22, color="#0F6B45").encode(x="date:T", y="lo:Q", y2="hi:Q"),
    alt.Chart(fut).mark_line(point=True, color="#0F6B45").encode(
        x="date:T", y="pred:Q", tooltip=["date:T", alt.Tooltip("pred:Q", format=",.0f")]),
    alt.Chart(fut).mark_line(strokeDash=[4, 4], color="#B0B8B3").encode(x="date:T", y="naive:Q"),
]
if reveal:
    layers.append(alt.Chart(fut).mark_point(color="#D62728", size=70, filled=True).encode(x="date:T", y="y:Q"))
left, right = st.columns([3, 2])
left.altair_chart(alt.layer(*layers).properties(height=280), use_container_width=True)
left.caption("Grey: last 28 days of sales. Green: AI forecast with 90% range. Dashed: same day last week."
             + (" Red: what actually sold (replay)." if reveal else ""))
if reveal and fut["y"].notna().any():
    err = (fut["y"] - fut["pred"]).abs().sum() / max(fut["y"].sum(), 1e-9)
    left.markdown(f"This week the model was off by **{err:.0%}** (WAPE) for {pick_name}; "
                  f"{int(((fut['y'] >= band['lo']) & (fut['y'] <= band['hi'])).sum())} of {len(fut)} days fell inside "
                  "the 90% range.")
daily = week["fc_wide"][pick].to_numpy()
proj = pd.DataFrame({"date": pd.date_range(week["as_of"], week["end"]),
                     "stock": prow["on_hand"] + prow["on_order"] - np.cumsum(daily)})
delivery = week["as_of"] + pd.Timedelta(days=int(prow["lead_time"]))
right.altair_chart(
    (alt.Chart(proj).mark_line(point=True, color="#0F6B45").encode(x=alt.X("date:T", title=None),
                                                                   y=alt.Y("stock:Q", title="projected stock"))
     + alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color="#D62728").encode(y="y:Q")
     + alt.Chart(pd.DataFrame({"date": [delivery]})).mark_rule(strokeDash=[3, 3]).encode(x="date:T"))
    .properties(height=280), use_container_width=True)
right.caption("Projected stock if you don't order. Dashed line: when an order placed today would arrive.")
