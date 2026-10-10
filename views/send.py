import pandas as pd
import streamlit as st

import laris_ui as ui
import planning
import store

ss = st.session_state
ctx = ss["ctx"]
ui.require_plan(ctx)
plan, ref, as_of = ctx["plan"], ctx["ref"], ctx["week"]["as_of"]
rec = store.get("orders", {}).get(ref, {"status": "Draft", "history": []})
order = plan[plan["order_qty"] > 0]
rows = ctx["rows"].set_index("product")


def _status(new, note=""):
    r = store.get("orders", {}).get(ref, {"status": "Draft", "history": []})
    r["status"] = new
    r["history"] = r.get("history", []) + [{"status": new, "at": store.now(), "note": note}]
    if new in ("Ready to share", "Shared") or "items" not in r:   # snapshot what was shared
        r["items"] = {n: float(q) for n, q in zip(order["name"], order["order_qty"])}
        r["total_rm"] = float(order["order_rm"].sum())
    store.update("orders", ref, r)


# ---------------- A. order ready ----------------
arrive = as_of + pd.Timedelta(days=int(rows.loc[order["product"], "lead_time"].min())) if len(order) else None
left = ctx["budget_rm"] - ctx["order_rm"]
k = st.columns(4)
k[0].markdown(ui.kpi("ORDER STATUS", rec["status"], f"order {ref}"), unsafe_allow_html=True)
k[1].markdown(ui.kpi("ESTIMATED TOTAL", ui.money(ctx["order_rm"], 2), f"{len(order)} products"), unsafe_allow_html=True)
k[2].markdown(ui.kpi("BUDGET LEFT" if left >= 0 else "OVER BUDGET", ui.money(abs(left)), f"of {ui.money(ctx['budget_rm'])}",
                     None if left >= 0 else "bad"), unsafe_allow_html=True)
k[3].markdown(ui.kpi("FIRST DELIVERY", f"{arrive:%a %d %b}" if arrive is not None else "–",
                     "if ordered today (your delivery days)"), unsafe_allow_html=True)
st.caption(f"Supplier: {ss.get('supplier_name') or 'not set'}"
           f"{' · WhatsApp ' + ss['supplier_phone'] if ss.get('supplier_phone') else ''}. Change it in Settings.")

# ---------------- B. review / edit, then share ----------------
ui.section("1. Check the order", "Change any quantity, then save. Your changes show on every page; LARIS's own "
                                 "suggestion stays visible next to them.")
edit = pd.DataFrame({"product": plan["product"], "Product": plan["name"], "LARIS suggests": plan["qty"],
                     "Order": plan["order_qty"], "Unit cost (RM)": plan["unit_cost"], "Total (RM)": plan["order_rm"]})
edited = st.data_editor(edit, key=f"order_editor_{ref}_{ss.get('order_ver', 0)}", hide_index=True,
                        use_container_width=True, disabled=["Product", "LARIS suggests", "Unit cost (RM)", "Total (RM)"],
                        column_config={"product": None,
                                       "LARIS suggests": st.column_config.NumberColumn(format="%d"),
                                       "Order": st.column_config.NumberColumn(min_value=0, step=1, format="%d"),
                                       "Unit cost (RM)": st.column_config.NumberColumn(format="%.2f"),
                                       "Total (RM)": st.column_config.NumberColumn(format="%.2f")})


def _save_edits():
    for p, sug, q in zip(edited["product"], edited["LARIS suggests"], edited["Order"]):
        q = 0.0 if pd.isna(q) else max(0.0, float(q))
        if q != sug:
            ui.set_qty_value(p, q)
        else:
            ui.clear_qty(p)
    ss["order_ver"] = ss.get("order_ver", 0) + 1


a, b = st.columns([1, 3], vertical_alignment="center")
a.button("Save changes", on_click=_save_edits, type="primary", use_container_width=True)
b.caption("Totals update after you save.")

ui.section("2. Share it with your supplier")
msg = planning.order_message(plan, ctx["shop"], as_of, ref)
with st.expander("Preview the message"):
    st.code(msg, language=None)
a, b = st.columns([2, 3], vertical_alignment="center")
a.link_button("Open WhatsApp draft", planning.whatsapp_url(msg, ss.get("supplier_phone")), type="primary",
              icon=":material/send:", use_container_width=True, disabled=order.empty)
b.markdown('<span class="lr-muted">This opens WhatsApp with the message filled in. <b>You</b> check it and press '
           "send. LARIS can't see whether it was sent, so record each step below yourself.</span>",
           unsafe_allow_html=True)
c = st.columns(4)
c[0].button("Save for later (ready)", on_click=_status, args=("Ready to share",), use_container_width=True,
            disabled=rec["status"] != "Draft")
c[1].button("I've sent it", on_click=_status, args=("Shared",), use_container_width=True,
            disabled=rec["status"] not in ("Draft", "Ready to share"))
c[2].button("Supplier confirmed", on_click=_status, args=("Acknowledged",), use_container_width=True,
            disabled=rec["status"] != "Shared")
c[3].button("Back to draft", on_click=_status, args=("Draft", "reopened"), use_container_width=True,
            disabled=rec["status"] == "Draft")
