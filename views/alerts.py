from html import escape

import streamlit as st

import laris_ui as ui
import planning
import store

ss = st.session_state
ctx = ss["ctx"]
ui.require_plan(ctx)
HERE, ref = "views/alerts.py", ctx["ref"]

alerts = planning.alert_table(ctx)
muted = set(store.get("prefs", {}).get("muted", []))
saved = store.get("alerts", {})
if len(alerts):
    alerts = alerts[~alerts["product"].isin(muted)]
STATUSES = ["New", "Reviewed", "Action planned", "Resolved", "Snoozed"]


def status_of(p):
    return saved.get(f"{ref}|{p}", {}).get("status", "New")


# ---------------- A. urgency summary ----------------
counts = alerts["level"].value_counts().to_dict() if len(alerts) else {}
for col, level, text in zip(st.columns(3), ["URGENT", "WARNING", "MONITOR"],
                            ["may run out before the next delivery", "may run low before the delivery after",
                             "fine for now, worth a check"]):
    col.markdown(ui.kpi(level, f"{counts.get(level, 0)} products", text,
                        {"URGENT": "bad", "WARNING": "warn"}.get(level)), unsafe_allow_html=True)
if muted:
    st.caption(f"{len(muted)} muted product(s) hidden. Manage mutes in S · Send & Sync.")
if alerts.empty:
    st.success("No product is expected to run out before your next delivery.")
    st.stop()

OPTIONS = {"topup": "Top up from a wholesaler today", "next": "Order more for the next delivery",
           "sub": "Offer a substitute", "none": "Do nothing for now"}


def _save(p, k_status, k_choice, k_sub):
    store.update("alerts", f"{ref}|{p}", {"status": ss[k_status], "choice": ss[k_choice],
                                          "substitute": ss.get(k_sub, ""), "at": store.now()})


def alert_card(r):
    rec = saved.get(f"{ref}|{r.product}", {})
    with st.container(border=True):
        a, b = st.columns([3, 1.2])
        a.markdown(f'{ui.status_chip(r.level)}{ui.must_chip(r.must_have)}<span class="lr-name">{escape(r.name)}</span>'
                   f'<br><span class="lr-muted">{escape(r.reason)}</span>', unsafe_allow_html=True)
        b.markdown(f'<div style="text-align:right">{ui.label("ESTIMATED", "estimated")}<br>'
                   f'<span class="lr-impact">{ui.money(r.rm_at_risk)} margin at risk</span><br>'
                   f'<span class="lr-muted">if nothing is done</span></div>', unsafe_allow_html=True)
        if r.runout is None:
            when = "not within the week"
        else:
            when = f"around {r.runout:%a %d %b}"
            if r.runout_lo is not None and r.runout_hi is not None and r.runout_lo.date() != r.runout_hi.date():
                when += f" (likely between {r.runout_lo:%a %d} and {r.runout_hi:%a %d %b})"
        st.markdown(f"Stock **{r.stock:,.0f}** · sells about **{r.daily:,.1f} a day** · lasts about **{r.cover:,.1f} "
                    f"days** · may run out **{when}** · next delivery if ordered today **{r.delivery:%a %d %b}** "
                    f"({r.lead} day(s)).")
        c, d = st.columns([3, 2])
        keys = list(OPTIONS)
        k_choice, k_status, k_sub = f"al_choice_{r.product}", f"al_status_{r.product}", f"al_sub_{r.product}"
        choice = c.radio("What will you do?", keys, key=k_choice, index=keys.index(rec.get("choice", r.choice)),
                         format_func=lambda o: OPTIONS[o] + (" (recommended)" if o == r.choice else ""))
        c.caption(f"Why LARIS recommends '{OPTIONS[r.choice].lower()}': {r.why}")
        with d:
            if choice == "topup":
                st.markdown(f"Bridge the gap with about **{r.bridge_qty:,.0f} units** (the expected shortfall "
                            "before the delivery).")
                st.caption("LARIS can't see wholesaler prices or stock. At your usual cost it would be about "
                           f"{ui.money(r.bridge_qty * r.unit_cost)}; a wholesaler may charge more. Record it as "
                           "'Action planned' once you've arranged it.")
            elif choice == "next":
                st.markdown(f"In this week's order: **{r.order_qty:,.0f} units**.")
                if r.order_qty == 0 and r.bridge_qty > 0:
                    st.button(f"Add {r.bridge_qty:,.0f} to the order", key=f"al_add_{r.product}",
                              on_click=ui.set_qty_value, args=(r.product, r.bridge_qty))
            elif choice == "sub":
                st.text_input("Which product can customers buy instead?", value=rec.get("substitute", ""),
                              key=k_sub, help="Your choice. LARIS doesn't know which products substitute for each other.")
            else:
                st.caption("A short gap can be acceptable for a low-priority item. Check the shelf again tomorrow.")
            st.selectbox("Status", STATUSES, index=STATUSES.index(status_of(r.product)), key=k_status)
            st.button("Save", key=f"al_save_{r.product}", type="primary", on_click=_save,
                      args=(r.product, k_status, k_choice, k_sub))
            ui.why_button(r.product, HERE, key=f"al_why_{r.product}", label="View details")
        if rec.get("at"):
            st.caption(f"Last saved {rec['at']}: {rec.get('status')}.")


active = alerts[~alerts["product"].map(status_of).isin(["Resolved", "Snoozed"])]
done = alerts[alerts["product"].map(status_of).isin(["Resolved", "Snoozed"])]
ui.section("Alerts", "Most urgent first; must-haves and bigger losses rank higher. Dates are estimates from the "
                     "forecast and its usual error, not exact.")
for r in active.itertuples():
    alert_card(r)
if len(done):
    with st.expander(f"Resolved or snoozed ({len(done)})"):
        for r in done.itertuples():
            alert_card(r)
st.caption("Alert decisions are saved on this computer (state/laris_state.json) for this order week.")
