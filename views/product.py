from html import escape

import numpy as np
import streamlit as st

import laris_ui as ui

ss = st.session_state
ctx = ss["ctx"]
ui.require_plan(ctx)
plan = ctx["plan"]
rows = ctx["rows"].set_index("product")
names = dict(zip(plan["product"], plan["name"]))
back = ss.get("back_to", "views/laris.py")

a, b = st.columns([1, 3], vertical_alignment="center")
a.button("Back", icon=":material/arrow_back:", on_click=ui.goto, args=(back,), use_container_width=True)
if ss.get("sel") not in names:
    ss["sel"] = plan["product"].iloc[0]
ss["sel_w"] = ss["sel"]
b.selectbox("Product", list(names), format_func=names.get, key="sel_w", label_visibility="collapsed",
            on_change=lambda: ss.update(sel=ss["sel_w"]))
p = ss["sel"]
pl, r = plan.set_index("product").loc[p], rows.loc[p]

# ---------------- identity, action, quantity, impact ----------------
st.markdown(ui.page_header(f"Product detail · {pl['group']}", pl["name"], "", small=True)
            + f'<div class="lr-chips">{ui.action_chip(pl["action"])}{ui.must_chip(pl["must_have"])}'
            + (ui.status_chip("URGENT") if pl["urgent"] else "") + f'<b>{escape(pl["rec"])}</b></div>'
            + (f'<div class="lr-chips">{ui.label("ESTIMATED", "estimated")}<span class="lr-impact">'
               f'{escape(pl["impact_txt"])} vs your usual order</span></div>' if pl["impact_txt"] else ""),
            unsafe_allow_html=True)
mine = f" · your change (LARIS suggests {pl['qty']:,.0f})" if pl["adjusted"] else ""
cover = f"{pl['cover_days']:,.1f} days" if np.isfinite(pl["cover_days"]) else "no sales expected"
ui.kpi_row(
    ui.kpi("Current stock", f"{r['on_hand'] + r['on_order']:,.0f}", "units on hand"),
    ui.kpi("Sold last 7 days", f"{r['demand_last7']:,.0f}",
           f"trend: {pl['trend'].lower()}" + (f" ({pl['change']:+.0%})" if pl["trend"] != "Stable" else "")),
    ui.kpi("Stock lasts", cover, f"delivery takes {r['lead_time']} day(s)",
           "bad" if pl["cover_days"] < r["lead_time"] else None),
    ui.kpi("Order this week", f"{pl['order_qty']:,.0f} units", f"{ui.money(pl['order_rm'])}{mine}"))

left, right = st.columns([1.7, 1], gap="medium")
# ---------------- forecast chart ----------------
with left, st.container(key="tile_chart"):
    st.markdown('<div class="lr-section" style="margin-top:0">Sales and forecast</div>', unsafe_allow_html=True)
    chart, note = ui.forecast_chart(ctx, p, height=260)
    st.altair_chart(chart, use_container_width=True)
    st.caption(note)

# ---------------- change the order ----------------
with right, st.container(key="tile_order"):
    st.markdown('<div class="lr-section" style="margin-top:0">Change the order</div>', unsafe_allow_html=True)
    st.number_input("Quantity to order", min_value=0.0, value=float(pl["order_qty"]), step=float(pl["pack_size"]),
                    format="%.0f", key=f"pi_qty_{p}")
    st.button("Use this quantity", type="primary", on_click=ui.set_qty_from, args=(p, f"pi_qty_{p}"),
              use_container_width=True)
    st.button(f"Back to LARIS's {pl['qty']:,.0f}", on_click=ui.clear_qty, args=(p,), disabled=not pl["adjusted"],
              use_container_width=True)
    st.caption("Changes apply to this week's order on every page.")

# ---------------- explanation ----------------
could = [w[0].upper() + w[1:] + "." for w in r["low_why"]]
could.append("If your stock count or last week's sales are wrong, the recommendation will be too. Update them in "
             "Products.")
if r["forecast_source"] == "model":
    could.append("A promotion, local event or supplier delay the model doesn't know about could change demand.")
impact = f' {escape(pl["impact_txt"])} (estimate, compared with reordering last week\'s sales).' if pl["impact_txt"] else ""
with st.container(key="tile_why"):
    st.markdown(
        '<div class="lr-why">'
        f'<h4>What we see</h4><p>{escape(r["why"][0][1])} {escape(pl["risk"])}</p>'
        f'<h4>Why it matters</h4><p>{escape(pl["why"])}</p>'
        f'<h4>What we recommend</h4><p>{escape(pl["rec"])}.{impact}</p>'
        '<h4>What could change this</h4><p>' + "<br>".join(escape(c) for c in could) + "</p></div>",
        unsafe_allow_html=True)
with st.expander("Show the evidence (AI forecast, calculations, track record, cautions, your settings)"):
    st.markdown(ui.evidence(r["why"]), unsafe_allow_html=True)
