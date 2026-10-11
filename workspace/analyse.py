"""A · Analyse: what has happened. A few key trends, not every chart."""
import altair as alt
import numpy as np
import streamlit as st

import laris_ui as ui
import planning


def render(ctx):
    cmp7 = planning.sales_compare(ctx, 7)
    _, t28 = planning.sales_summary(ctx, 28)
    inv = planning.inventory_table(ctx)
    chg = cmp7["change_pct"]
    ui.kpi_row(
        ui.kpi("Sales, last 7 days", ui.money(cmp7["revenue_rm"]),
               f"{chg:+.1f}% vs the week before" if np.isfinite(chg) else "no earlier week to compare"),
        ui.kpi("Sales, last 28 days", ui.money(t28["revenue"]), f"{t28['start']:%d %b} – {t28['end']:%d %b}"),
        ui.kpi("Gross profit, 28 days", ui.money(t28["gross_profit"]),
               f"{t28['margin_pct']:.1f}% margin" if np.isfinite(t28["margin_pct"]) else "no cost data"),
        ui.kpi("Stock value at cost", ui.money(inv["value_rm"].sum(skipna=True)),
               f"{int(inv['value_rm'].isna().sum())} product(s) without a cost price"
               if inv["value_rm"].isna().any() else "all products priced"))

    ui.section("Weekly sales and gross profit", "Daily sales history scaled to your weekly sales, priced at your "
                                                 "selling prices.")
    wk = planning.weekly_sales(ctx, 8)
    if wk.empty:
        st.caption("Not enough sales history yet.")
    else:
        long = wk.melt("week_start", ["revenue", "gross_profit"], "measure", "rm").replace(
            {"measure": {"revenue": "Sales", "gross_profit": "Gross profit"}})
        st.altair_chart(alt.Chart(long).mark_bar(cornerRadiusTopLeft=2, cornerRadiusTopRight=2).encode(
            x=alt.X("week_start:T", title="Week starting", axis=alt.Axis(format="%d %b", grid=False)),
            xOffset="measure:N", y=alt.Y("rm:Q", title="RM"),
            color=alt.Color("measure:N", scale=alt.Scale(domain=["Sales", "Gross profit"], range=[ui.chart_colors()["bar"], ui.chart_colors()["bar2"]]),
                            legend=alt.Legend(orient="top", title=None)),
            tooltip=[alt.Tooltip("week_start:T", format="%d %b"), "measure", alt.Tooltip("rm:Q", format=",.0f")])
            .properties(height=240).configure_view(strokeWidth=0), use_container_width=True)

    ui.section("What changed last week", "Units sold in the last 7 days vs the 7 days before.")
    cat = ui.category_filter(ctx, "an_cat")
    tr = ui.in_category(planning.product_trends(ctx, 7), cat)
    if tr.empty:
        st.caption("No product here has two weeks of history yet.")
    else:
        tr = tr.sort_values("change_pct", ascending=False)
        st.caption("Click a product for its details.")
        ui.product_table(tr[["product", "name", "units_prev", "units", "change_pct", "revenue"]], "an_trends",
                         "views/laris.py", column_config={
                         "name": "Product", "units_prev": st.column_config.NumberColumn("Week before", format="%d"),
                         "units": st.column_config.NumberColumn("Last week", format="%d"),
                         "change_pct": st.column_config.NumberColumn("Change", format="%+.0f%%"),
                         "revenue": st.column_config.NumberColumn("Sales last week (RM)", format="%.0f")})

    track = ctx["metrics"].get("model_vs_baselines_7day_ci", {})
    rows = [(k2, v) for k2, v in track.items() if k2 != "label"]
    if rows:
        better = sum(1 for _, v in rows if v["ci95"][1] < 0)
        st.markdown(ui.label("MEASURED", "measured") + f'<span class="lr-muted">How good are the forecasts? On held-out '
                    f"test weeks the AI model was clearly more accurate than {better} of {len(rows)} simple rules "
                    "(7-day totals, 95% confidence).</span>", unsafe_allow_html=True)
