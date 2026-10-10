from datetime import datetime
from html import escape

import streamlit as st

import laris_ui as ui
import planning

ss = st.session_state
ctx = ss["ctx"]
ui.require_plan(ctx)
plan, as_of = ctx["plan"], ctx["week"]["as_of"]
HERE = "views/home.py"

hour = datetime.now().hour
greet = "Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening"
st.markdown(ui.page_header(f"WEEK OF {as_of:%d %b %Y}".upper(), f"{greet}, {ss['owner']}.",
                           "Here's what needs your attention this week."), unsafe_allow_html=True)

# ---------------- A. insights recap ----------------
found = planning.insights(ctx)
if not any(level in ("URGENT", "WARNING") for level, _, _ in found):
    st.markdown('<div class="lr-insight info">Your inventory is generally on track. Review the suggested order below.'
                '</div>', unsafe_allow_html=True)
for level, text, page in found[:4]:
    a, b = st.columns([6, 1.2], vertical_alignment="center")
    a.markdown(f'<div class="lr-insight {level.lower()}">{ui.status_chip(level)}{escape(text)}</div>',
               unsafe_allow_html=True)
    b.page_link(page, label="Review", icon=":material/arrow_forward:")

# ---------------- B. order summary + send ----------------
order_rm, budget = ctx["order_rm"], ctx["budget_rm"]
left = budget - order_rm
lines = [f"RM {left:,.0f} of your budget left." if left >= -0.5 else
         f"<b>Your order exceeds your budget by RM {-left:,.0f}.</b>"]
if ctx["budget_limited"]:
    lines.append(f"Your budget doesn't cover the full recommended order (RM {ctx['ideal_rm']:,.0f}), so this is the "
                 "best order within it.")
n_adj = int(plan["adjusted"].sum())
if n_adj:
    lines.append(f"Includes your changes to {n_adj} product(s).")
with st.container(border=True):
    a, b = st.columns([3, 2], vertical_alignment="center")
    a.markdown(f'<div class="lr-big">Your order: {ui.money(order_rm)} <small>of {ui.money(budget)}</small></div>'
               f'<p class="lr-muted" style="margin-top:6px">{" ".join(lines)}</p>', unsafe_allow_html=True)
    with b:
        has_order = bool((plan["order_qty"] > 0).any())
        msg = planning.order_message(plan, ctx["shop"], as_of, ctx["ref"])
        st.link_button("Send order on WhatsApp", planning.whatsapp_url(msg, ss.get("supplier_phone")),
                       type="primary", icon=":material/send:", use_container_width=True, disabled=not has_order)
        st.caption("Opens a WhatsApp draft for you to check and send. LARIS doesn't send anything."
                   if has_order else "Nothing to order this week.")
        st.page_link("views/send.py", label="Edit or track this order", icon=":material/fact_check:")

# ---------------- C. order list, grouped by action ----------------
st.markdown('<div class="lr-section">Your order list</div>', unsafe_allow_html=True)
pick = st.segmented_control("Show", ["All"] + [planning.ACTION_LABEL[a] for a in ui.ACTIONS], default="All",
                            key="home_filter", label_visibility="collapsed") or "All"
st.markdown(ui.label("ESTIMATED", "estimated") + '<span class="lr-muted">RM impact compares LARIS\'s quantity with '
            "reordering last week's sales (expected lost profit plus waste). It's an estimate, not guaranteed savings."
            "</span>", unsafe_allow_html=True)


def product_row(r):
    with st.container(key=f"row_{r.Index}"):
        a, b, c, d = st.columns([3.1, 2.1, 3.2, 1.3], vertical_alignment="center")
        price = r.unit_cost + r.margin
        margin = f"{r.margin / price:.0%} margin" if price > 0 else "no price"
        a.markdown(f'<span class="lr-name">{escape(r.name)}</span><br>{ui.action_chip(r.action)}'
                   f'{ui.must_chip(r.must_have)}<span class="lr-muted">{margin}</span>', unsafe_allow_html=True)
        mine = f'<br><span class="lr-muted">Your change · LARIS suggests {r.qty:,.0f}</span>' if r.adjusted else ""
        b.markdown(f'<div class="lr-qty">{r.order_qty:,.0f} <span>to order · usually {r.usual:,.0f}</span></div>{mine}',
                   unsafe_allow_html=True)
        impact = f'<span class="lr-impact">{escape(r.impact_txt)}</span><br>' if r.impact_txt else ""
        c.markdown(f'{impact}<span class="lr-muted">{escape(r.risk)}</span>', unsafe_allow_html=True)
        with d:
            ui.why_button(r.product, HERE, key=f"why_{r.product}")
            with st.popover("Adjust", use_container_width=True):
                k = f"adj_{r.product}"
                st.number_input(f"Quantity for {r.name}", min_value=0.0, step=float(r.pack_size), format="%.0f",
                                value=float(r.order_qty), key=k)
                st.button("Use this quantity", key=f"set_{r.product}", on_click=ui.set_qty_from,
                          args=(r.product, k), type="primary")
                if r.adjusted:
                    st.button(f"Back to LARIS's {r.qty:,.0f}", key=f"clr_{r.product}", on_click=ui.clear_qty,
                              args=(r.product,))


for action in ui.ACTIONS:
    label = planning.ACTION_LABEL[action]
    group = plan[plan["action"] == action]
    if pick not in ("All", label) or group.empty:
        continue
    if action == "MAINTAIN" and pick == "All":
        with st.expander(f"{label} ({len(group)}): {planning.ACTION_HELP[action]}"):
            for r in group.itertuples():
                product_row(r)
        continue
    st.markdown(f'<div class="lr-section">{label.upper()} ({len(group)})</div>'
                f'<p class="lr-help">{planning.ACTION_HELP[action]}</p>', unsafe_allow_html=True)
    for r in group.itertuples():
        product_row(r)
if pick != "All" and plan[plan["action"].map(planning.ACTION_LABEL) == pick].empty:
    st.info(f"No products in '{pick}' this week.")

# ---------------- D. shortcuts ----------------
st.markdown('<div class="lr-section">Go deeper</div>', unsafe_allow_html=True)
for col, (path, text) in zip(st.columns(5), [("views/look_ahead.py", "L · Look Ahead"),
                                             ("views/alerts.py", "A · Alert Before Stockout"),
                                             ("views/waste.py", "R · Reduce Waste"),
                                             ("views/budget.py", "I · Invest Within Budget"),
                                             ("views/send.py", "S · Send & Sync")]):
    col.page_link(path, label=text)
