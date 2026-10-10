"""I · Invest Within Budget: the order list for the cash or supplier credit you have, what it protects first, what was
cut and why, and what a little more cash would add. Quantities come from LARIS's optimiser (inventory.allocate_budget
via the shared context); the owner's own changes are kept next to LARIS's suggestion."""
from html import escape

import streamlit as st

import laris_core as core
import laris_fx as fx
import laris_ui as ui
import planning

HERE = "views/laris.py"


def _set_budget(v, note=None):
    st.session_state["budget_rm"] = max(0.0, float(round(v / 10) * 10))
    ui.flash(note or f"Budget set to {ui.money(st.session_state['budget_rm'])}.")


def _row(ctx, r, deadline):
    icon, name = ui.split_name(r.name)
    with st.container(key=f"row_{ui.safe_key(r.product)}"):
        a, b, c, d = st.columns([3, 2, 3.3, 1.3], vertical_alignment="center")
        a.markdown(f'<span class="lr-name">{escape(icon)} {escape(name)}</span><br>{ui.action_chip(r.action)}'
                   f'{ui.must_chip(r.must_have)}', unsafe_allow_html=True)
        mine = f'<br><span class="lr-muted">your change · LARIS suggests {r.qty:,.0f}</span>' if r.adjusted else ""
        b.markdown(f'<div class="lr-qty">{r.order_qty:,.0f} <span>· usually {r.usual:,.0f} · {ui.money(r.order_rm)}'
                   f'</span></div>{mine}', unsafe_allow_html=True)
        extra = f" {escape(deadline)}" if deadline and r.action == "RESTOCK" else ""
        impact = f'<span class="lr-impact">{escape(r.impact_txt)}</span><br>' if r.impact_txt else ""
        c.markdown(f'{impact}<span class="lr-muted">{escape(r.risk)}{extra}</span>', unsafe_allow_html=True)
        with d:
            ui.why_button(r.product, HERE, key=f"rc_why_{r.product}")
            with st.popover("Adjust", width="stretch"):
                k = f"rc_adj_{r.product}"
                st.number_input(f"Quantity for {name}", min_value=0.0, step=float(r.pack_size), format="%.0f",
                                value=float(r.order_qty), key=k)
                st.button("Use this quantity", key=f"rc_set_{r.product}", type="primary", width="stretch",
                          on_click=lambda p=r.product, k=k, n=name: (ui.set_qty_from(p, k), ui.flash(
                              f"{n}: this week's order is now {st.session_state[k]:,.0f} units.")))
                q1, q2 = st.columns(2)
                q1.button(f"Full need ({r.ideal:,.0f})", key=f"rc_full_{r.product}", on_click=ui.set_qty_value,
                          args=(r.product, r.ideal), width="stretch")
                q2.button(f"Usual ({r.usual:,.0f})", key=f"rc_usual_{r.product}", on_click=ui.set_qty_value,
                          args=(r.product, r.usual), width="stretch")
                if r.adjusted:
                    st.button(f"Back to LARIS's {r.qty:,.0f}", key=f"rc_clr_{r.product}", on_click=ui.clear_qty,
                              args=(r.product,), width="stretch")


