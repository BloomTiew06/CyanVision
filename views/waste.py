from html import escape

import streamlit as st

import laris_ui as ui
import planning
import store

ss = st.session_state
ctx = ss["ctx"]
ui.require_plan(ctx)
HERE, ref = "views/waste.py", ctx["ref"]

tbl = planning.waste_table(ctx)
saved = store.get("waste", {})
hidden = {k.split("|", 1)[1] for k, v in saved.items()
          if k.startswith(ref + "|") and v.get("status") in ("Dismissed", "Snoozed")}

# ---------------- A. summary ----------------
for col, kind, text in zip(st.columns(4), ["Expiry risk", "Excess stock", "Needs less than usual", "Slow-moving"],
                           ["may expire before it sells", "weeks of stock on hand", "smaller order than usual",
                            "sales falling, stock high"]):
    sub = tbl[tbl["kind"] == kind] if len(tbl) else tbl
    rm = float(sub["tied_rm"].sum()) if len(sub) else 0.0
    col.markdown(ui.kpi(kind.upper(), f"{len(sub)} products", text + (f" · ~{ui.money(rm)}" if rm >= 1 else "")),
                 unsafe_allow_html=True)
st.markdown(ui.label("ESTIMATED", "estimated") + '<span class="lr-muted">Expiry dates aren\'t recorded, so expiry risk '
            "uses each product's shelf life and assumes the stock on hand is fresh. Treat it as a rough guide; slow "
            "sales alone don't mean stock has expired.</span>", unsafe_allow_html=True)
if tbl.empty:
    st.success("No product looks overstocked or at risk of expiring this week.")
    st.stop()

OPTIONS = {"cut": "Cut the next order", "skip": "Skip the next reorder", "front": "Move to the front or bundle it",
           "keep": "Keep the usual order"}


def _record(p, choice, status):
    store.update("waste", f"{ref}|{p}", {"choice": choice, "status": status, "at": store.now()})


def _apply(p, qty, choice):
    ui.set_qty_value(p, qty)
    _record(p, choice, "Applied to order")


def waste_card(r):
    rec = saved.get(f"{ref}|{r.product}", {})
    with st.container(border=True):
        a, b = st.columns([3, 1.3])
        a.markdown(f'{ui.chip(r.kind, "lr-s-warning" if r.kind == "Expiry risk" else "lr-s-info")}'
                   f'<span class="lr-name">{escape(r.name)}</span>', unsafe_allow_html=True)
        b.markdown(f'<div style="text-align:right">{ui.label("ESTIMATED", "estimated")}<br><span class="lr-impact">'
                   f'~{ui.money(r.tied_rm)} at cost</span><br><span class="lr-muted">'
                   f'{"may expire unsold" if r.kind == "Expiry risk" else "beyond what sells before the next order"}'
                   '</span></div>', unsafe_allow_html=True)
        before = (f" · expected to sell about **{r.sales_before_expiry:,.0f}** before it expires" if r.perishable else "")
        st.markdown(f"Stock **{r.stock:,.0f}** · sold **{r.sold7:,.0f}** last week{before} · estimated unsold "
                    f"**{r.unsold:,.0f}** · shelf life **{r.shelf_life} days** (your setting; expiry dates not recorded).")
        c, d = st.columns([3, 2])
        keys = [o for o in OPTIONS if o != "cut" or 0 < r.recommended_qty < r.usual]
        default = rec.get("choice", r.choice)
        choice = c.radio("What will you do?", keys, key=f"wa_choice_{r.product}",
                         index=keys.index(default) if default in keys else 0,
                         format_func=lambda o: OPTIONS[o] + (" (recommended)" if o == r.choice else ""))
        c.caption(f"Why LARIS recommends '{OPTIONS[r.choice].lower()}': {r.why}")
        if r.front:
            c.caption("Also worth doing: move older stock to the front, or bundle it with a popular item. If you "
                      "discount it, check the lower price still covers what you paid; a discount isn't automatically "
                      "profitable.")
        with d:
            qty = {"cut": r.recommended_qty, "skip": 0.0, "keep": r.usual}.get(choice)
            if qty is not None:
                st.markdown(f"Order **{qty:,.0f}** (usually {r.usual:,.0f}). In your order now: **{r.order_qty:,.0f}**.")
                st.button("Apply to this week's order", key=f"wa_apply_{r.product}", type="primary",
                          on_click=_apply, args=(r.product, qty, choice))
            else:
                st.button("Record: moved to the front / bundled", key=f"wa_front_{r.product}", type="primary",
                          on_click=_record, args=(r.product, choice, "Shelf action recorded"))
            e, f = st.columns(2)
            e.button("Snooze", key=f"wa_snooze_{r.product}", on_click=_record, args=(r.product, choice, "Snoozed"),
                     use_container_width=True)
            f.button("Dismiss", key=f"wa_dismiss_{r.product}", on_click=_record, args=(r.product, choice, "Dismissed"),
                     use_container_width=True)
            ui.why_button(r.product, HERE, key=f"wa_why_{r.product}", label="View details")
        if rec.get("at"):
            st.caption(f"Last recorded {rec['at']}: {rec.get('status')}.")


ui.section("Products to buy less of", "Most money at stake first.")
for r in tbl[~tbl["product"].isin(hidden)].itertuples():
    waste_card(r)
gone = tbl[tbl["product"].isin(hidden)]
if len(gone):
    with st.expander(f"Snoozed or dismissed ({len(gone)})"):
        for r in gone.itertuples():
            a, b = st.columns([4, 1], vertical_alignment="center")
            a.markdown(f"**{r.name}**: {saved[f'{ref}|{r.product}']['status'].lower()}.")
            b.button("Show again", key=f"wa_undo_{r.product}", on_click=_record, args=(r.product, r.choice, "New"))
st.caption("Decisions are saved on this computer (state/laris_state.json) for this order week.")
