"""The LARIS workspace: the five tools behind the five letters, drawn in one content area (no page change).
L Look Ahead · A Alert Before Stockout · R Reduce Waste · I Invest Within Budget · S Send & Sync."""
import streamlit as st

import laris_fx as fx
import laris_ui as ui
import planning
import store
from workspace import alerts, invest, look_ahead, send, waste

TOOLS = {  # letter: (tile name, full name, what it answers, renderer)
    "L": ("Look Ahead", "Look Ahead", "Demand for the next 7 days, what's rising, and how much extra to stock.",
          look_ahead.render),
    "A": ("Alert", "Alert Before Stockout", "What may run out before the next delivery, when, and what to do.",
          alerts.render),
    "R": ("Reduce Waste", "Reduce Waste", "Stock that may expire unsold or tie up cash, and how to buy less of it.",
          waste.render),
    "I": ("Invest", "Invest Within Budget", "The best order for your cash or supplier credit, and what was cut.",
          invest.render),
    "S": ("Send & Sync", "Send & Sync", "Share the order with your supplier, record each step and what arrives.",
          send.render),
}
ss = st.session_state
ctx = ss["ctx"]
if ss.get("tool") not in TOOLS:
    ss["tool"] = "L"
ui.require_plan(ctx)


def _badges():
    """Short outcome words on the tiles, from the same counts Home uses (text, so never colour alone)."""
    att = planning.attention(ctx)
    status = store.get("orders", {}).get(ctx["ref"], {}).get("status", "Draft")
    rising = int((ctx["plan"]["trend"] == "Growing").sum())
    left = ctx["budget_rm"] - ctx["order_rm"]
    sent = {"Draft": "not sent", "Ready to share": "not sent", "Shared": "sent, awaiting reply",
            "Acknowledged": "confirmed", "Received": "received", "Partly received": "part received"}
    return {"L": f"{rising} selling more" if rising else "demand steady",
            "A": f"{len(att['urgent'])} run out soon" if att["urgent"] else "all clear",
            "R": f"{len(att['waste'])} may go to waste" if att["waste"] else "all clear",
            "I": f"RM {left:,.0f} left" if left >= -0.5 else f"RM {-left:,.0f} over",
            "S": sent.get(status, status.lower())}


def _pick(letter):
    ss["tool"] = letter


badge = _badges()
items = [{"id": letter, "letter": letter, "name": tile, "badge": badge[letter]}
         for letter, (tile, full, desc, _) in TOOLS.items()]
if not fx.nav(items, ss["tool"], "laris_nav", _pick):     # static tiles when the motion layer is off
    with st.container(key="letters"):
        for col, (letter, (tile, full, desc, _)) in zip(st.columns(5), TOOLS.items()):
            with col.container(key=f"letter_{letter}"):
                st.button(f"**{letter}**{tile} · {badge[letter]}", key=f"tool_{letter}", help=f"{full}: {desc}",
                          on_click=_pick, args=(letter,), type="primary" if ss["tool"] == letter else "secondary",
                          width="stretch")

tile, full, desc, render = TOOLS[ss["tool"]]
st.markdown(ui.page_header(f"{ss['tool']} · {full}", full, desc), unsafe_allow_html=True)
render(ctx)
