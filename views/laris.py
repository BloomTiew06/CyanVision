"""The LARIS workspace: five tools behind five letters, drawn in one content area (no page change)."""
import streamlit as st

import laris_ui as ui
from workspace import analyse, inventory, lookup, recommend, sales

TOOLS = {  # letter: (name, what it answers, renderer)
    "L": ("Look Up", "Find a product: stock, forecast, reorder point and this week's order.", lookup.render),
    "A": ("Analyse", "What has happened: sales, profit and demand trends.", analyse.render),
    "R": ("Recommend", "What to do this week: what to buy, how much, and why.", recommend.render),
    "I": ("Inventory", "Your stock: what's low, out or excess, its value, and stock counts.", inventory.render),
    "S": ("Sales", "Revenue, gross profit and margin, best sellers.", sales.render),
}
ss = st.session_state
ctx = ss["ctx"]
if ss.get("tool") not in TOOLS:
    ss["tool"] = "L"


def _pick(letter):
    ss["tool"] = letter


with st.container(key="letters"):
    for col, (letter, (name, desc, _)) in zip(st.columns(5), TOOLS.items()):
        with col.container(key=f"letter_{letter}"):
            st.button(f"**{letter}**{name}", key=f"tool_{letter}", help=desc, on_click=_pick, args=(letter,),
                      type="primary" if ss["tool"] == letter else "secondary", use_container_width=True)

name, desc, render = TOOLS[ss["tool"]]
st.markdown(ui.page_header(f"{ss['tool']} · {name}", name, desc), unsafe_allow_html=True)
ui.require_plan(ctx)
render(ctx)
