from html import escape

import pandas as pd
import streamlit as st

import laris_ui as ui
import planning
import store

ss = st.session_state
ctx = ss["ctx"]
ui.require_plan(ctx)
week, HERE = ctx["week"], "views/look_ahead.py"
as_of, end = week["as_of"], week["end"]

tbl = planning.look_ahead_table(ctx, ss.get("la_rank") or "Biggest increase")
events = store.get("events", [])
this_week = [e for e in events if pd.Timestamp(e["start"]) <= end and pd.Timestamp(e["end"]) >= as_of]

# ---------------- A. demand overview ----------------
k = st.columns(4)
k[0].markdown(ui.kpi("SELLING MORE", f"{int((tbl['trend'] == 'Growing').sum())} products", "next 7 days vs last 7"),
              unsafe_allow_html=True)
k[1].markdown(ui.kpi("SELLING LESS", f"{int((tbl['trend'] == 'Declining').sum())} products", "next 7 days vs last 7"),
              unsafe_allow_html=True)
k[2].markdown(ui.kpi("LESS CERTAIN", f"{int(tbl['uncertain'].sum())} products", "wide range or little history"),
              unsafe_allow_html=True)
k[3].markdown(ui.kpi("YOUR EVENTS THIS WEEK", str(len(this_week)), "context only, see below"), unsafe_allow_html=True)

# ---------------- B. ranking ----------------
ui.section("Expected demand, next 7 days", "Forecasts come from the AI model, scaled to what you sold last week.")
st.segmented_control("Rank by", list(planning.RANKINGS), default="Biggest increase", key="la_rank")
show = tbl.assign(
    change_pct=tbl["change"] * 100,
    lasts=tbl["cover"].map(lambda c: f"{c:.1f} days" if pd.notna(c) and c < 1e9 else "no sales expected"),
    delivery=tbl["delivery"].dt.strftime("%a %d %b"), action=tbl["action"].map(planning.ACTION_LABEL),
    note=tbl["uncertain"].map({True: "Less certain", False: ""}))
st.dataframe(show[["name", "fc7", "last7", "change_pct", "lasts", "delivery", "action", "note", "why"]],
             hide_index=True, use_container_width=True, column_config={
                 "name": st.column_config.TextColumn("Product", width="medium"),
                 "fc7": st.column_config.NumberColumn("Expected sales (7 days)", format="%.0f"),
                 "last7": st.column_config.NumberColumn("Sold last 7 days", format="%.0f"),
                 "change_pct": st.column_config.NumberColumn("Change", format="%+.0f%%"),
                 "lasts": "Stock lasts", "delivery": "Next delivery if ordered today", "action": "Plan",
                 "note": "Forecast", "why": st.column_config.TextColumn("Why", width="large")})

# ---------------- C. stock-up options ----------------
ui.section("Prepare for higher demand",
           "Where LARIS suggests ordering more than last week, choose how much extra to buy. Your choice updates the "
           "order on every page.")
cands = tbl[tbl["options"].map(len) > 0]
if cands.empty:
    st.success("No product needs extra stock beyond your usual order this week.")
LABELS = {"full": "Stock up fully", "part": "Stock up partly", "skip": "Skip the extra (your usual order)"}
for r in cands.itertuples():
    with st.container(border=True):
        a, b = st.columns([3, 2])
        a.markdown(f'<span class="lr-name">{escape(r.name)}</span> {ui.action_chip(r.action)}<br>'
                   f'<span class="lr-muted">Expected to sell {r.fc7:,.0f} next week ({r.change:+.0%} vs last week). '
                   f'{escape(r.deadline)}</span>', unsafe_allow_html=True)
        a.markdown(f"**Recommended: {LABELS[r.recommended].lower()}.** {r.rec_why}")
        keys = list(r.options)
        choice = b.radio("How much to order", keys, index=keys.index(r.recommended), key=f"la_opt_{r.product}",
                         format_func=lambda o, r=r: f"{LABELS[o]}: {r.options[o]:,.0f} units")
        b.button(f"Use {r.options[choice]:,.0f} units", key=f"la_use_{r.product}", on_click=ui.set_qty_value,
                 args=(r.product, r.options[choice]), type="primary")
        b.caption(f"In your order now: {r.order_qty:,.0f}")

# ---------------- E. forecast chart ----------------
ui.section("Forecast detail")
names = dict(zip(tbl["product"], tbl["name"]))
p = st.selectbox("Product", list(names), format_func=names.get, key="la_product")
chart, note = ui.forecast_chart(ctx, p)
st.altair_chart(chart, use_container_width=True)
st.caption(f"{names[p]}: units per day, recorded sales (grey) and forecast for {as_of:%d %b} – {end:%d %b} "
           f"(green). {note}")
ui.why_button(p, HERE, key="la_why", label="Why this recommendation?")

# ---------------- D. local events ----------------
ui.section("Local events (your notes)",
           "Paydays, school events, a nearby factory shift: record them so you remember to check stock. LARIS's "
           "forecast does not use these events yet, so nothing here changes the numbers above.")
with st.form("event_form", clear_on_submit=True):
    a, b, c = st.columns([2, 1, 1])
    name = a.text_input("Event name", placeholder="e.g. School sports day")
    start = b.date_input("Start", value=as_of.date())
    stop = c.date_input("End", value=as_of.date())
    notes = st.text_input("Notes (optional)")
    assumed = st.number_input("Your guess of the effect on sales, % (optional, an assumption)", value=0, step=5,
                              help="Saved as your note only. It is not applied to the forecast.")
    if st.form_submit_button("Save event", type="primary"):
        if not name.strip():
            st.error("Give the event a name.")
        elif stop < start:
            st.error("The end date is before the start date.")
        else:
            events.append({"name": name.strip(), "start": str(start), "end": str(stop), "notes": notes.strip(),
                           "assumed_change_pct": assumed or None, "saved": store.now()})
            store.put("events", events)
            st.rerun()
if not events:
    st.caption("No events recorded yet.")


def _delete(i):
    ev = store.get("events", [])
    ev.pop(i)
    store.put("events", ev)


for i, e in enumerate(events):
    overlap = pd.Timestamp(e["start"]) <= end and pd.Timestamp(e["end"]) >= as_of
    a, b = st.columns([6, 1], vertical_alignment="center")
    guess = f" · your assumption: {e['assumed_change_pct']:+}% (not applied)" if e.get("assumed_change_pct") else ""
    a.markdown(f"{ui.chip('This week', 'lr-s-warning') if overlap else ''}**{escape(e['name'])}** "
               f"<span class='lr-muted'>{e['start']} to {e['end']}{' · ' + escape(e['notes']) if e['notes'] else ''}"
               f"{guess}</span>", unsafe_allow_html=True)
    b.button("Delete", key=f"ev_del_{i}", on_click=_delete, args=(i,))
st.caption("Events are saved on this computer (state/laris_state.json) and kept after a restart.")
