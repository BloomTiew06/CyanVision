"""L · Look Ahead: the 7-day demand forecast per product, what's rising, and how much extra to stock before it does.
Every number comes from the shared context (planning.look_ahead_table / lookup_table); this file only draws them."""
from html import escape

import pandas as pd
import streamlit as st

import laris_ui as ui
import planning
import store

HERE = "views/laris.py"
OPTION = {"full": "Stock up fully", "part": "Stock up partly", "skip": "Usual order"}
SHORT = {"full": "Full", "part": "Part", "skip": "Usual"}


def _apply(p, name, qty):
    ui.set_qty_value(p, qty)
    ui.flash(f"{ui.split_name(name)[1]}: this week's order is now {qty:,.0f} units.")


def _spike_card(r, as_of, is_mock, anim, i):
    icon, name = ui.split_name(r.name)
    peak = f"{r.deadline}" if r.deadline else ""
    return (f'<div class="lr-card{" lr-in" if anim else ""}" style="animation-delay:{i * 40}ms">'
            f'<div class="lr-pc"><div class="lr-avatar" aria-hidden="true">{escape(icon)}</div><div>'
            f'<span class="lr-name">{escape(name)}</span><br>{ui.chip(f"{r.change:+.0%} next week", "lr-s-ok", "▲")}'
            f'<div class="figs">Expected <b>{r.fc7:,.0f}</b> units (sold {r.last7:,.0f} last week)</div>'
            f'<div class="meta">{escape(peak)}</div></div></div></div>')


