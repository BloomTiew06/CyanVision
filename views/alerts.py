import streamlit as st

import laris_ui as ui
from inventory import CATEGORIES

ctx = st.session_state["ctx"]
rows = ctx["rows"]
alerts = rows[rows["tier"] != "OK"]

c = st.columns(3)
for col, tier, tone in zip(c, ["Act today", "This order", "Watch"], ["bad", "warn", None]):
    col.markdown(ui.kpi(tier, f"{int((alerts['tier'] == tier).sum())}", "products", tone), unsafe_allow_html=True)

present = [code for code in CATEGORIES if code in set(alerts["category"])]
names = {code: CATEGORIES[code][1] for code in present}
pick = st.segmented_control("Type of problem", ["All"] + [names[c] for c in present], default="All",
                            key="alert_filter")
if pick and pick != "All":
    code = next(c for c, n in names.items() if n == pick)
    alerts = alerts[alerts["category"] == code]

st.caption("Ranked by urgency, then by RM at risk if you do nothing. Tags show where each statement comes from: "
           "the AI forecast, a calculation from it, the model's recent track record, or your settings.")
if alerts.empty:
    st.success("No alerts of this type this week.")
for _, r in alerts.iterrows():
    rod = r["run_out_day"]
    days_left = "lasts beyond 7 days" if rod is None or rod != rod else f"runs out in ~{int(rod)} day(s)"
    head = f"{r['name']} · {r['label'].split(' / ')[1]} · {r['tier']} · RM {r['rm_at_risk']:,.0f} at risk"
    with st.expander(head, expanded=r["tier"] == "Act today"):
        st.markdown(f"{ui.tier_chip(r['tier'])}{ui.chip(r['label'])}"
                    f"{ui.chip('Must-have') if r['must_have'] else ''}", unsafe_allow_html=True)
        a, b, c3 = st.columns(3)
        a.metric("Chance of running out before delivery", f"{r['p_stockout']:.0%}")
        b.metric("Stock", days_left, f"delivery in {r['lead_time']} day(s)", delta_color="off")
        c3.metric("RM at risk", f"RM {r['rm_at_risk']:,.0f}")
        st.markdown(f"**Recommended action:** {r['action']}")
        st.markdown(ui.evidence(r["why"]), unsafe_allow_html=True)