def render(ctx):
    ss = st.session_state
    plan, budget, ideal = ctx["plan"], ctx["budget_rm"], ctx["ideal_rm"]
    ui.first_view("tool:I")
    order_rm = ctx["order_rm"]
    left = budget - order_rm

    # ---------------- budget meter ----------------
    must_rm = float(plan.loc[plan["must_have"], "order_rm"].sum())
    other_rm = order_rm - must_rm
    scale = max(budget, order_rm, ideal, 1.0)
    status = f"{ui.money(left)} left" if left >= -0.5 else f"over budget by {ui.money(-left)}"
    with st.container(border=True, key="card_in_budget"):
        bcol, _ = st.columns([1, 2])
        bcol.number_input("Budget this week (RM, cash or supplier credit)", min_value=0.0, step=10.0, format="%.0f",
                          **ui.bind("in_budget", "budget_rm"))
        a, b = st.columns([1, 2.2], vertical_alignment="bottom")
        with a:
            fx.number(ui.money(order_rm), "in_order", label=f"Order total {ui.money(order_rm)}", size="30px",
                      color="#174D3A")
        b.markdown(f'<div class="lr-big"><small>order{ui.delta_chip("in_order", order_rm)} of your {ui.money(budget)} '
                   f'budget (cash or supplier credit) · {escape(status)}</small></div>', unsafe_allow_html=True)
        uncovered = max(0.0, ideal - order_rm)
        fx.meter([(must_rm / scale, "#174D3A"), (other_rm / scale, "#7FA392"),
                  (uncovered / scale, "repeating-linear-gradient(-45deg, #E9B98A 0 4px, #FCEBCF 4px 8px)")],
                 "in_budget_meter", marker=budget / scale, height=12,
                 label=f"Must-haves {ui.money(must_rm)}, other products {ui.money(other_rm)}, budget {ui.money(budget)}, "
                       f"full recommended order {ui.money(ideal)}")
        st.markdown(f'<div class="lr-meter-legend"><span>■ Must-haves {ui.money(must_rm)}</span>'
                    f'<span>■ Other products {ui.money(other_rm)}</span>'
                    + (f'<span>▨ Not covered {ui.money(uncovered)}</span>' if uncovered > 0.5 else "")
                    + f'<span>│ Budget {ui.money(budget)}</span></div>', unsafe_allow_html=True)
        notes = []
        if ctx["budget_limited"]:
            notes.append(f"Your budget doesn't cover the full recommended order ({ui.money(ideal)}); this is the best "
                         "order within it.")
        if plan["adjusted"].any():
            notes.append(f"Includes your changes to {int(plan['adjusted'].sum())} product(s).")
        notes.append("RM impacts compare LARIS's quantity with reordering last week's sales: estimates, not guaranteed "
                     "savings. Send the order from S · Send & Sync.")
        st.caption(" ".join(notes))
        cols = st.columns(4)
        for col, (text, value) in zip(cols, [("−RM 50", budget - 50), ("+RM 50", budget + 50),
                                             ("75% of full", ideal * 0.75), ("Cover the full order", ideal)]):
            col.button(text, key=f"rc_b_{text}", on_click=_set_budget, args=(value,), width="stretch")

    # ---------------- how the budget is spent | what a little more cash adds ----------------
    left, right = st.columns([1.35, 1], gap="medium")
    with left.container(border=True, key="card_in_alloc"):
        st.markdown(f'{ui.decision_badge("HOW THE BUDGET IS SPENT")}<span class="lr-muted">funded vs cut, must-haves '
                    "first</span>", unsafe_allow_html=True)
        chart = ui.allocation_chart(ctx)
        if chart is None:
            st.markdown(ui.empty("✓", "Nothing to order this week"), unsafe_allow_html=True)
        else:
            st.altair_chart(chart, width="stretch")
    a = b = right
    with a.container(border=True, key="card_in_extra"):
        extra = st.number_input("What would extra cash add? (RM)", min_value=10.0, step=10.0, format="%.0f",
                                **ui.sticky("rc_extra", 50.0))
        names = dict(zip(plan["product"], plan["name"]))
        sc = core.budget_scenario(ctx["items"], ctx["alloc"], budget, extra, names, ss["strategy"] == "essentials")
        if sc["added"]:
            st.markdown(f"With **{ui.money(extra)} more**, LARIS would add "
                        + ", ".join(f"**{q:,.0f} × {ui.split_name(n)[1]}**" for n, q in sc["added"]) + ".")
            st.markdown(ui.label("ESTIMATED", "estimated") + f'<span class="lr-muted">About {ui.money(max(0, sc["saves"]))} '
                        "less lost profit and waste (same forecast; not guaranteed).</span>", unsafe_allow_html=True)
            st.button(f"Use a budget of {ui.money(budget + extra)}", key="rc_use_extra", type="primary",
                      on_click=_set_budget, args=(budget + extra,))
        else:
            st.caption("Your budget already covers the full recommended order; more cash wouldn't change it.")
    with b.container(border=True, key="card_in_strategy"):
        keys = list(planning.STRATEGIES)
        ss["rc_strategy"] = ss["strategy"]
        st.radio("When cash is short, LARIS should…", keys, key="rc_strategy",
                 format_func=lambda s: planning.STRATEGIES[s] + (" (recommended)" if s == "essentials" else ""),
                 on_change=lambda: ss.update(strategy=ss["rc_strategy"]))
        cmp = planning.strategy_compare(ctx)
        same = all(abs(cmp["essentials"][f] - cmp["value"][f]) < 0.5 for f in ("spent", "loss"))
        st.caption(("At this budget both choose the same order. " if same else "")
                   + f"Estimated lost profit + waste: essentials first {ui.money(cmp['essentials']['loss'])}, best value "
                     f"per ringgit {ui.money(cmp['value']['loss'])}.")

    # ---------------- top-ups live in A ----------------
    al = planning.alert_table(ctx)
    urgent = al[al["level"] == "URGENT"] if len(al) else al
    if len(urgent):
        x, y = st.columns([5, 1.3], vertical_alignment="center")
        x.markdown(f'<div class="lr-insight urgent">{ui.status_chip("URGENT")}{len(urgent)} product(s) may run out before '
                   "an order placed today can arrive. Plan wholesaler top-ups in A.</div>", unsafe_allow_html=True)
        with y:
            ui.tool_button("A", "Open A", key="in_to_a")

    # ---------------- the order list ----------------
    ui.section("This week's order", "Grouped by what LARIS suggests. Adjust any quantity; LARIS's own suggestion stays "
                                    "visible.")
    pick = ui.choice("Show", ["All"] + [planning.ACTION_LABEL[x] for x in ui.ACTIONS], "rc_filter", "All", keep=True)
    deadlines = planning.look_ahead_table(ctx).set_index("product")["deadline"].to_dict()
    for action in ui.ACTIONS:
        label = planning.ACTION_LABEL[action]
        group = plan[plan["action"] == action]
        if pick not in ("All", label) or group.empty:
            continue
        if action == "MAINTAIN" and pick == "All":
            with st.expander(f"{label} ({len(group)}): {planning.ACTION_HELP[action]}"):
                for r in group.itertuples():
                    _row(ctx, r, deadlines.get(r.product))
            continue
        ui.section(f"{label} ({len(group)})", planning.ACTION_HELP[action])
        for r in group.itertuples():
            _row(ctx, r, deadlines.get(r.product))
    if pick != "All" and plan[plan["action"].map(planning.ACTION_LABEL) == pick].empty:
        st.markdown(ui.empty("✓", f"No products in '{pick}' this week"), unsafe_allow_html=True)

    # ---------------- what was cut and why ----------------
    bd = planning.budget_breakdown(ctx)
    cut = bd["cut"]
    ui.section("What the budget cut, and why",
               f"{len(bd['full'])} products fully covered · {int((cut['status'] == 'Reduced').sum())} reduced · "
               f"{int((cut['status'] == 'Left out').sum())} left out.")
    if cut.empty:
        st.markdown(ui.empty("✓", "Every product gets its full recommended amount"), unsafe_allow_html=True)
    for r in cut.itertuples():
        st.markdown(f'<div class="lr-insight {"warning" if r.status == "Left out" else "info"}">'
                    f'{ui.chip(r.status, "lr-s-soon" if r.status == "Left out" else "lr-s-info")}'
                    f'<span><b>{escape(ui.split_name(r.name)[1])}</b>: {r.qty:,.0f} of {r.ideal:,.0f} needed. '
                    f'<span class="lr-muted">{escape(r.reason)}</span></span></div>', unsafe_allow_html=True)
    bs = ctx["metrics"].get("budget_simulation")
    t = bs["totals_by_budget"].get("75%", {}) if bs else {}
    laris, usual = t.get("LARIS (AI forecast + optimiser)"), t.get("Usual: split cash by sales value")
    if laris and usual and usual["lost_margin_plus_waste_rm"] > 0:
        cut_pct = 1 - laris["lost_margin_plus_waste_rm"] / usual["lost_margin_plus_waste_rm"]
        st.markdown(ui.label("BACKTEST", "simulated") + f'<span class="lr-muted">Tested on past weeks for '
                    f"{len(bs['stores'])} stores at 75% of the cash needed, ordering this way lost {abs(cut_pct):.0%} "
                    f"{'less' if cut_pct >= 0 else 'more'} profit and stock to waste than splitting the cash by last "
                    "month's sales. A backtest estimate, not measured savings. Details on Proof.</span>",
                    unsafe_allow_html=True)
    else:
        st.caption("Backtest not available for this data.")
