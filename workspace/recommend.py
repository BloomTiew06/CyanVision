"""R · Recommend: what to do this week. The order list grouped by action, urgent top-ups, and budget trade-offs."""
from html import escape

import streamlit as st

import laris_core as core
import laris_ui as ui
import planning
import store

HERE = "views/laris.py"


def _row(ctx, r, deadline):
    with st.container(key=f"row_{r.Index}"):
        a, b, c, d = st.columns([3, 2, 3.3, 1.3], vertical_alignment="center")
        a.markdown(f'<span class="lr-name">{escape(r.name)}</span><br>{ui.action_chip(r.action)}'
                   f'{ui.must_chip(r.must_have)}{ui.cat_chip(r.group)}', unsafe_allow_html=True)
        mine = f'<br><span class="lr-muted">your change · LARIS suggests {r.qty:,.0f}</span>' if r.adjusted else ""
        b.markdown(f'<div class="lr-qty">{r.order_qty:,.0f} <span>· usually {r.usual:,.0f} · {ui.money(r.order_rm)}'
                   f'</span></div>{mine}', unsafe_allow_html=True)
        extra = f" {escape(deadline)}" if deadline and r.action == "RESTOCK" else ""
        impact = f'<span class="lr-impact">{escape(r.impact_txt)}</span><br>' if r.impact_txt else ""
        c.markdown(f'{impact}<span class="lr-muted">{escape(r.risk)}{extra}</span>', unsafe_allow_html=True)
        with d:
            ui.why_button(r.product, HERE, key=f"rc_why_{r.product}")
            with st.popover("Adjust", use_container_width=True):
                k = f"rc_adj_{r.product}"
                st.number_input(f"Quantity for {r.name}", min_value=0.0, step=float(r.pack_size), format="%.0f",
                                value=float(r.order_qty), key=k)
                st.button("Use this quantity", key=f"rc_set_{r.product}", on_click=ui.set_qty_from,
                          args=(r.product, k), type="primary", use_container_width=True)
                q1, q2 = st.columns(2)
                q1.button(f"Full need ({r.ideal:,.0f})", key=f"rc_full_{r.product}", on_click=ui.set_qty_value,
                          args=(r.product, r.ideal), use_container_width=True)
                q2.button(f"Usual ({r.usual:,.0f})", key=f"rc_usual_{r.product}", on_click=ui.set_qty_value,
                          args=(r.product, r.usual), use_container_width=True)
                if r.adjusted:
                    st.button(f"Back to LARIS's {r.qty:,.0f}", key=f"rc_clr_{r.product}", on_click=ui.clear_qty,
                              args=(r.product,), use_container_width=True)


def _toggle_handled(k, p):
    store.update("alerts", k, {"status": "Resolved" if st.session_state[f"rc_done_{p}"] else "New",
                               "at": store.now()})


def render(ctx):
    plan = ctx["plan"]
    left = ctx["budget_rm"] - ctx["order_rm"]
    status = f"RM {left:,.0f} left" if left >= -0.5 else f"over by RM {-left:,.0f}"
    st.markdown(f'<div class="lr-big">Order {ui.money(ctx["order_rm"])} <small>of your {ui.money(ctx["budget_rm"])} '
                f"budget · {status}</small></div>", unsafe_allow_html=True)
    ui.budget_slider(ctx, "rc_budget")
    notes = []
    if ctx["budget_limited"]:
        notes.append(f"Your budget doesn't cover the full recommended order ({ui.money(ctx['ideal_rm'])}); this is the "
                     "best order within it. See 'Budget trade-offs' below.")
    if plan["adjusted"].any():
        notes.append(f"Includes your changes to {int(plan['adjusted'].sum())} product(s).")
    st.markdown(f'<p class="lr-muted">{" ".join(notes)} RM impact compares LARIS\'s quantity with reordering last '
                "week's sales: an estimate, not guaranteed savings. Send the order from <b>Orders</b>.</p>",
                unsafe_allow_html=True)

    # urgent: may run out before an order placed today can arrive
    al = planning.alert_table(ctx)
    muted = set(store.get("prefs", {}).get("muted", []))
    urgent = al[(al["level"] == "URGENT") & ~al["product"].isin(muted)] if len(al) else al
    if len(urgent):
        handled = store.get("alerts", {})
        ui.section("Act today", "These may run out before an order placed today can arrive.")
        for r in urgent.itertuples():
            k = f"{ctx['ref']}|{r.product}"
            done = handled.get(k, {}).get("status") == "Resolved"
            a, b = st.columns([5, 1.3], vertical_alignment="center")
            tip = (f"top up about {r.bridge_qty:,.0f} from a wholesaler today (at your usual cost about "
                   f"{ui.money(r.bridge_qty * r.unit_cost)}; LARIS can't see wholesaler prices)" if r.choice == "topup"
                   else "a short gap may be acceptable; make sure it's in this order")
            a.markdown(f'<div class="lr-insight {"info" if done else "urgent"}">{ui.must_chip(r.must_have)}'
                       f'<b>{escape(r.name)}</b>: stock lasts about {r.cover:.1f} days, delivery takes {r.lead} day(s). '
                       f'Suggestion: {escape(tip)}.</div>', unsafe_allow_html=True)
            b.toggle("Handled", value=done, key=f"rc_done_{r.product}", on_change=_toggle_handled, args=(k, r.product))

    # the order list, grouped by action
    pick = st.segmented_control("Show", ["All"] + [planning.ACTION_LABEL[a] for a in ui.ACTIONS],
                                label_visibility="collapsed", **ui.sticky("rc_filter", "All")) or "All"
    cat = ui.category_filter(ctx, "rc_cat")
    shown = ui.in_category(plan, cat)
    deadlines = planning.look_ahead_table(ctx).set_index("product")["deadline"].to_dict()
    for action in ui.ACTIONS:
        label = planning.ACTION_LABEL[action]
        group = shown[shown["action"] == action]
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
    if shown.empty or (pick != "All" and shown[shown["action"].map(planning.ACTION_LABEL) == pick].empty):
        st.info("No products match these filters this week.")

    with st.expander("Budget trade-offs: what was cut, strategy, and what more cash would add"):
        _budget(ctx)


