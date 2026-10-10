from html import escape

import pandas as pd
import streamlit as st

import laris_core as core
import laris_ui as ui
import planning

ss = st.session_state
ss.setdefault("inputs_ver", 0)
ctx = ss["ctx"]
HERE = "views/products.py"
SORTS = {"Category": ("Category", True), "Name": ("Product", True), "Sales rank": ("Sales rank", True),
         "Profit rank": ("Profit rank", True), "Margin %": ("Margin %", False), "Stock": ("Stock", True)}


def _apply(new, warnings):
    ss.update(inputs=new, inputs_dirty=True, inputs_ver=ss["inputs_ver"] + 1,
              flash=["Stock plan updated."] + warnings)


def _ranked(view):
    """Last-7-day sales and gross profit in RM from the product list, with ranks (1 = best)."""
    v = view.copy()
    price, cost = v["Selling price (RM)"], v["Cost price (RM)"]
    v["Sales 7d (RM)"] = v["Sold last 7 days"] * price
    v["Profit 7d (RM)"] = v["Sold last 7 days"] * (price - cost)
    v["Margin %"] = ((price - cost) / price.where(price > 0) * 100).round(1)
    v["Sales rank"] = v["Sales 7d (RM)"].rank(ascending=False, method="min").astype(int)
    v["Profit rank"] = v["Profit 7d (RM)"].rank(ascending=False, method="min").astype(int)
    return v


def _set_category(product, key):
    inp = ss["inputs"].copy()
    if "Category" not in inp:
        inp.insert(2, "Category", inp["product"].map(core.category_map(inp)))
    inp.loc[inp["product"] == product, "Category"] = ss[key]
    ss.update(inputs=inp, inputs_dirty=True)


st.markdown(ui.label("SAMPLE SHOP", "placeholder") + '<span class="lr-muted">Preloaded with an illustrative kedai '
            "runcit. Your edits are kept while the app is open; reset the sample shop from Settings.</span>",
            unsafe_allow_html=True)

full = _ranked(planning.to_view(ss["inputs"]))
a, b, c = st.columns([1.3, 1.6, 1.4], vertical_alignment="bottom")
with a:
    view = st.segmented_control("View", ["List", "Cards"], **ui.sticky("pr_view", "List")) or "List"
sort = b.selectbox("Sort by", list(SORTS), **ui.sticky("pr_sort", "Category"))
go = c.button("Generate stock plan", type="primary", icon=":material/auto_awesome:", use_container_width=True)
cat = ui.category_filter(ctx, "pr_cat")
col, asc = SORTS[sort]
shown = ui.in_category(full, cat, "Category").sort_values([col, "Product"], ascending=[asc, True])

