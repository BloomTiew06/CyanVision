"""L · Look Up: find a product and see where it stands (stock, sales, forecast, reorder point, this week's order)."""
from html import escape

import numpy as np
import streamlit as st

import laris_ui as ui
import planning

HERE = "views/laris.py"


def render(ctx):
    a, b = st.columns([3, 1.4], vertical_alignment="bottom")
    q = a.text_input("Find a product", placeholder="Type part of a name, e.g. milk", **ui.sticky("lu_q", ""))
    only = b.selectbox("Show", ["All products", "Running low", "Forecast unavailable"],
                       **ui.sticky("lu_show", "All products"))
    cat = ui.category_filter(ctx, "lu_cat")
    t = ui.in_category(planning.lookup_table(ctx, q), cat)
    if only == "Running low":
        low = set(planning.inventory_table(ctx).query("status in ['Low', 'Out of stock']")["product"])
        t = t[t["product"].isin(low)]
    elif only == "Forecast unavailable":
        t = t[t["source"] == planning.SOURCE_LABEL["unavailable"]]
    t = t.reset_index(drop=True)
    if t.empty:
        st.info("No product matches. Clear the search or choose 'All' categories.")
        return
    show = t.assign(lasts=t["cover_days"].map(lambda c: f"{c:.1f} days" if np.isfinite(c) else "no sales expected"))
    st.caption("Click a product to see it below. Forecasts come from the same data as every other screen.")
    event = st.dataframe(
        show[["name", "group", "stock", "sold7", "forecast", "source", "lasts", "reorder_point", "order_qty", "action"]],
        hide_index=True, use_container_width=True, on_select="rerun", selection_mode="single-cell", key="lu_table",
        column_config={"name": st.column_config.TextColumn("Product", width="medium"), "group": "Category",
                       "stock": st.column_config.NumberColumn("Stock", format="%d"),
                       "sold7": st.column_config.NumberColumn("Sold last 7 days", format="%d"),
                       "forecast": st.column_config.TextColumn("Forecast, next 7 days"),
                       "source": st.column_config.TextColumn("Forecast from"), "lasts": "Stock lasts",
                       "reorder_point": st.column_config.NumberColumn("Reorder at", format="%d",
                                                                      help="Order when stock falls to this level"),
                       "order_qty": st.column_config.NumberColumn("Order this week", format="%d"), "action": "Plan"})
    cells = event.selection.cells if event is not None and event.selection else []
    if cells and cells[0][0] < len(t):
        st.session_state["_keep_lu_pick"] = t.iloc[cells[0][0]]["product"]
    pick = st.session_state.get("_keep_lu_pick")
    if pick not in set(t["product"]):
        pick = t["product"].iloc[0]
    _detail(ctx, pick)


def _detail(ctx, p):
    pl = ctx["plan"].set_index("product").loc[p]
    r = ctx["rows"].set_index("product").loc[p]
    st.markdown(f'<div class="lr-section">{escape(pl["name"])}</div><div class="lr-chips">'
                f'{ui.action_chip(pl["action"])}{ui.must_chip(pl["must_have"])}{ui.cat_chip(pl["group"])}'
                f'<span class="lr-muted">{escape(pl["rec"])}</span></div>', unsafe_allow_html=True)
    ui.kpi_row(
        ui.kpi("Stock", f"{r['on_hand'] + r['on_order']:,.0f}", "units on hand"),
        ui.kpi("Forecast, 7 days", planning.forecast_text(pl["forecast_7d"], pl["forecast_source"]),
               planning.SOURCE_LABEL[pl["forecast_source"]]),
        ui.kpi("Stock lasts", f"{pl['cover_days']:.1f} days" if np.isfinite(pl["cover_days"]) else "–",
               f"delivery takes {r['lead_time']} day(s)", "bad" if pl["cover_days"] < r["lead_time"] else None),
        ui.kpi("Order this week", f"{pl['order_qty']:,.0f}", ui.money(pl["order_rm"])))
    chart, note = ui.forecast_chart(ctx, p, height=230)
    st.altair_chart(chart, use_container_width=True)
    st.caption(note)
    a, b = st.columns([4, 1.2], vertical_alignment="center")
    a.markdown(f'<span class="lr-muted">{escape(pl["why"])}</span>', unsafe_allow_html=True)
    with b:
        ui.why_button(p, HERE, key="lu_more", label="Full details")