def _set_budget(v):
    st.session_state["budget_rm"] = max(0.0, float(round(v / 10) * 10))


def _budget(ctx):
    ss = st.session_state
    budget, ideal = ctx["budget_rm"], ctx["ideal_rm"]
    for col, (text, value) in zip(st.columns(4), [("− RM 50", budget - 50), ("+ RM 50", budget + 50),
                                                  ("75% of full", ideal * 0.75), ("Cover the full order", ideal)]):
        col.button(text, key=f"rc_b_{text}", on_click=_set_budget, args=(value,), use_container_width=True)
    bd = planning.budget_breakdown(ctx)
    cut = bd["cut"]
    st.markdown(f"**{len(bd['full'])}** products fully covered · **{int((cut['status'] == 'Reduced').sum())}** reduced · "
                f"**{int((cut['status'] == 'Left out').sum())}** left out.")
    if len(cut):
        st.dataframe(cut[["name", "status", "qty", "ideal", "reason"]], hide_index=True, use_container_width=True,
                     column_config={"name": "Product", "status": "Status",
                                    "qty": st.column_config.NumberColumn("In the order", format="%d"),
                                    "ideal": st.column_config.NumberColumn("Needed", format="%d"),
                                    "reason": st.column_config.TextColumn("Why", width="large")})
    keys = list(planning.STRATEGIES)
    ss["rc_strategy"] = ss["strategy"]
    st.radio("How should LARIS choose when cash is short?", keys, key="rc_strategy", horizontal=True,
             format_func=lambda s: planning.STRATEGIES[s] + (" (recommended)" if s == "essentials" else ""),
             on_change=lambda: ss.update(strategy=ss["rc_strategy"]))
    cmp = planning.strategy_compare(ctx)
    same = all(abs(cmp["essentials"][f] - cmp["value"][f]) < 0.5 for f in ("spent", "loss"))
    st.caption(("At this budget both strategies choose the same order. " if same else "")
               + "Estimated lost profit + waste: essentials first "
               f"{ui.money(cmp['essentials']['loss'])}, best value per ringgit {ui.money(cmp['value']['loss'])}. "
               "Splitting the order across two deliveries isn't available yet: LARIS doesn't know your delivery fees.")
    extra = st.number_input("What would extra cash add? (RM)", min_value=10.0, step=10.0, format="%.0f",
                            **ui.sticky("rc_extra", 50.0))
    names = dict(zip(ctx["plan"]["product"], ctx["plan"]["name"]))
    sc = core.budget_scenario(ctx["items"], ctx["alloc"], budget, extra, names, ss["strategy"] == "essentials")
    if sc["added"]:
        st.markdown(f"With **{ui.money(extra)} more**: " + ", ".join(f"{q:,.0f} × {n}" for n, q in sc["added"])
                    + f". {ui.label('ESTIMATED', 'estimated')}about {ui.money(max(0, sc['saves']))} less lost profit "
                    "and waste.", unsafe_allow_html=True)
    else:
        st.caption("Your budget already covers the full recommended order.")
    bs = ctx["metrics"].get("budget_simulation")
    t = bs["totals_by_budget"].get("75%", {}) if bs else {}
    laris, usual = t.get("LARIS (AI forecast + optimiser)"), t.get("Usual: split cash by sales value")
    if laris and usual and usual["lost_margin_plus_waste_rm"] > 0:
        cut_pct = 1 - laris["lost_margin_plus_waste_rm"] / usual["lost_margin_plus_waste_rm"]
        st.markdown(ui.label("BACK-TEST", "simulated") + f'<span class="lr-muted">On past weeks of sales for '
                    f"{len(bs['stores'])} stores at 75% of the cash needed, ordering this way lost {abs(cut_pct):.0%} "
                    f"{'less' if cut_pct >= 0 else 'more'} profit and stock to waste than splitting the cash by last "
                    "month's sales. A back-test with estimated costs, not measured savings in your shop.</span>",
                    unsafe_allow_html=True)