if view == "List":
    # ---------------- list view: edit everything, including the category ----------------
    st.markdown('<span class="lr-muted">Edit any cell, including the category. Add a product with the <b>+</b> button '
                "at the top right of the table, or select rows and press the bin to delete. Ranks use last week's "
                "sales and your prices; they refresh when you generate the plan.</span>", unsafe_allow_html=True)
    edited = st.data_editor(
        shown.reset_index(drop=True), key=f"products_{ss['inputs_ver']}_{cat}_{sort}", num_rows="dynamic",
        hide_index=True, use_container_width=True,
        disabled=["Sales 7d (RM)", "Profit 7d (RM)", "Margin %", "Sales rank", "Profit rank"],
        column_order=["Product", "Category", "Stock", "Sold last 7 days", "Cost price (RM)", "Selling price (RM)",
                      "Sales 7d (RM)", "Sales rank", "Profit 7d (RM)", "Profit rank", "Margin %", "Delivery days",
                      "Shelf life (days)", "Must-have"],
        column_config={
            "Product": st.column_config.TextColumn("Product", width="medium"),
            "Category": st.column_config.SelectboxColumn("Category", options=core.CATEGORIES, required=True),
            "Stock": st.column_config.NumberColumn("Stock (units)", min_value=0, format="%d"),
            "Sold last 7 days": st.column_config.NumberColumn("Sold last 7 days", min_value=0, format="%d"),
            "Cost price (RM)": st.column_config.NumberColumn("Cost (RM)", min_value=0.0, format="%.2f"),
            "Selling price (RM)": st.column_config.NumberColumn("Price (RM)", min_value=0.0, format="%.2f"),
            "Sales 7d (RM)": st.column_config.NumberColumn("Sales 7d (RM)", format="%.0f"),
            "Profit 7d (RM)": st.column_config.NumberColumn("Gross profit 7d (RM)", format="%.0f"),
            "Margin %": st.column_config.NumberColumn("Margin", format="%.0f%%"),
            "Sales rank": st.column_config.NumberColumn("Sales rank", format="#%d", help="1 = sells the most in RM"),
            "Profit rank": st.column_config.NumberColumn("Profit rank", format="#%d",
                                                         help="1 = earns the most gross profit"),
            "Delivery days": st.column_config.NumberColumn("Delivery days", min_value=1, format="%d",
                                                           help="Days from ordering to your supplier's delivery"),
            "Shelf life (days)": st.column_config.NumberColumn("Shelf life (days)", min_value=1, format="%d"),
            "Must-have": st.column_config.CheckboxColumn("Must-have", help="Essentials are funded first"),
        })
    # products hidden by the category filter are kept exactly as they are
    edited = pd.concat([edited, full[~full["product"].isin(shown["product"])]], ignore_index=True)
else:
    # ---------------- card view: one card per product; Details opens the full picture ----------------
    edited = full
    plan = ctx["plan"].set_index("product") if len(ctx["plan"]) else pd.DataFrame()
    if shown.empty:
        st.info("No products in this category.")
    records = shown.to_dict("records")
    for start in range(0, len(records), 3):
        for col_, r in zip(st.columns(3), records[start:start + 3]):
            pid = r["product"]
            with col_.container(key=f"pcard_{pid}"):
                action = ui.action_chip(plan.at[pid, "action"]) if pid in plan.index else ""
                st.markdown(
                    f'<div class="lr-pc-top"><div class="lr-pc-name">{escape(r["Product"])}</div>'
                    f'<div class="lr-pc-rank">#{r["Sales rank"]} sales · #{r["Profit rank"]} profit</div></div>'
                    f'<div class="lr-chips">{action}{ui.must_chip(r["Must-have"])}</div>'
                    f'<div class="lr-pc-grid"><div>Stock<b>{r["Stock"]:,.0f}</b></div>'
                    f'<div>Sold last 7 days<b>{r["Sold last 7 days"]:,.0f}</b></div>'
                    f'<div>Sales 7d<b>{ui.money(r["Sales 7d (RM)"])}</b></div>'
                    f'<div>Gross profit 7d<b>{ui.money(r["Profit 7d (RM)"])}</b></div></div>',
                    unsafe_allow_html=True)
                key = f"pc_cat_{pid}_{ss['inputs_ver']}"
                options = core.CATEGORIES if r["Category"] in core.CATEGORIES else core.CATEGORIES + [r["Category"]]
                st.selectbox("Category", options, index=options.index(r["Category"]), key=key,
                             on_change=_set_category, args=(pid, key))
                if pid in plan.index:
                    ui.why_button(pid, HERE, key=f"pc_open_{pid}", label="Details")
                else:
                    st.caption("New product: generate the stock plan to see details.")

if go:
    new, errors, warnings = planning.validate_products(edited, ss["inputs"], core.INPUT_COLUMNS)
    if errors:
        st.error("Please fix these before generating the plan:\n\n" + "\n".join(f"- {e}" for e in errors))
        for w in warnings:
            st.warning(w)
    else:
        _apply(new, warnings)
        ui.goto("views/home.py")
        st.rerun()
st.caption("New products have no sales history, so their forecast is a simple baseline from 'Sold last 7 days', "
           "not a trained-model prediction.")
