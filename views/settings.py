"""Settings: each function in its own section, saved where the rest of LARIS reads it."""
from html import escape
from urllib.parse import urlparse

import pandas as pd
import streamlit as st

import assistant
import laris_ui as ui
import store

ss = st.session_state
ctx = ss["ctx"]
TITLES = ["Encik", "Puan", "Cik", "Tuan", "Mr.", "Mrs.", "Ms.", "Dr.", "(none)"]


def _seed(widget_key, value):
    if widget_key not in ss:
        ss[widget_key] = value


def _save_prefs(fields):
    """fields: {pref name: widget key}. Saves to state/laris_state.json; the app reads it on every run."""
    prefs = store.get("prefs", {})
    prefs.update({f: ss[k] for f, k in fields.items()})
    store.put("prefs", prefs)
    ss["set_msg"] = "Saved."


prefs = store.get("prefs", {})

# ---------------- shop & owner ----------------
with st.expander("Shop and owner", expanded=True, icon=":material/storefront:"):
    with st.form("f_shop"):
        a, b = st.columns(2)
        shop = a.text_input("Shop name", value=ss["shop_name"])
        place = b.text_input("Location", value=ss["shop_place"])
        c, d = st.columns([1, 2])
        title = c.selectbox("How should LARIS address you?", TITLES,
                            index=TITLES.index(ss["title"]) if ss["title"] in TITLES else len(TITLES) - 1)
        owner = d.text_input("Your name", value=ss["owner"])
        if st.form_submit_button("Save", type="primary"):
            if not shop.strip() or not owner.strip():
                st.error("Shop name and your name can't be empty.")
            else:
                store.put("prefs", {**store.get("prefs", {}), "shop_name": shop.strip(), "shop_place": place.strip(),
                                    "title": title, "owner": owner.strip()})
                st.success("Saved. Home will greet you as "
                           f"{(title + ' ') if title != '(none)' else ''}{owner.strip()}.")

# ---------------- supplier ----------------
with st.expander("Supplier", icon=":material/local_shipping:"):
    with st.form("f_supplier"):
        name = st.text_input("Supplier name", value=ss["supplier_name"])
        phone = st.text_input("Supplier WhatsApp number", value=ss["supplier_phone"],
                              help="With country code, e.g. 60123456789. Used only to open a WhatsApp draft.")
        if st.form_submit_button("Save", type="primary"):
            digits = "".join(ch for ch in phone if ch.isdigit())
            if phone.strip() and len(digits) < 8:
                st.error("That number looks too short. Include the country code, e.g. 60123456789.")
            else:
                store.put("prefs", {**store.get("prefs", {}), "supplier_name": name.strip(), "supplier_phone": digits})
                st.success("Saved. Orders will open WhatsApp drafts addressed to this number.")

# ---------------- budget ----------------
with st.expander("Budget", icon=":material/payments:"):
    st.number_input("Budget for this week's order (RM)", min_value=0.0, step=10.0, format="%.0f",
                    **ui.bind("set_budget", "budget_rm"))
    st.caption(f"The full recommended order costs {ui.money(ctx['ideal_rm'])}. The same budget box is in the top bar.")
    st.radio("When cash is short", ["essentials", "value"], horizontal=True, **ui.bind("set_strategy", "strategy"),
             format_func={"essentials": "Protect essentials first (recommended)",
                          "value": "Best value per ringgit"}.get)

# ---------------- alerts & reminders ----------------
with st.expander("Alerts and reminders", icon=":material/notifications:"):
    names = dict(zip(ctx["plan"]["product"], ctx["plan"]["name"])) if not ctx["empty"] else {}
    _seed("pf_urgent", prefs.get("urgent", True))
    _seed("pf_evening", prefs.get("evening", False))
    _seed("pf_muted", [p for p in prefs.get("muted", []) if p in names])
    _seed("pf_snooze", pd.Timestamp(prefs["snooze_until"]).date() if prefs.get("snooze_until") else None)
    fields = {"urgent": "pf_urgent", "evening": "pf_evening", "muted": "pf_muted"}
    st.toggle("Urgent stock alerts", key="pf_urgent", on_change=_save_prefs, args=(fields,))
    st.toggle("Evening summary", key="pf_evening", on_change=_save_prefs, args=(fields,))
    st.multiselect("Mute alerts for these products", list(names), format_func=names.get, key="pf_muted",
                   on_change=_save_prefs, args=(fields,), help="Muted products are left out of 'Act today' in Recommend.")
    st.date_input("Snooze order reminders until", key="pf_snooze",
                  on_change=lambda: store.put("prefs", {**store.get("prefs", {}), "snooze_until":
                                                        str(ss["pf_snooze"]) if ss["pf_snooze"] else None}))
    st.markdown(ui.label("NOT CONNECTED", "planned") + '<span class="lr-muted">These preferences are saved, but LARIS '
                "has no notification service yet, so no alerts or reminders are actually sent. Muting works inside "
                "the app.</span>", unsafe_allow_html=True)

