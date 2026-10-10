import streamlit as st

import laris_ui as ui

ctx = st.session_state["ctx"]
rows = ctx["rows"]
dead = rows[rows["dead_flag"]].sort_values("expected_expire_rm", ascending=False)

c = st.columns(3)
c[0].markdown(ui.kpi("Products flagged", f"{len(dead)}", "dead stock or cash tied up", "warn" if len(dead) else "good"),
              unsafe_allow_html=True)
c[1].markdown(ui.kpi("May expire unsold", f"RM {dead['expected_expire_rm'].sum():,.0f}", "perishables, at cost", "warn"),
              unsafe_allow_html=True)
c[2].markdown(ui.kpi("Cash in long-life overstock", f"RM {(dead.loc[~dead['perishable'], 'on_hand'] * dead.loc[~dead['perishable'], 'unit_cost']).sum():,.0f}",
                     "more than 4 weeks of cover"), unsafe_allow_html=True)
st.write("")
if dead.empty:
    st.success("No dead stock: everything should sell before it expires.")
for _, r in dead.iterrows():
    with st.container(border=True):
        st.markdown(f"{ui.chip(r['label'].split(' / ')[1], 'lr-order')} **{r['name']}**", unsafe_allow_html=True)
        if r["perishable"]:
            st.markdown(f"**{r['days_of_cover']:,.0f} days** of stock vs a **{r['shelf_life']}-day** shelf life. "
                        f"About **{r['expected_expire_units']:,.0f} units (RM {r['expected_expire_rm']:,.0f})** "
                        "are expected to expire unsold.")
            st.progress(min(1.0, r["shelf_life"] / max(r["days_of_cover"], 1e-9)),
                        text=f"Shelf life covers {min(1.0, r['shelf_life'] / max(r['days_of_cover'], 1e-9)):.0%} "
                             "of the stock you hold")
        else:
            st.markdown(f"**{r['days_of_cover']:,.0f} days** of stock for a long-life product "
                        f"(RM {r['on_hand'] * r['unit_cost']:,.0f} of cash tied up).")
        st.markdown(f"**Action:** {r['action']}")
st.caption("Assumes the stock on hand is fresh (LARIS doesn't know its age). Shelf lives are PLACEHOLDER settings.")
