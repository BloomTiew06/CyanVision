"""S · Send & Sync: review this week's order, share it with the supplier as a WhatsApp draft, record each step, record
what arrives, and choose which reminders you want. LARIS never sends anything itself: WhatsApp opens a draft the owner
sends, and every status here is the owner's own record. Order records live in the local store (orders[ref])."""
from html import escape

import pandas as pd
import streamlit as st

import laris_ui as ui
import planning
import store

STEPS = [("Review", "check quantities"), ("Share", "open the WhatsApp draft"), ("Supplier confirms", "your record"),
         ("Receive", "count what arrived")]
STEP_OF = {"Draft": 0, "Ready to share": 1, "Shared": 2, "Acknowledged": 3, "Received": 4, "Partly received": 4}


def _status(ref, order, new, note=""):
    r = store.get("orders", {}).get(ref, {"status": "Draft", "history": []})
    r["status"] = new
    r["history"] = r.get("history", []) + [{"status": new, "at": store.now(), "note": note}]
    if new in ("Ready to share", "Shared") or "items" not in r:   # snapshot what was shared
        r["items"] = {n: float(q) for n, q in zip(order["name"], order["order_qty"])}
        r["total_rm"] = float(order["order_rm"].sum())
    try:
        store.update("orders", ref, r)
    except OSError:
        ui.flash("Couldn't save the order status: the local file isn't writable. Nothing was changed.")
        return False
    ui.flash(f"Order {ref}: {new.lower()} (your record).")
    return True


def _save_prefs(names):
    ss = st.session_state
    try:
        store.put("prefs", {**store.get("prefs", {}), "muted": [p for p in ss["pf_muted"] if p in names]})
    except OSError:
        ui.flash("Couldn't save your muted products: the local file isn't writable.")
        return
    ui.flash("Muted products saved.")


