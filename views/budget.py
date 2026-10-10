import pandas as pd
import streamlit as st

import laris_core as core
import laris_ui as ui
import planning

ss = st.session_state
ctx = ss["ctx"]
ui.require_plan(ctx)
budget, ideal, spent = ctx["budget_rm"], ctx["ideal_rm"], ctx["totals"]["spent_rm"]


def _set_budget(v):
    ss["budget_rm"] = max(0.0, float(round(v / 10) * 10))


# ---------------- A. budget control ----------------
k = st.columns(3)
k[0].markdown(ui.kpi("AVAILABLE BUDGET", ui.money(budget), "set in the Budget box at the top"), unsafe_allow_html=True)
k[1].markdown(ui.kpi("FULL RECOMMENDED ORDER", ui.money(ideal), "what LARIS would buy with no cash limit"),
              unsafe_allow_html=True)
gap = ideal - budget
k[2].markdown(ui.kpi("SHORTFALL" if gap > 0.5 else "ROOM TO SPARE", ui.money(abs(gap)),
                     "budget is less than the full order" if gap > 0.5 else "budget covers the full order",
                     "warn" if gap > 0.5 else "good"), unsafe_allow_html=True)
st.write("")
for col, (text, value) in zip(st.columns(5), [("− RM 50", budget - 50), ("+ RM 50", budget + 50),
                                              ("50% of full", ideal * 0.5), ("75% of full", ideal * 0.75),
                                              ("Cover the full order", ideal)]):
    col.button(text, key=f"bq_{text}", on_click=_set_budget, args=(value,), use_container_width=True)

# ---------------- B. recommended allocation ----------------
bd = planning.budget_breakdown(ctx)
ui.section("How LARIS spends it", "When cash is short, the order can't cover every product's ideal amount. This is "
                                  "the best order within your budget.")
cut = bd["cut"]
k = st.columns(4)
k[0].markdown(ui.kpi("RECOMMENDED ORDER", ui.money(spent), f"{ui.money(budget - spent)} of the budget left"),
              unsafe_allow_html=True)
k[1].markdown(ui.kpi("FULLY COVERED", f"{len(bd['full'])} products", "get everything they need"), unsafe_allow_html=True)
k[2].markdown(ui.kpi("REDUCED", f"{int((cut['status'] == 'Reduced').sum())} products", "get part of what they need"),
              unsafe_allow_html=True)
k[3].markdown(ui.kpi("LEFT OUT", f"{int((cut['status'] == 'Left out').sum())} products", "nothing this week"),
              unsafe_allow_html=True)
if ctx["plan"]["adjusted"].any():
    st.caption(f"With your own changes the order is {ui.money(ctx['order_rm'])}; the figures above are LARIS's "
               "recommendation before your changes.")

# ---------------- C. strategy ----------------
ui.section("How should LARIS choose?", "Both options are real settings of the same optimiser; the order on every page "
                                       "follows your choice.")
cmp = planning.strategy_compare(ctx)
keys = list(planning.STRATEGIES)
ss["strategy_w"] = ss["strategy"]
st.radio("Strategy", keys, key="strategy_w", horizontal=True, label_visibility="collapsed",
         format_func=lambda s: planning.STRATEGIES[s] + (" (recommended)" if s == "essentials" else ""),
         on_change=lambda: ss.update(strategy=ss["strategy_w"]))
st.dataframe(pd.DataFrame([{"Strategy": planning.STRATEGIES[s], "Order cost (RM)": v["spent"],
                            "Expected lost profit + waste (RM)": v["loss"],
                            "Must-have units short (expected)": v["must_short"]} for s, v in cmp.items()]),
             hide_index=True, use_container_width=True,
             column_config={"Order cost (RM)": st.column_config.NumberColumn(format="%.0f"),
                            "Expected lost profit + waste (RM)": st.column_config.NumberColumn(format="%.0f"),
                            "Must-have units short (expected)": st.column_config.NumberColumn(format="%.1f")})
