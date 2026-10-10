import altair as alt
import pandas as pd
import streamlit as st

import laris_ui as ui

ctx = st.session_state["ctx"]
metrics, frontier, imp, per = ctx["metrics"], ctx["frontier"], ctx["imp"], ctx["per"]
s = metrics["splits"]

t1, t2, t3, t4, t5 = st.tabs(["Forecast accuracy", "Alert quality", "Robustness", "Decision quality",
                              "Assumptions and limits"])
with t1:
    st.markdown(ui.label("MEASURED", "measured") + f" Held-out test period {s['test'][0]} to {s['test'][1]}; the model "
                "never saw these dates. WAPE = total absolute error ÷ total sales (lower is better).",
                unsafe_allow_html=True)
    acc = pd.DataFrame([{"Method": m, "Daily WAPE": v["WMAPE"],
                         "7-day total WAPE": metrics["test_weekly_totals"][m]["WMAPE"],
                         "Daily MAE": v["MAE"], "Bias": v["bias"]}
                        for m, v in metrics["test_daily"].items()])
    best = acc.loc[acc["7-day total WAPE"].idxmin(), "Method"]
    model_row = acc[acc["Method"].str.startswith("Model")]
    c = st.columns(3)
    if len(model_row):
        m7 = float(model_row["7-day total WAPE"].iloc[0])
        base7 = acc[~acc["Method"].str.startswith("Model")]["7-day total WAPE"].min()
        c[0].markdown(ui.kpi("Forecast accuracy, 7-day totals", f"{1 - m7:.0%}", "1 − WAPE, test period"),
                      unsafe_allow_html=True)
        c[1].markdown(ui.kpi("Best simple rule", f"{1 - base7:.0%}", "same measure, same days",
                             "good" if m7 < base7 else "bad"), unsafe_allow_html=True)
    if "band_coverage_90" in metrics:
        c[2].markdown(ui.kpi("Actual sales inside the 90% range", f"{metrics['band_coverage_90']:.0%}",
                             "about 90% = honest range"), unsafe_allow_html=True)
    st.dataframe(acc.style.format({"Daily WAPE": "{:.1%}", "7-day total WAPE": "{:.1%}", "Daily MAE": "{:,.1f}",
                                   "Bias": "{:+.1%}"}), hide_index=True, use_container_width=True)
    if not best.startswith("Model"):
        st.warning(f"On 7-day totals, '{best}' beat the model on this test period.")
    a, b = st.columns(2)
    a.markdown("**Accuracy by product (test WAPE)**")
    a.dataframe(per.set_index("product").drop(columns="test_units").style.format("{:.1%}"), use_container_width=True)
    b.markdown("**What the AI relies on (permutation importance)**")
    b.altair_chart(alt.Chart(imp.head(10)).mark_bar(color=ui.GREEN).encode(
        x=alt.X("importance:Q", title="increase in error when shuffled"), y=alt.Y("feature:N", sort="-x", title=None)),
        use_container_width=True)
with t2:
    st.markdown(ui.label("MEASURED on real sales, simulated stock", "measured"), unsafe_allow_html=True)
    if "alert_backtest" in metrics:
        st.json(metrics["alert_backtest"])
    else:
        st.info("Not run yet. The alert backtest (precision, recall and false-alarm rate vs a min-stock rule) "
                "is the next pipeline step.")
with t3:
    st.markdown(ui.label("MEASURED", "measured"), unsafe_allow_html=True)
    if "unseen_stores" in metrics:
        st.json(metrics["unseen_stores"])
    else:
        st.info("Not run yet. Unseen-store and noisy-data tests come in the next pipeline steps.")
with t4:
    sim = metrics["simulation"]
    st.markdown(ui.label("SIMULATED", "simulated") + f" {sim['label']}. Lead time {sim['lead_time_days']} days, "
                f"ordering every {sim['review_days']} days.", unsafe_allow_html=True)
    h = sim.get("headline_matched_fill_rate")
    if h:
        chg = h["stock_change_pct"]
        st.markdown(f"To reach the same **{h['matched_fill_rate']:.1%} fill rate**, ordering from the AI forecast held "
                    f"**{h['model_days_of_cover']:.2f} days** of stock vs **{h['baseline_days_of_cover']:.2f}** for "
                    f"the moving-average rule ({abs(chg):.0%} {'less' if chg < 0 else 'more'}).")
    fr = frontier.assign(policy=frontier["policy"].map({"model": "AI forecast (LARIS)",
                                                        "baseline": "28-day average + safety stock"}))
    st.altair_chart(alt.Chart(fr).mark_line(point=True).encode(
        x=alt.X("days_of_cover:Q", title="average stock held (days of demand)", scale=alt.Scale(zero=False)),
        y=alt.Y("fill_rate:Q", title="share of demand served", axis=alt.Axis(format="%"), scale=alt.Scale(zero=False)),
        color=alt.Color("policy:N", title=None, scale=alt.Scale(range=[ui.GREEN, "#9AA59F"]),
                        legend=alt.Legend(orient="bottom")),
        tooltip=["policy", "z", "fill_rate", "days_of_cover"]), use_container_width=True)
    st.caption("Each point is one service-level setting. Up and to the left is better: more demand served with less stock.")
    st.markdown("**Assumptions**\n" + "\n".join(f"- {x}" for x in sim["assumptions"]))
    if "budget_simulation" not in metrics:
        st.info("Budget replay (LARIS vs 'order last week's sales' and other usual rules at the same budget) not run yet.")
with t5:
    st.markdown(f"""
- **Training and test data:** {metrics['data_source']}. Not Malaysian. Results show the method works on real
  retail data; they are not a claim about any Malaysian shop.
- **Splits:** train to {s['train_end']}, validation {s['val'][0]} to {s['val'][1]} (used only for the error
  spread), test {s['test'][0]} to {s['test'][1]}.
- **Leakage control:** every feature uses sales from 7+ days earlier, plus calendar, holidays and planned promotions.
- **Not in the data:** stock levels, stockouts, prices, supplier lead times, shelf lives. These come from your inputs
  (PLACEHOLDER defaults); historical sales stand in for demand and may be lower than true demand where shelves ran empty.
- **Not yet demonstrable:** performance on Malaysian shops, real savings, and whether owners find the advice clear.
  These need a pilot.
""")
