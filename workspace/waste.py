"""R · Reduce Waste: stock that may expire unsold or tie up cash, how much, and how to avoid buying more of it.
Risk and options come from planning.waste_table; decisions are saved in the local store (waste[ref|product])."""
from html import escape

import streamlit as st

import laris_ui as ui
import planning
import store

HERE = "views/laris.py"
OPTIONS = {"cut": "Cut the order", "skip": "Skip reorder", "front": "Front / bundle", "keep": "Keep usual"}
OPTION_LONG = {"cut": "cut the next order", "skip": "skip the next reorder", "front": "move it to the front or bundle it",
               "keep": "keep the usual order"}
KIND_CHIP = {"Expiry risk": ("Expiry risk", "lr-s-expiry", "⌛"), "Excess stock": ("Excess stock", "lr-s-excess", "▣"),
             "Needs less than usual": ("Needs less", "lr-s-info", "ⓘ"), "Slow-moving": ("Slow-moving", "lr-s-info", "ⓘ")}


def _record(ref, p, name, choice, status, toast=True):
    try:
        store.update("waste", f"{ref}|{p}", {"choice": choice, "status": status, "at": store.now()})
    except OSError:
        ui.flash(f"Couldn't save the decision for {name}: the local file isn't writable. Nothing was changed.")
        return False
    if toast:
        ui.flash(f"{name}: {status.lower()}.")
    return True


def _apply(ref, p, name, qty, choice):
    ui.set_qty_value(p, qty)
    if _record(ref, p, name, choice, "Applied to order", toast=False):
        ui.flash(f"{name}: this week's order is now {qty:,.0f} units.")


def _card(ctx, r, rec, key, anim):
    ref = ctx["ref"]
    icon, name = ui.split_name(r.name)
    text, cls, ic = KIND_CHIP.get(r.kind, (r.kind, "lr-s-info", "ⓘ"))
    with st.container(border=True, key=key):
        a, b = st.columns([3, 1.3])
        a.markdown(f'{ui.chip(text, cls, ic)}<span class="lr-name">{escape(icon)} {escape(name)}</span>'
                   + ui.product_spark(ctx, r.product, 240, 40), unsafe_allow_html=True)
        b.markdown(f'<div style="text-align:right">{ui.label("ESTIMATED", "estimated")}<br><span class="lr-impact">'
                   f'~{ui.money(r.tied_rm)} at cost</span><br><span class="lr-muted">'
                   f'{"may expire unsold" if r.kind == "Expiry risk" else "beyond what sells before the next order"}'
                   '</span></div>', unsafe_allow_html=True)
        sells = max(0.0, r.stock - r.unsold)
        horizon = "before it expires" if r.perishable else "before the next order"
        st.markdown(ui.segments([(sells, ""), (r.unsold, "hatch")], max(r.stock, 1e-9),
                                f"Stock {r.stock:.0f}: about {sells:.0f} sell {horizon}, about {r.unsold:.0f} may be left",
                                anim=anim)
                    + f'<div class="lr-meter-legend"><span>■ Sells {horizon}: <b>{sells:,.0f}</b></span>'
                      f'<span>▨ May be left: <b>{r.unsold:,.0f}</b> of {r.stock:,.0f}</span></div>',
                    unsafe_allow_html=True)
        st.caption(f"Sold {r.sold7:,.0f} last week · shelf life {r.shelf_life} days (your setting; expiry dates aren't "
                   "recorded, so this assumes the stock on hand is fresh).")
        rec_qty = {"cut": r.recommended_qty, "skip": 0.0, "keep": r.usual}.get(r.choice)
        c, d = st.columns([3, 1.6], vertical_alignment="center")
        c.markdown(f'<span class="lr-muted"><b>LARIS suggests:</b> {escape(OPTION_LONG[r.choice])}. {escape(r.why)}</span>',
                   unsafe_allow_html=True)
        if rec_qty is not None:
            label = ("Skip the reorder (order 0)" if r.choice == "skip" else f"Cut the order to {rec_qty:,.0f}"
                     if r.choice == "cut" else f"Keep the usual {rec_qty:,.0f}")
            d.button(label, key=f"wa_go_{r.product}", type="primary", width="stretch",
                     disabled=rec_qty == r.order_qty, on_click=_apply, args=(ref, r.product, name, rec_qty, r.choice),
                     help="Already in this week's order" if rec_qty == r.order_qty else None)
        else:
            d.button("Record: moved to front / bundled", key=f"wa_go_{r.product}", type="primary",
                     width="stretch", on_click=_record, args=(ref, r.product, name, r.choice,
                                                                       "Shelf action recorded"))
        if r.front:
            st.caption("Also worth doing: move older stock to the front, or bundle it with a popular item. If you discount "
                       "it, check the lower price still covers what you paid.")
        with st.expander("More options: another choice, snooze, details"):
            keys = [o for o in OPTIONS if o != "cut" or 0 < r.recommended_qty < r.usual]
            default = rec.get("choice", r.choice)
            default = default if default in keys else (r.choice if r.choice in keys else keys[0])
            choice = ui.choice("What will you do?", keys, f"wa_choice_{r.product}", default,
                               format_func=lambda o, r=r: OPTIONS[o] + (" ★" if o == r.choice else ""))
            qty = {"cut": r.recommended_qty, "skip": 0.0, "keep": r.usual}.get(choice)
            e, f, g, h = st.columns([1.6, 1, 1, 1], vertical_alignment="center")
            if qty is not None:
                e.button(f"Apply: order {qty:,.0f}", key=f"wa_apply_{r.product}", width="stretch",
                         disabled=qty == r.order_qty, on_click=_apply, args=(ref, r.product, name, qty, choice))
            else:
                e.button("Record shelf action", key=f"wa_front_{r.product}", width="stretch",
                         on_click=_record, args=(ref, r.product, name, choice, "Shelf action recorded"))
            f.button("Snooze", key=f"wa_snooze_{r.product}", width="stretch",
                     on_click=_record, args=(ref, r.product, name, choice, "Snoozed"))
            g.button("Dismiss", key=f"wa_dismiss_{r.product}", width="stretch",
                     on_click=_record, args=(ref, r.product, name, choice, "Dismissed"))
            with h:
                ui.why_button(r.product, HERE, key=f"wa_why_{r.product}", label="Details")
            st.caption(f"Usually {r.usual:,.0f}; in your order now: {r.order_qty:,.0f}.")
        if rec.get("at"):
            st.caption(f"Last recorded {rec['at']}: {rec.get('status')}.")