if abs(cmp["essentials"]["spent"] - cmp["value"]["spent"]) < 0.5 and abs(cmp["essentials"]["loss"] - cmp["value"]["loss"]) < 0.5:
    st.info("At this budget both strategies choose the same order. Try a smaller budget to see them differ.")
st.caption("ESTIMATES from the same forecast. 'Protect essentials first' fills must-haves up to expected demand before "
           "anything else; 'Best value per ringgit' can leave a must-have short if other products are worth more per RM.")
a, b = st.columns(2)
a.markdown("**Explore a larger budget**: see the next section.")
b.markdown(ui.label("NOT AVAILABLE YET", "planned") + "**Split the order across two deliveries.** LARIS doesn't know "
           "your delivery fees or a second delivery date, so it can't compare this reliably yet.", unsafe_allow_html=True)

# ---------------- D. what would extra cash do? ----------------
ui.section("What would a little more cash protect?")
extra = st.number_input("Extra cash (RM)", min_value=10.0, value=50.0, step=10.0, format="%.0f", key="extra_rm")
names = dict(zip(ctx["plan"]["product"], ctx["plan"]["name"]))
sc = core.budget_scenario(ctx["items"], ctx["alloc"], budget, extra, names, ss["strategy"] == "essentials")
if sc["added"]:
    st.markdown(f"With **{ui.money(extra)} more**, LARIS would add: "
                + ", ".join(f"**{q:,.0f} × {n}**" for n, q in sc["added"]) + ".")
    st.markdown(ui.label("ESTIMATED", "estimated") + "Estimated additional lost profit and waste avoided: "
                f"**{ui.money(max(0, sc['saves']))}** (from the same forecast; not guaranteed).", unsafe_allow_html=True)
    st.button(f"Use a budget of {ui.money(budget + extra)}", on_click=_set_budget, args=(budget + extra,))
else:
    st.success("Your budget already covers the full recommended order; more cash wouldn't change it.")

# ---------------- E. what was cut and why ----------------
ui.section("Reduced or left out", "Nothing is hidden: every product that gets less than it needs is listed here.")
if cut.empty:
    st.success("Every product gets its full recommended amount.")
else:
    st.dataframe(cut[["name", "status", "qty", "ideal", "reason"]], hide_index=True, use_container_width=True,
                 column_config={"name": "Product", "status": "Status",
                                "qty": st.column_config.NumberColumn("In the order", format="%.0f"),
                                "ideal": st.column_config.NumberColumn("Needed", format="%.0f"),
                                "reason": st.column_config.TextColumn("Why", width="large")})

# ---------------- G. does it work? (pipeline replay) ----------------
bs = ctx["metrics"].get("budget_simulation")
t = bs["totals_by_budget"].get("75%", {}) if bs else {}
laris, usual = t.get("LARIS (AI forecast + optimiser)"), t.get("Usual: split cash by sales value")
ui.section("Does this approach work?")
if laris and usual and usual["lost_margin_plus_waste_rm"] > 0:
    cut_pct = 1 - laris["lost_margin_plus_waste_rm"] / usual["lost_margin_plus_waste_rm"]
    st.markdown(ui.label("SIMULATED", "simulated") + f"In a replay of past weeks for {len(bs['stores'])} stores, with "
                f"75% of the cash each order needed, ordering this way lost <b>{abs(cut_pct):.0%} "
                f"{'less' if cut_pct >= 0 else 'more'}</b> profit and stock to waste than splitting the cash by last "
                f"month's sales ({laris['must_have_short_units']:,.0f} vs {usual['must_have_short_units']:,.0f} must-have "
                "units short). Real past sales, simulated stock, placeholder costs: a simulation, not measured savings.",
                unsafe_allow_html=True)
else:
    st.caption("The budget replay hasn't been run for this data (pipeline.py --sim-stores).")