# ---------------- local events ----------------
with st.expander("Local events", icon=":material/event:"):
    st.caption("Paydays, school events, a nearby factory shift: note them so you remember to check stock. LARIS's "
               "forecast does not use these events yet, so they don't change any numbers.")
    events = store.get("events", [])
    as_of = ctx["week"]["as_of"]
    with st.form("event_form", clear_on_submit=True):
        a, b, c = st.columns([2, 1, 1])
        ev_name = a.text_input("Event name", placeholder="e.g. School sports day")
        start = b.date_input("Start", value=as_of.date())
        stop = c.date_input("End", value=as_of.date())
        notes = st.text_input("Notes (optional)")
        assumed = st.number_input("Your guess of the effect on sales, % (optional; saved as a note, not applied)",
                                  value=0, step=5)
        if st.form_submit_button("Save event", type="primary"):
            if not ev_name.strip():
                st.error("Give the event a name.")
            elif stop < start:
                st.error("The end date is before the start date.")
            else:
                events.append({"name": ev_name.strip(), "start": str(start), "end": str(stop), "notes": notes.strip(),
                               "assumed_change_pct": assumed or None, "saved": store.now()})
                store.put("events", events)
                st.rerun()

    def _delete(i):
        ev = store.get("events", [])
        ev.pop(i)
        store.put("events", ev)

    for i, e in enumerate(events):
        a, b = st.columns([6, 1], vertical_alignment="center")
        guess = f" · your guess {e['assumed_change_pct']:+}% (not applied)" if e.get("assumed_change_pct") else ""
        a.markdown(f"**{escape(e['name'])}** <span class='lr-muted'>{e['start']} to {e['end']}"
                   f"{' · ' + escape(e['notes']) if e['notes'] else ''}{guess}</span>", unsafe_allow_html=True)
        b.button("Delete", key=f"ev_del_{i}", on_click=_delete, args=(i,))

# ---------------- assistant ----------------
with st.expander("Assistant (AI)", icon=":material/smart_toy:"):
    try:
        secrets = dict(st.secrets)
    except Exception:
        secrets = {}
    cfg = assistant.config(secrets)
    if cfg["enabled"]:
        st.success(f"AI assistant is on: model {cfg['model']} at {urlparse(cfg['base_url']).netloc}.")
        if st.button("Test the connection"):
            with st.spinner("Checking…"):
                ok, msg = assistant.check_connection(cfg)
            (st.success if ok else st.error)(msg)
    else:
        st.info("The AI assistant is off, so Home answers common questions with quick answers from LARIS's own "
                "calculations.")
    st.markdown("""
**To turn it on**, set these before starting the app (environment variables, or `.streamlit/secrets.toml`):

| Name | What |
|---|---|
| `AI_API_KEY` | API key for an OpenAI-compatible chat service |
| `AI_MODEL` | The model name that service gives you |
| `AI_BASE_URL` | Optional. The service's API address (default `https://api.openai.com/v1`) |

Keys are read on the server only and never shown in the browser. The assistant only sees product-level figures
from LARIS's tools, never your name or supplier contacts. It can't change anything without your confirmation.
""")

# ---------------- sample data ----------------
with st.expander("Sample data (demo only)", icon=":material/dataset:"):
    st.markdown(ui.label("SAMPLE", "placeholder") + '<span class="lr-muted">These controls choose which past week '
                "and store pattern the demo replays. They are not real shop settings.</span>", unsafe_allow_html=True)
    days, stores = ss["_days"], ss["_stores"]
    a, b = st.columns(2)
    a.selectbox("Week to replay", days, format_func=lambda d: f"{d:%d %b} – {d + pd.Timedelta(days=6):%d %b %Y}",
                **ui.bind("set_week", "as_of"))
    b.selectbox("Sales pattern from store", stores, **ui.bind("set_store", "store"))
    st.caption(f"Data source: {ctx['metrics'].get('data_source', 'unknown')}.")

    def _reset():
        for k in ("inputs_key", "inputs", "budget_rm"):
            ss.pop(k, None)
        ss.update(order_adj={}, inputs_dirty=False, reset_ok=False, inputs_ver=ss.get("inputs_ver", 0) + 1,
                  flash=["The sample shop was reloaded for this week."])

    st.checkbox("I understand this replaces my products and order changes", key="reset_ok")
    st.button("Reset to sample shop", on_click=_reset, disabled=not ss.get("reset_ok"))

if ss.pop("set_msg", None):
    st.toast("Saved.")
