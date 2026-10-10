import streamlit as st

import laris_ui as ui

ss = st.session_state
ctx = ss["ctx"]
alloc, tot, ideal = ctx["alloc"], ctx["totals"], ctx["ideal_totals"]


def _sync_budget():
    ss["budget_pct"] = ss["budget_w"]


def _sync_must():
    inp = ss["inputs"].copy()
    inp["Must-have"] = inp["Name"].isin(set(ss["must_w"]))
    ss["inputs"] = inp


left, right = st.columns([2, 3])
with left:
    with st.container(border=True):
        st.slider("Your budget this week (% of the ideal order)", 0, 150, value=int(ss["budget_pct"]), step=5,
                  key="budget_w", on_change=_sync_budget)
        st.markdown(f"### RM {ctx['budget_rm']:,.0f}")
        st.caption(f"Ideal order (no cash limit): RM {ideal['ideal_rm']:,.0f}")
        st.progress(min(1.0, tot["spent_rm"] / ctx["budget_rm"]) if ctx["budget_rm"] > 0 else 0.0,
                    text=f"Order total RM {tot['spent_rm']:,.0f} · RM {tot['unspent_rm']:,.0f} left")
    st.multiselect("Must-have items (protected first)", ss["inputs"]["Name"].tolist(),
                   default=ss["inputs"].loc[ss["inputs"]["Must-have"], "Name"].tolist(), key="must_w",
                   on_change=_sync_must)
with right:
    c = st.columns(3)
    c[0].markdown(ui.kpi("Expected lost margin", f"RM {tot['exp_lost_margin_rm']:,.0f}", "with this order"),
                  unsafe_allow_html=True)
    c[1].markdown(ui.kpi("Expected waste", f"RM {tot['exp_waste_rm']:,.0f}", "perishables left at expiry"),
                  unsafe_allow_html=True)
    c[2].markdown(ui.kpi("Must-have units short", f"{tot['must_have_short_units']:,.1f}", "expected"),
                  unsafe_allow_html=True)
    if ctx["more"]:
        st.info(f"With RM {ctx['more_rm']:,.0f} more you'd add: "
                + ", ".join(f"{q:,.0f} × {n}" for n, q in ctx["more"]))
    else:
        st.success("Your budget covers the full ideal order.")
    st.caption("Expected values are ESTIMATES from the AI forecast and your placeholder costs, not results.")

show = alloc.copy()
show["unit_price"] = ctx["inputs"].set_index("product").loc[alloc["product"], "Unit cost (RM)"].to_numpy()
st.dataframe(
    show[["name", "must_have", "ideal_qty", "qty", "unit_price", "spend_rm", "exp_short_units", "cut_reason"]],
    hide_index=True, use_container_width=True,
    column_config={
        "name": st.column_config.TextColumn("Product"),
        "must_have": st.column_config.CheckboxColumn("Must-have"),
        "ideal_qty": st.column_config.NumberColumn("Ideal qty", format="%d"),
        "qty": st.column_config.NumberColumn("LARIS qty", format="%d"),
        "unit_price": st.column_config.NumberColumn("Unit cost (RM)", format="%.2f"),
        "spend_rm": st.column_config.NumberColumn("Total (RM)", format="%.0f"),
        "exp_short_units": st.column_config.NumberColumn("Expected short", format="%.1f"),
        "cut_reason": st.column_config.TextColumn("Why cut"),
    })
st.caption("How LARIS chooses: each extra pack is worth (margin, plus a goodwill cost for must-haves) × the chance "
           "it sells, minus its cost × the chance it's left over or expires. LARIS buys packs in order of value per "
           "ringgit until the budget runs out.")
order = alloc[alloc["qty"] > 0][["name", "qty", "spend_rm"]].rename(columns={"name": "product", "spend_rm": "total_rm"})
st.download_button("Download order list (CSV)", order.to_csv(index=False).encode("utf-8"), "laris_order.csv",
                   "text/csv", help="Nothing is sent anywhere; share the file with your supplier yourself.")