st.caption("'Supplier confirmed' is your own record of their reply, not a confirmation LARIS received.")
st.markdown(ui.label("NOT CONNECTED", "planned") + "**Telegram**: needs a Telegram bot, its secret token and a "
            "webhook before LARIS could send or read messages. Not set up, so nothing is sent.", unsafe_allow_html=True)

# ---------------- D. delivery received ----------------
ui.section("3. Record the delivery", "Enter what actually arrived. Only quantities you confirm are added to your stock.")
items = rec.get("items") or {n: float(q) for n, q in zip(order["name"], order["order_qty"])}
if not items:
    st.caption("Nothing ordered yet.")
else:
    with st.form("received_form"):
        got = st.data_editor(pd.DataFrame({"Product": list(items), "Ordered": list(items.values()),
                                           "Received": list(items.values())}),
                             hide_index=True, use_container_width=True, disabled=["Product", "Ordered"],
                             column_config={"Ordered": st.column_config.NumberColumn(format="%d"),
                                            "Received": st.column_config.NumberColumn(min_value=0, step=1, format="%d")})
        d1, d2 = st.columns(2)
        when = d1.date_input("Received on", value=(as_of + pd.Timedelta(days=1)).date())
        note = d2.text_input("Notes (damaged, wrong item…)", "")
        add = st.checkbox("Add the received quantities to my stock in My Products")
        if st.form_submit_button("Record delivery", type="primary"):
            got["Received"] = got["Received"].fillna(0).clip(lower=0)
            status = "Received" if (got["Received"] >= got["Ordered"]).all() else "Partly received"
            disc = {r.Product: {"ordered": float(r.Ordered), "received": float(r.Received)}
                    for r in got.itertuples() if r.Received != r.Ordered}
            _status(status, f"received {when}" + (f"; {note}" if note else ""))
            r2 = store.get("orders", {})[ref]
            r2["received"] = {"date": str(when), "quantities": {k: float(v) for k, v in zip(got["Product"], got["Received"])},
                              "discrepancies": disc, "note": note, "added_to_stock": add}
            store.update("orders", ref, r2)
            if add:
                inp = ss["inputs"].copy()
                inp["On hand"] = inp["On hand"] + inp["Name"].map(dict(zip(got["Product"], got["Received"]))).fillna(0)
                ss["inputs"], ss["inputs_dirty"] = inp, True
            ss["flash"] = [f"Delivery recorded: {status.lower()}." + (" Stock updated." if add else "")]
            st.rerun()
if rec.get("received"):
    r = rec["received"]
    st.caption(f"Last delivery recorded for {r['date']}" + (f"; differences: {', '.join(r['discrepancies'])}"
                                                             if r["discrepancies"] else "; everything arrived") + ".")
if rec.get("history"):
    with st.expander("Order history"):
        for h in reversed(rec["history"]):
            st.markdown(f"- {h['at']}: **{h['status']}**{' (' + h['note'] + ')' if h.get('note') else ''}")

# ---------------- E. alerts and reminders ----------------
ui.section("Alerts and reminders")
prefs = store.get("prefs", {})
names = dict(zip(plan["product"], plan["name"]))


def _save_prefs():
    store.put("prefs", {**store.get("prefs", {}), "urgent": ss["pf_urgent"], "evening": ss["pf_evening"],
                        "muted": ss["pf_muted"], "snooze_until": str(ss["pf_snooze"]) if ss["pf_snooze"] else None})


a, b = st.columns(2)
a.toggle("Urgent stock alerts", value=prefs.get("urgent", True), key="pf_urgent", on_change=_save_prefs)
a.toggle("Evening summary", value=prefs.get("evening", False), key="pf_evening", on_change=_save_prefs)
b.multiselect("Mute alerts for these products", list(names), default=[p for p in prefs.get("muted", []) if p in names],
              format_func=names.get, key="pf_muted", on_change=_save_prefs,
              help="Muted products are hidden from A · Alert Before Stockout.")
b.date_input("Snooze order reminders until", value=pd.Timestamp(prefs["snooze_until"]).date()
             if prefs.get("snooze_until") else None, key="pf_snooze", on_change=_save_prefs)
st.markdown(ui.label("NOT CONNECTED", "planned") + '<span class="lr-muted">These preferences are saved, but LARIS has '
            "no notification service yet, so no alerts or reminders are actually sent. Muting works inside the app."
            "</span>", unsafe_allow_html=True)

# ---------------- F. reorder levels ----------------
ui.section("Reorder levels", "When stock falls to the reorder point, order up to the maximum. Calculated from the "
                             "forecast and your delivery days, not fixed numbers.")
lv = planning.reorder_levels(ctx)
st.dataframe(lv.assign(state=lv["below"].map({True: "Below reorder point", False: "OK"}))
             [["name", "stock", "reorder_point", "max_level", "state"]], hide_index=True, use_container_width=True,
             column_config={"name": "Product", "stock": st.column_config.NumberColumn("Stock", format="%d"),
                            "reorder_point": st.column_config.NumberColumn("Reorder point", format="%d"),
                            "max_level": st.column_config.NumberColumn("Order up to", format="%d"), "state": "Now"})
st.caption(f"Reorder point = expected sales during the delivery time + safety stock for a {ctx['service']:.0%} chance of "
           "not running out (assumes forecast errors are roughly normal). Order up to = expected sales until the "
           "following delivery (capped by shelf life) + the same safety stock. Order records are saved in "
           "state/laris_state.json on this computer.")
