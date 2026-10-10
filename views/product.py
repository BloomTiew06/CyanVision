"""Product detail: everything about one product (recommendation, stock, forecast, why) and the one action that
matters here, changing this week's quantity. Opens from any product button; Back returns to where it came from."""
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
TOOL_NAME = {"L": "L · Look Ahead", "A": "A · Alert", "R": "R · Reduce Waste", "I": "I · Invest", "S": "S · Send & Sync"}
BACK_NAME = {"views/laris.py": TOOL_NAME.get(ss.get("tool"), "LARIS"), "views/home.py": "Home",
             "views/products.py": "Products", "views/insights.py": "Insights"}
anim = ui.first_view("page:product")

if ss.get("sel") not in names:
    ss["sel"] = plan["product"].iloc[0]
p = ss["sel"]
pl, r = plan.set_index("product").loc[p], rows.loc[p]
icon, name = ui.split_name(pl["name"])


def _use(product, key):
    ui.set_qty_from(product, key)
    ui.flash(f"{name}: this week's order is now {ss[key]:,.0f} units.")


def _reset(product, qty):
    ui.clear_qty(product)
    ui.flash(f"{name}: back to LARIS's {qty:,.0f} units.")


# ---------------- breadcrumb: back + switch product ----------------
with st.container(key="crumbs"):
    a, _, b = st.columns([1.6, 2, 1.6], vertical_alignment="center")
    a.button(f"Back to {BACK_NAME.get(back, 'LARIS')}", icon=":material/arrow_back:", on_click=ui.goto, args=(back,),
             key="pd_back", type="tertiary")
    ss["sel_w"] = ss["sel"]
    b.selectbox("Switch product", list(names), format_func=lambda x: ui.split_name(names[x])[1], key="sel_w",
                label_visibility="collapsed", on_change=lambda: ss.update(sel=ss["sel_w"]))

cover = f"{pl['cover_days']:,.1f} days" if np.isfinite(pl["cover_days"]) else "no sales expected"
src = {"model": "AI forecast", "baseline": "Simple forecast (last week's sales)", "unavailable": "No forecast"}[
    pl["forecast_source"]]
left, right = st.columns([1, 1.25], gap="medium")

# ---------------- left: the decision ----------------
with left.container(border=True, key="card_pd_head"):
    st.markdown(
        f'<div class="lr-pc{" lr-in" if anim else ""}"><div class="lr-avatar lr-avatar-lg" aria-hidden="true">'
        f'{escape(icon)}</div><div style="flex:1"><div class="lr-crumb">{escape(ui.category_of(p, ctx.get("inputs")))}'
        f'</div><p class="lr-title lr-title-md">{escape(name)}</p>'
        f'<div style="margin:6px 0 2px">{ui.action_chip(pl["action"])}{ui.must_chip(pl["must_have"])}'
        f'{ui.status_chip("URGENT") if pl["urgent"] else ""}</div></div></div>'
        f'<p class="lr-decision">{escape(pl["rec"])}.</p>'
        + (f'<p class="lr-muted" style="margin:0">{ui.label("ESTIMATED", "estimated")}{escape(pl["impact_txt"])} vs your '
           "usual order.</p>" if pl["impact_txt"] else ""), unsafe_allow_html=True)
    st.markdown(
        '<div class="lr-statgrid">'
        f'<div><span>Stock</span><b>{r["on_hand"] + r["on_order"]:,.0f}</b><em>units on hand</em></div>'
        f'<div><span>Lasts</span><b class="{"bad" if pl["cover_days"] < r["lead_time"] else ""}">{escape(cover)}</b>'
        f'<em>delivery takes {int(r["lead_time"])} day(s)</em></div>'
        f'<div><span>Sold last week</span><b>{r["demand_last7"]:,.0f}</b><em>trend {escape(pl["trend"].lower())}'
        + (f' ({pl["change"]:+.0%})' if pl["trend"] != "Stable" else "") + '</em></div>'
        f'<div><span>Order this week</span><b>{pl["order_qty"]:,.0f}'
        f'{ui.delta_chip(f"pd_qty:{p}", float(pl["order_qty"]), lambda x: f"{x:,.0f}")}</b>'
        f'<em>{ui.money(pl["order_rm"])}' + (f" · LARIS suggests {pl['qty']:,.0f}" if pl["adjusted"] else "")
        + '</em></div></div>', unsafe_allow_html=True)
    c1, c2 = st.columns([1.3, 1], vertical_alignment="bottom")
    c1.number_input("Quantity to order this week", min_value=0.0, value=float(pl["order_qty"]),
                    step=float(pl["pack_size"]), format="%.0f", key=f"pi_qty_{p}")
    c2.button("Use this quantity", type="primary", on_click=_use, args=(p, f"pi_qty_{p}"), width="stretch")
    if pl["adjusted"]:
        st.button(f"Back to LARIS's {pl['qty']:,.0f}", on_click=_reset, args=(p, pl["qty"]), key="pd_reset",
                  type="tertiary")

# ---------------- right: the forecast, and what really happened ----------------
with right.container(border=True, key="card_pd_chart"):
    a, b = st.columns([1.4, 1], vertical_alignment="center")
    a.markdown(f'<span class="lr-crumb">{escape(src)}</span><br><span class="lr-muted">Units per day: recorded sales '
               "(grey), 7-day forecast (green)</span>", unsafe_allow_html=True)
    reveal = b.toggle("Backtest: compare with actual sales", key="pd_reveal",
                      help="For a past week the actual sales are known.")
    chart, note = ui.forecast_chart(ctx, p, height=250, reveal=reveal)
    st.altair_chart(chart, width="stretch")
    if reveal:
        st.markdown(ui.reveal_note(ctx, p), unsafe_allow_html=True)
    st.caption(note)

# ---------------- why ----------------
could = [w[0].upper() + w[1:] + "." for w in r["low_why"]]
could.append("If your stock count or last week's sales are wrong, the recommendation will be too. Update them in "
             "Products.")
if r["forecast_source"] == "model":
    could.append("A promotion, local event or supplier delay the model doesn't know about could change demand.")
impact = f' {escape(pl["impact_txt"])} (estimate, compared with reordering last week\'s sales).' if pl["impact_txt"] else ""
st.markdown(
    '<div class="lr-why">'
    f'<h4>What we see</h4><p>{escape(r["why"][0][1])} {escape(pl["risk"])}</p>'
    f'<h4>Why it matters</h4><p>{escape(pl["why"])}</p>'
    f'<h4>What we recommend</h4><p>{escape(pl["rec"])}.{impact}</p>'
    '<h4>What could change this</h4><p>' + "<br>".join(escape(c) for c in could) + "</p></div>",
    unsafe_allow_html=True)
with st.expander("Show the evidence (AI forecast, calculations, track record, cautions, your settings)"):
    st.markdown(ui.evidence(r["why"]), unsafe_allow_html=True)
