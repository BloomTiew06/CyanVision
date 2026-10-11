"""S · Sales: revenue, gross profit and margin, best sellers, and products that deserve attention."""
from html import escape

import altair as alt
import streamlit as st

import laris_ui as ui
import planning

HERE = "views/laris.py"


def render(ctx):

    period = st.segmented_control("Period", list(planning.PERIODS), **ui.sticky("sales_period", "Last 28 days")) \
        or "Last 28 days"
    df, tot = planning.sales_summary(ctx, planning.PERIODS[period])
    st.markdown(f'<span class="lr-muted">{tot["start"]:%d %b %Y} – {tot["end"]:%d %b %Y} ({tot["days"]} days). '
                "Daily sales history scaled to your weekly sales, priced with your selling prices and costs.</span>",
                unsafe_allow_html=True)

    # ---------------- A. summary ----------------
    ui.kpi_row(ui.kpi("Revenue", ui.money(tot["revenue"]), "units sold × selling price"),
               ui.kpi("Cost of goods sold", ui.money(tot["cogs"]), "units sold × cost price"),
               ui.kpi("Gross profit", ui.money(tot["gross_profit"]), "revenue − cost of goods"),
               ui.kpi("Gross margin", f"{tot['margin_pct']:.1f}%" if tot["margin_pct"] == tot["margin_pct"] else "–",
                      "gross profit ÷ revenue"))
    notes = ["Gross figures: rent, wages, electricity and other running costs aren't included, so this is not net profit."]
    if tot["no_history"]:
        notes.append(f"{tot['no_history']} product(s) have no sales history for this period and are left out.")
    if tot["no_cost"]:
        notes.append(f"{tot['no_cost']} product(s) have no cost price, so they're left out of profit and margin.")
    st.caption(" ".join(notes))

    # ---------------- B/C. revenue and gross profit rankings ----------------
    a, b = st.columns([2.2, 1], vertical_alignment="center")
    with a:
        cat = ui.category_filter(ctx, "sales_cat")
    with b:
        n = st.segmented_control("Show", ["Top 5", "Top 10", "Top 20", "All"], label_visibility="collapsed",
                                 **ui.sticky("sales_top", "Top 10")) or "Top 10"
    df = ui.in_category(df, cat)
    limit = None if n == "All" else int(n.split()[1])


    def ranking(col, title):
        d = df.dropna(subset=[col])
        d = d[d[col] != 0].sort_values(col, ascending=False)
        d = d.head(limit) if limit else d
        if d.empty:
            st.caption("No data for this period.")
            return
        base = alt.Chart(d).encode(y=alt.Y("name:N", sort="-x", title=None, axis=alt.Axis(labelLimit=220)))
        cc = ui.chart_colors()
        bars = base.mark_bar(color=cc["bar"], cornerRadiusEnd=2).encode(
            x=alt.X(f"{col}:Q", title=title), tooltip=["name", alt.Tooltip(f"{col}:Q", format=",.2f", title=title)])
        text = base.mark_text(align="left", dx=4, color=cc["text"], fontSize=11).encode(
            x=f"{col}:Q", text=alt.Text(f"{col}:Q", format=",.0f"))
        st.altair_chart((bars + text).properties(height=max(160, 28 * len(d))), use_container_width=True)


    a, b = st.columns(2)
    with a:
        ui.section("Revenue by product", "What brings money in.")
        ranking("revenue", "Revenue (RM)")
    with b:
        ui.section("Gross profit by product", "What you keep after the cost of goods. High revenue isn't always high profit.")
        ranking("gross_profit", "Gross profit (RM)")

    # ---------------- D. margin ----------------
    ui.section("Gross margin %", "The share of each ringgit of sales you keep. A high percentage on a slow seller can still "
                                 "mean little profit in RM.")
    m = df.dropna(subset=["margin_pct"]).sort_values("margin_pct", ascending=False)
    st.caption("Click a product for its details.")
    ui.product_table(m[["product", "name", "units", "revenue", "gross_profit", "margin_pct"]], "sales_margin", HERE,
                         column_config={"name": "Product", "units": st.column_config.NumberColumn("Units sold", format="%.0f"),
                                    "revenue": st.column_config.NumberColumn("Revenue (RM)", format="%.0f"),
                                    "gross_profit": st.column_config.NumberColumn("Gross profit (RM)", format="%.0f"),
                                    "margin_pct": st.column_config.ProgressColumn("Gross margin", format="%.0f%%",
                                                                                  min_value=0, max_value=100)})
    st.caption("Products with no revenue in this period or no cost price aren't ranked.")

    # ---------------- E. insights ----------------
    ui.section("What to look at", "Findings that connect sales to your stock decisions.")
    found = planning.profit_insights(ctx, df)
    if not found:
        st.caption("Nothing stands out for this period.")
    for i, (title, text, product, page) in enumerate(found[:8]):
        a, b, c = st.columns([5, 1.2, 1.2], vertical_alignment="center")
        a.markdown(f"**{escape(title)}.** {escape(text)}")
        with b:
            ui.why_button(product, HERE, key=f"si_why_{i}", label="View product")
        if page.startswith("views/"):
            c.page_link(page, label="Review", icon=":material/arrow_forward:")
        else:
            with c:
                ui.tool_button(page, "Review", key=f"si_go_{i}")