def render(ctx):
    ss = st.session_state
    week, is_mock = ctx["week"], ctx.get("is_mock", False)
    as_of, end = week["as_of"], week["end"]
    anim = ui.first_view("tool:L")
    tbl = planning.look_ahead_table(ctx, ss.get("la_rank") or "Biggest increase")
    plan = ctx["plan"].set_index("product")
    events = [e for e in store.get("events", []) if pd.Timestamp(e["start"]) <= end and pd.Timestamp(e["end"]) >= as_of]

    k = st.columns(4)
    k[0].markdown(ui.kpi("Selling more", " products", "next 7 days vs last 7", None,
                         int((tbl["trend"] == "Growing").sum()), "la_up"), unsafe_allow_html=True)
    k[1].markdown(ui.kpi("Selling less", " products", "next 7 days vs last 7", None,
                         int((tbl["trend"] == "Declining").sum()), "la_down"), unsafe_allow_html=True)
    k[2].markdown(ui.kpi("Less certain", " products", "wide range or little history", "warn" if tbl["uncertain"].any()
                         else None, int(tbl["uncertain"].sum()), "la_unc"), unsafe_allow_html=True)
    k[3].markdown(ui.kpi("Your events this week", "", "notes only; not used by the forecast", None, len(events),
                         "la_ev"), unsafe_allow_html=True)

    keep = ui.filter_bar("la", ctx)
    view = keep(tbl)
    if view is None or view.empty:
        st.markdown(ui.empty("🔍", "No product matches", "Clear the search or the category filter."),
                    unsafe_allow_html=True)
        return

    # ---------------- the forecast: table + chart side by side ----------------
    ui.stage(1, "The forecast", "predicted units per day for the next 7 days, from the AI model")
    grid, day_cols = planning.forecast_grid(ctx)
    grid = grid[grid["product"].isin(set(view["product"]))]
    names = dict(zip(grid["product"], grid["name"]))
    left, right = st.columns([1.45, 1], gap="medium")
    with right.container(border=True, key="card_la_chart"):
        p = st.selectbox("Product", list(names), format_func=lambda x: ui.split_name(names[x])[1],
                         label_visibility="collapsed", **ui.sticky("la_product", list(names)[0]))
        if p not in names:
            p = list(names)[0]
        rng = ui.forecast_range(ctx, p)
        st.markdown(f'{ui.prediction_badge()}<span class="lr-range">{escape(rng or "–")}<small>units next 7 days</small>'
                    "</span>", unsafe_allow_html=True)
        reveal = st.toggle("Backtest: compare with actual sales", key="la_reveal",
                           help="For a past week the actual sales are known: show them next to the forecast to see how "
                                "close it was.")
        chart, note = ui.forecast_chart(ctx, p, height=220, reveal=reveal)
        st.altair_chart(chart, width="stretch")
        if reveal:
            st.markdown(ui.reveal_note(ctx, p), unsafe_allow_html=True)
        st.markdown('<div class="lr-crumb" style="margin-top:6px">What moves this week (AI what-if)</div>'
                    + ui.drivers(ctx, p), unsafe_allow_html=True)
        st.caption(note)
        ui.why_button(p, HERE, key="la_why", label="Why this recommendation?")
    with left.container(border=True, key="card_la_heat"):
        st.markdown(f'{ui.prediction_badge("7-DAY DEMAND FORECAST")}<span class="lr-muted">darker = busier day for that '
                    "product</span>", unsafe_allow_html=True)
        st.markdown(ui.heat_table(grid, day_cols, ctx, selected=p), unsafe_allow_html=True)

    # ---------------- decisions: what's rising and how much extra to stock ----------------
    ui.stage(2, "What to do about it", "products selling more, and how much extra to order")
    rising = view[view["trend"] == "Growing"].sort_values("change", ascending=False).head(6)
    if not rising.empty:
        cols = st.columns(3)
        for i, r in enumerate(rising.itertuples()):
            cols[i % 3].markdown(_spike_card(r, as_of, is_mock, anim, i), unsafe_allow_html=True)
    cands = view[view["options"].map(len) > 0]
    if cands.empty and rising.empty:
        st.markdown(ui.empty("✓", "Nothing needs extra stock", "Your usual order covers expected demand this week."),
                    unsafe_allow_html=True)
    keys = []
    grid_cols = st.columns(2, gap="medium")
    for i, r in enumerate(cands.itertuples()):
        key = f"card_la_{ui.safe_key(r.product)}"
        keys.append(key)
        cost = float(plan.at[r.product, "unit_cost"])
        icon, name = ui.split_name(r.name)
        with grid_cols[i % 2].container(border=True, key=key):
            st.markdown(f'{ui.decision_badge()}<span class="lr-name">{escape(name)}</span> {ui.action_chip(r.action)}<br>'
                        f'<span class="lr-muted">Expected {r.fc7:,.0f} next week ({r.change:+.0%} vs last week). '
                        f'{escape(r.deadline)}</span>', unsafe_allow_html=True)
            st.markdown(f'{ui.product_spark(ctx, r.product, 260, 44)}<span class="lr-impact">Recommended: '
                        f'{OPTION[r.recommended].lower()}.</span> <span class="lr-muted">{escape(r.rec_why)}</span>',
                        unsafe_allow_html=True)
            opts = list(r.options)
            pick = ui.choice("How much", opts, f"la_opt_{r.product}", r.recommended,
                             format_func=lambda o, r=r: f"{SHORT[o]} · {r.options[o]:,.0f}")
            qty = float(r.options[pick])
            diff = (qty - float(r.order_qty)) * cost
            effect = ("no change to your order" if abs(diff) < 0.5 else
                      f"{'+' if diff > 0 else '−'}{ui.money(abs(diff))} vs your order now")
            st.markdown(f'<span class="lr-muted">{OPTION[pick]}: <b>{qty:,.0f} units</b> · {effect}. In your order now: '
                        f'{r.order_qty:,.0f}.</span>', unsafe_allow_html=True)
            st.button(f"Use {qty:,.0f} units", key=f"la_use_{r.product}", type="primary", on_click=_apply,
                      args=(r.product, r.name, qty), disabled=qty == float(r.order_qty), width="stretch")
    ui.enter(keys, anim)

    # ---------------- events ----------------
    ui.section("Local events this week", "Your notes from Settings › Local events. The forecast doesn't use them yet, "
                                         "so they don't change any number above.")
    if not events:
        st.caption("No events noted for this week. Add one in Settings › Local events.")
    for e in events:
        st.markdown(f"{ui.chip('This week', 'lr-s-soon', '◔')}**{escape(e['name'])}** <span class='lr-muted'>{e['start']} "
                    f"to {e['end']}{' · ' + escape(e['notes']) if e.get('notes') else ''}</span>", unsafe_allow_html=True)
