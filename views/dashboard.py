import altair as alt
import streamlit as st

import laris_core as core
import laris_ui as ui

ctx = st.session_state["ctx"]
ss = st.session_state
rows, tot, ideal = ctx["rows"], ctx["totals"], ctx["ideal_totals"]

st.markdown(f"#### Selamat pagi, {ss['owner']}")
st.markdown('<div class="lr-hero"><h3>Biar laris, jangan habis.</h3><p>LARIS predicts what will run out or go '
            'to waste before your next delivery, and builds the best order for the cash you have.</p></div>',
            unsafe_allow_html=True)

act = rows[rows["tier"] == "Act today"]
stock_cats = rows["category"].isin(["STOCKOUT_IMMINENT", "REORDER_NEEDED", "DEMAND_SURGE"])
exp_rm = rows.loc[rows["dead_flag"] & rows["perishable"], "expected_expire_rm"].sum()
c = st.columns(4)
c[0].markdown(ui.kpi("Act today", f"{len(act)} product(s)", "run out before delivery" if len(act) else "nothing urgent",
                     "bad" if len(act) else "good"), unsafe_allow_html=True)
c[1].markdown(ui.kpi("Sales at risk (margin)", f"RM {rows.loc[stock_cats, 'rm_at_risk'].sum():,.0f}",
                     "if you do nothing", "bad"), unsafe_allow_html=True)
c[2].markdown(ui.kpi("Stock that may expire", f"RM {exp_rm:,.0f}", "skip or discount it", "warn"),
              unsafe_allow_html=True)
c[3].markdown(ui.kpi("Recommended order", f"RM {tot['spent_rm']:,.0f}",
                     f"of RM {ctx['budget_rm']:,.0f} budget · ideal RM {ideal['ideal_rm']:,.0f}"),
              unsafe_allow_html=True)

st.write("")
left, right = st.columns([3, 2])
with left:
    st.markdown("**Expected sales, next 7 days (RM per day)**")
    fut, hist = core.sales_value_series(ctx["week"], ctx["inputs"], ctx["sig"], ctx["store"], ctx["scale"])
    chart = (alt.Chart(fut).mark_area(opacity=0.25, color=ui.GREEN).encode(x="date:T", y="lo:Q", y2="hi:Q")
             + alt.Chart(fut).mark_line(point=True, color=ui.GREEN).encode(
                 x=alt.X("date:T", title=None), y=alt.Y("rm:Q", title="RM per day"),
                 tooltip=[alt.Tooltip("date:T"), alt.Tooltip("rm:Q", format=",.0f")])
             + alt.Chart(hist).mark_line(color="#9AA59F").encode(x="date:T", y="rm:Q"))
    st.altair_chart(chart.properties(height=260), use_container_width=True)
    st.caption("Green: AI forecast × your prices, with a 90% range (product errors assumed independent). "
               "Grey: actual sales of the last 14 days.")
with right:
    st.markdown("**Top risks, ranked by what they could cost**")
    top = rows[rows["tier"] != "OK"].head(5)
    if top.empty:
        st.success("No risks this week.")
    for _, r in top.iterrows():
        when = "" if r["act_by"] is None or r["act_by"] != r["act_by"] else f" · act within {int(r['act_by'])} day(s)"
        st.markdown(f'<div class="lr-card" style="margin-bottom:8px">{ui.tier_chip(r["tier"])}'
                    f'{ui.chip(r["label"].split(" / ")[1])}<br><b>{r["name"]}</b> · RM {r["rm_at_risk"]:,.0f} at risk'
                    f'{when}<br><span style="font-size:13px;color:#5B6B62">{r["action"]}</span></div>',
                    unsafe_allow_html=True)
    st.page_link("views/alerts.py", label="See all risk alerts and why", icon=":material/arrow_forward:")
