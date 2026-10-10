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


def _apply(new, warnings):
    ss.update(inputs=new, inputs_dirty=True, inputs_ver=ss["inputs_ver"] + 1,
              flash=["Stock plan updated."] + warnings)


st.markdown(ui.label("SAMPLE SHOP", "placeholder") + '<span class="lr-muted">Preloaded with an illustrative kedai '
            "runcit. Your edits are kept while the app is open; reset the sample shop from Settings.</span>",
            unsafe_allow_html=True)
mode = st.segmented_control("View", ["Table", "Cards"], default="Table", key="prod_view",
                            label_visibility="collapsed") or "Table"

# ---------------- table view ----------------
if mode == "Table":
    top = st.columns([3, 1.4], vertical_alignment="center")
    top[0].markdown('<span class="lr-muted">Edit any cell. Add a product with the <b>+</b> button at the top right '
                    "of the table, or select rows and press the bin to delete. Fully empty rows are ignored.</span>",
                    unsafe_allow_html=True)
    go = top[1].button("Generate stock plan", type="primary", icon=":material/auto_awesome:", use_container_width=True)
    edited = st.data_editor(
        planning.to_view(ss["inputs"]), key=f"products_{ss['inputs_ver']}", num_rows="dynamic", hide_index=True,
        use_container_width=True, column_config={
            "product": None,
            "Product": st.column_config.TextColumn("Product", width="medium"),
            "Stock": st.column_config.NumberColumn("Stock (units)", min_value=0, format="%d"),
            "Sold last 7 days": st.column_config.NumberColumn("Sold last 7 days", min_value=0, format="%d"),
            "Cost price (RM)": st.column_config.NumberColumn("Cost (RM)", min_value=0.0, format="%.2f"),
            "Selling price (RM)": st.column_config.NumberColumn("Price (RM)", min_value=0.0, format="%.2f"),
            "Delivery days": st.column_config.NumberColumn("Delivery days", min_value=1, format="%d",
                                                           help="Days from ordering to your supplier's delivery"),
            "Shelf life (days)": st.column_config.NumberColumn("Shelf life (days)", min_value=1, format="%d"),
            "Must-have": st.column_config.CheckboxColumn("Must-have", help="Essentials are funded first"),
        })
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
    st.stop()

# ---------------- card view ----------------
ui.require_plan(ctx)
f1, f2, f3 = st.columns([2, 1.3, 1.3])
search = f1.text_input("Search products", key="pc_search", placeholder="e.g. milk")
sort = f2.selectbox("Sort by", list(planning.SORTS), key="pc_sort")
flt = f3.selectbox("Show", planning.FILTERS, key="pc_filter")
cards = planning.product_cards(ctx, sort, flt, search)
st.caption(f"{len(cards)} of {len(ctx['plan'])} products · revenue and gross profit are for the last 7 days "
           "(sample prices) · gross profit = revenue − cost of goods.")
if cards.empty:
    st.info("No products match. Clear the search or choose 'All products'.")


@st.dialog("Edit product")
def edit_dialog(product):
    view = planning.to_view(ss["inputs"])
    row = view[view["product"] == product].iloc[0]
    name = st.text_input("Product name", row["Product"])
    a, b = st.columns(2)
    stock = a.number_input("Stock (units)", min_value=0.0, value=float(row["Stock"]), step=1.0, format="%.0f")
    sold = b.number_input("Sold last 7 days", min_value=0.0, value=float(row["Sold last 7 days"]), step=1.0,
                          format="%.0f")
    cost = a.number_input("Cost price (RM)", min_value=0.0, value=float(row["Cost price (RM)"]), step=0.1, format="%.2f")
    price = b.number_input("Selling price (RM)", min_value=0.0, value=float(row["Selling price (RM)"]), step=0.1,
                           format="%.2f")
    lead = a.number_input("Delivery days", min_value=1, value=int(row["Delivery days"]), step=1)
    shelf = b.number_input("Shelf life (days)", min_value=1, value=int(row["Shelf life (days)"]), step=1)
    must = st.checkbox("Must-have", value=bool(row["Must-have"]))
    s, c = st.columns(2)
    if s.button("Save", type="primary", use_container_width=True):
        view = view.astype({"Product": object, "Must-have": object})
        view.loc[view["product"] == product, ["Product", "Stock", "Sold last 7 days", "Cost price (RM)",
                                              "Selling price (RM)", "Delivery days", "Shelf life (days)",
                                              "Must-have"]] = [name, stock, sold, cost, price, lead, shelf, must]
        new, errors, warnings = planning.validate_products(view, ss["inputs"], core.INPUT_COLUMNS)
        if errors:
            for e in errors:
                st.error(e)
        else:
            _apply(new, warnings)
            st.rerun()
    if c.button("Cancel", use_container_width=True):
        st.rerun()


for start in range(0, len(cards), 3):
    for col, r in zip(st.columns(3), list(cards.iloc[start:start + 3].itertuples())):
        with col.container(border=True):
            st.markdown(f'<span class="lr-name">{escape(r.name)}</span><br>{ui.action_chip(r.action)}'
                        f'{ui.must_chip(r.must_have)}{ui.status_chip("URGENT") if r.urgent else ""}',
                        unsafe_allow_html=True)
            margin = f" ({r.margin_pct:.0f}%)" if pd.notna(r.margin_pct) else ""
            st.markdown(f"Stock **{r.stock:,.0f}** · sold **{r.sold7:,.0f}** last week  \n"
                        f"Revenue {ui.money(r.revenue)} · gross profit {ui.money(r.gross_profit)}{margin}  \n"
                        f"Order this week: **{r.order_qty:,.0f}** (usually {r.usual:,.0f})")
            st.caption(r.risk)
            a, b = st.columns(2)
            with a:
                ui.why_button(r.product, HERE, key=f"pc_why_{r.product}", label="Details")
            if b.button("Edit", key=f"pc_edit_{r.product}", use_container_width=True,
                        help="Edit the product or adjust its stock"):
                edit_dialog(r.product)