def render(ctx):
    ref = ctx["ref"]
    anim = ui.first_view("tool:R")
    tbl = planning.waste_table(ctx)
    saved = store.get("waste", {})
    rec_of = lambda p: saved.get(f"{ref}|{p}", {})

    k = st.columns(4)
    for col, kind, text in zip(k, ["Expiry risk", "Excess stock", "Needs less than usual", "Slow-moving"],
                               ["may expire before it sells", "weeks of stock on hand", "smaller order than usual",
                                "sales falling, stock high"]):
        sub = tbl[tbl["kind"] == kind] if len(tbl) else tbl
        rm = float(sub["tied_rm"].sum()) if len(sub) else 0.0
        col.markdown(ui.kpi(kind, " products", text + (f" · ~{ui.money(rm)}" if rm >= 1 else ""),
                            "warn" if kind == "Expiry risk" and len(sub) else None, len(sub), f"wa_{kind}"),
                     unsafe_allow_html=True)
    st.markdown(ui.label("ESTIMATED", "estimated") + '<span class="lr-muted">Expiry dates aren\'t recorded, so expiry risk '
                "uses each product's shelf life and assumes the stock on hand is fresh. Treat it as a rough guide.</span>",
                unsafe_allow_html=True)
    if tbl.empty:
        st.markdown(ui.empty("✓", "Nothing looks overstocked or at risk of expiring",
                             "LARIS checks again whenever your stock or sales change."), unsafe_allow_html=True)
        return
    keep = ui.filter_bar("wa", ctx)
    view = keep(tbl)
    if view is None or view.empty:
        st.markdown(ui.empty("🔍", "No product matches", "Clear the search or the category filter."),
                    unsafe_allow_html=True)
        return
    hidden = view["product"].map(lambda p: rec_of(p).get("status") in ("Dismissed", "Snoozed"))
    ui.section("Products to buy less of", "Most money at stake first.")
    keys = []
    grid = st.columns(2, gap="medium")
    for i, r in enumerate(view[~hidden].itertuples()):
        key = f"card_wa_{ui.safe_key(r.product)}"
        keys.append(key)
        with grid[i % 2]:
            _card(ctx, r, rec_of(r.product), key, anim)
    if not len(keys):
        st.markdown(ui.empty("✓", "All handled", "Snoozed or dismissed products are listed below."),
                    unsafe_allow_html=True)
    ui.enter(keys, anim)
    gone = view[hidden]
    if len(gone):
        with st.expander(f"Snoozed or dismissed ({len(gone)})", icon=":material/task_alt:"):
            for r in gone.itertuples():
                a, b = st.columns([4, 1], vertical_alignment="center")
                a.markdown(f"**{ui.split_name(r.name)[1]}**: {rec_of(r.product)['status'].lower()}.")
                b.button("Show again", key=f"wa_undo_{r.product}", width="stretch",
                         on_click=_record, args=(ref, r.product, ui.split_name(r.name)[1], r.choice, "New"))
    st.caption("Decisions are saved on this computer (state/laris_state.json) for this order week.")