def render(ctx):
    ss = st.session_state
    plan, ref, as_of = ctx["plan"], ctx["ref"], ctx["week"]["as_of"]
    rec = store.get("orders", {}).get(ref, {"status": "Draft", "history": []})
    order = plan[plan["order_qty"] > 0]
    rows = ctx["rows"].set_index("product")
    step = STEP_OF.get(rec["status"], 0)

    # ---------------- status ----------------
    st.markdown(ui.stepper(STEPS, step), unsafe_allow_html=True)
    arrive = as_of + pd.Timedelta(days=int(rows.loc[order["product"], "lead_time"].min())) if len(order) else None
    left = ctx["budget_rm"] - ctx["order_rm"]
    k = st.columns(4)
    k[0].markdown(ui.kpi("Order status", rec["status"], f"order {ref} · your record"), unsafe_allow_html=True)
    k[1].markdown(ui.kpi("Estimated total", ui.money(ctx["order_rm"], 2), f"{len(order)} products"),
                  unsafe_allow_html=True)
    k[2].markdown(ui.kpi("Budget left" if left >= 0 else "Over budget", ui.money(abs(left)),
                         f"of {ui.money(ctx['budget_rm'])}", None if left >= 0 else "bad"), unsafe_allow_html=True)
    k[3].markdown(ui.kpi("First delivery", f"{arrive:%a %d %b}" if arrive is not None else "–",
                         "if ordered today (your delivery days)"), unsafe_allow_html=True)

    # ---------------- 1. review ----------------
    ui.section("1. Check the order", "The quantities LARIS planned within your budget, including your changes.")
    if order.empty:
        st.markdown(ui.empty("🧾", "Nothing to order this week", "Your stock covers expected sales."),
                    unsafe_allow_html=True)
    else:
        st.dataframe(pd.DataFrame({"Product": order["name"], "Order": order["order_qty"],
                                   "LARIS suggests": order["qty"], "Unit cost (RM)": order["unit_cost"],
                                   "Total (RM)": order["order_rm"]}),
                     hide_index=True, width="stretch",
                     column_config={"Order": st.column_config.NumberColumn(format="%d"),
                                    "LARIS suggests": st.column_config.NumberColumn(format="%d"),
                                    "Unit cost (RM)": st.column_config.NumberColumn(format="%.2f"),
                                    "Total (RM)": st.column_config.NumberColumn(format="%.2f")})
    a, b = st.columns([1.3, 4], vertical_alignment="center")
    with a:
        ui.tool_button("I", "Edit quantities in I", key="se_edit")
    b.caption("Quantities are edited in one place, I · Invest Within Budget, so every screen shows the same order.")

    # ---------------- 2. share ----------------
    ui.section("2. Share it with your supplier")
    st.caption(f"Supplier: {ss.get('supplier_name') or 'not set'}"
               f"{' · WhatsApp ' + ss['supplier_phone'] if ss.get('supplier_phone') else ''}. Change it in Settings › "
               "Supplier.")
    msg = planning.order_message(plan, ctx["shop"], as_of, ref)
    a, b = st.columns([1.15, 1], vertical_alignment="center", gap="medium")
    a.markdown(ui.whatsapp_preview(msg, ss.get("supplier_name") or "Your supplier", ss.get("supplier_phone")),
               unsafe_allow_html=True)
    with b:
        st.link_button("Open WhatsApp draft", planning.whatsapp_url(msg, ss.get("supplier_phone")), type="primary",
                       icon=":material/send:", width="stretch", disabled=order.empty)
        st.markdown('<span class="lr-muted">This opens WhatsApp with the message filled in. <b>You</b> check it and press '
                    "send. LARIS can't see whether it was sent, so record each step below yourself.</span>",
                    unsafe_allow_html=True)
    c = st.columns(4)
    c[0].button("Save for later (ready)", on_click=_status, args=(ref, order, "Ready to share"), width="stretch",
                disabled=rec["status"] != "Draft")
    c[1].button("I've sent it", on_click=_status, args=(ref, order, "Shared"), width="stretch",
                disabled=rec["status"] not in ("Draft", "Ready to share"))
    c[2].button("Supplier confirmed", on_click=_status, args=(ref, order, "Acknowledged"), width="stretch",
                disabled=rec["status"] != "Shared")
    c[3].button("Back to draft", on_click=_status, args=(ref, order, "Draft", "reopened"), width="stretch",
                disabled=rec["status"] == "Draft")
    st.caption("'Supplier confirmed' is your own record of their reply, not a confirmation LARIS received.")
    po = planning.purchase_order(plan, ref, as_of, ss.get("supplier_name"))
    st.download_button("Download purchase order (CSV)", po.to_csv(index=False).encode("utf-8"), file_name=f"{ref}.csv",
                       mime="text/csv", icon=":material/download:", disabled=po.empty, key="se_po")

    # ---------------- 3. receive ----------------
    ui.section("3. Record the delivery", "Enter what actually arrived. Only quantities you confirm are added to your stock.")
    items = rec.get("items") or {n: float(q) for n, q in zip(order["name"], order["order_qty"])}
    received = rec["status"] in ("Received", "Partly received")
    if rec.get("received"):
        r = rec["received"]
        st.markdown(f'{ui.status_chip("Handled")}<span class="lr-muted">Delivery recorded for {escape(r["date"])}'
                    + (f"; differences: {escape(', '.join(r['discrepancies']))}" if r["discrepancies"] else
                       "; everything arrived") + (". Added to your stock." if r.get("added_to_stock") else ".")
                    + "</span>", unsafe_allow_html=True)
    again = ss.get("se_again", False)
    if items and received and not again:
        st.button("Record another delivery for this order", key="se_again_btn", on_click=lambda: ss.update(se_again=True),
                  help="This order already has a delivery recorded. Use this only for a second, separate delivery, so "
                       "the same goods aren't added to your stock twice.")
    if not items:
        st.caption("Nothing ordered yet.")
    elif not received or again:
        with st.form("received_form"):
            got = st.data_editor(pd.DataFrame({"Product": list(items), "Ordered": list(items.values()),
                                               "Received": list(items.values())}),
                                 hide_index=True, width="stretch", disabled=["Product", "Ordered"],
                                 column_config={"Ordered": st.column_config.NumberColumn(format="%d"),
                                                "Received": st.column_config.NumberColumn(min_value=0, step=1,
                                                                                          format="%d")})
            d1, d2 = st.columns(2)
            when = d1.date_input("Received on", value=(as_of + pd.Timedelta(days=1)).date())
            note = d2.text_input("Notes (damaged, wrong item…)", "")
            add = st.checkbox("Add the received quantities to my stock in Products")
            if st.form_submit_button("Record delivery", type="primary"):
                got["Received"] = got["Received"].fillna(0).clip(lower=0)
                status = "Received" if (got["Received"] >= got["Ordered"]).all() else "Partly received"
                disc = {r.Product: {"ordered": float(r.Ordered), "received": float(r.Received)}
                        for r in got.itertuples() if r.Received != r.Ordered}
                if _status(ref, order, status, f"received {when}" + (f"; {note}" if note else "")):
                    r2 = store.get("orders", {})[ref]
                    r2["received"] = {"date": str(when),
                                      "quantities": {k: float(v) for k, v in zip(got["Product"], got["Received"])},
                                      "discrepancies": disc, "note": note, "added_to_stock": add}
                    store.update("orders", ref, r2)
                    if add:
                        inp = ss["inputs"].copy()
                        inp["On hand"] = inp["On hand"] + inp["Name"].map(dict(zip(got["Product"],
                                                                                    got["Received"]))).fillna(0)
                        ss["inputs"], ss["inputs_dirty"] = inp, True
                    ss["flash"] = [f"Delivery recorded: {status.lower()}." + (" Stock updated." if add else "")]
                    ss["se_again"] = False
                st.rerun()
    if rec.get("history"):
        with st.expander("Order history"):
            for h in reversed(rec["history"]):
                st.markdown(f"- {h['at']}: **{h['status']}**{' (' + h['note'] + ')' if h.get('note') else ''}")

    # ---------------- 4. muted products ----------------
    ui.section("Muted products", "Products you don't want flagged for now. They stay visible in A under 'Muted, still at "
                                 "risk', so no risk is ever hidden.")
    prefs = store.get("prefs", {})
    names = dict(zip(plan["product"], plan["name"]))
    ss.setdefault("pf_muted", [p for p in prefs.get("muted", []) if p in names])
    st.multiselect("Mute these products", list(names), format_func=names.get, key="pf_muted",
                   on_change=_save_prefs, args=(names,), label_visibility="collapsed")
