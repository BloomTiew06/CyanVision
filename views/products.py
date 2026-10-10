"""Products: the shop's catalogue (cards with search, category and status filters), the editable product table, and
stock levels with explicit stock counts. Edits go through planning.validate_products, as before."""
from html import escape

import numpy as np
import pandas as pd
import streamlit as st

import laris_core as core
import laris_ui as ui
import planning
from workspace import inventory

ss = st.session_state
ss.setdefault("inputs_ver", 0)
ctx = ss["ctx"]
HERE = "views/products.py"
STATUS_FILTERS = ["Low or out", "Excess", "Expiry risk", "Must-have", "Buy more"]
SORTS = {"Most urgent": None, "Name (A–Z)": ("name", True), "Lowest stock cover": ("cover_days", True),
         "Highest stock value": ("value_rm", False), "Most sold last week": ("sold7", False)}
FILTER_KEYS = {"pc_q": "", "pc_cat": [], "pc_status": []}


def _apply(new, warnings):
    ss.update(inputs=new, inputs_dirty=True, inputs_ver=ss["inputs_ver"] + 1,
              flash=["Stock plan updated."] + warnings)


def _clear_filters():
    for k, v in FILTER_KEYS.items():
        ss[k] = v
        ss[f"_keep_{k}"] = v


mode = ui.choice("View", ["Catalogue", "Edit table", "Stock & counts"], "prod_view", "Catalogue", keep=True)


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
    if s.button("Save", type="primary", width="stretch"):
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
    if c.button("Cancel", width="stretch"):
        st.rerun()


def catalogue():
    ui.require_plan(ctx)
    anim = ui.first_view("page:catalogue")
    inv = planning.inventory_table(ctx).set_index("product")
    plan = ctx["plan"].set_index("product")
    rows = ctx["rows"].set_index("product")
    df = pd.DataFrame({"product": plan.index, "name": plan["name"].to_numpy()})
    df = df.assign(status=df["product"].map(inv["status"]), cover_days=df["product"].map(inv["cover_days"]),
                   value_rm=df["product"].map(inv["value_rm"]), stock=df["product"].map(inv["stock"]),
                   sold7=df["product"].map(rows["demand_last7"]), action=df["product"].map(plan["action"]),
                   must=df["product"].map(plan["must_have"]),
                   expiry=df["product"].map(lambda p: bool(rows.at[p, "dead_flag"] and rows.at[p, "perishable"])))
    keep = ui.filter_bar("pc", ctx)
    a, b, c = st.columns([3, 1.4, 0.8], vertical_alignment="center")
    with a:
        flt = st.pills("Status", STATUS_FILTERS, selection_mode="multi", label_visibility="collapsed",
                       **ui.sticky("pc_status", [])) or []
    sort = b.selectbox("Sort by", list(SORTS), label_visibility="collapsed", **ui.sticky("pc_sort", "Most urgent"))
    c.button("Clear", key="pc_clear", width="stretch", help="Clear search, categories and status filters",
             on_click=_clear_filters)
    view = keep(df)
    rules = {"Low or out": view["status"].isin(["Low", "Out of stock"]), "Excess": view["status"] == "Excess",
             "Expiry risk": view["expiry"].astype(bool), "Must-have": view["must"].astype(bool),
             "Buy more": view["action"] == "RESTOCK"}
    for f in flt:
        if f in rules:
            view = view[rules[f].reindex(view.index, fill_value=False)]
    if SORTS.get(sort):
        col, asc = SORTS[sort]
        view = view.sort_values(col, ascending=asc, na_position="last")
    else:
        view = (view.assign(_r=view["status"].map(planning.STOCK_RANK)).sort_values(["_r", "cover_days"])
                .drop(columns="_r"))
    st.caption(f"{len(view)} of {len(df)} products · bar = days of stock, line = when a delivery ordered today arrives.")
    if view.empty:
        st.markdown(ui.empty("🔍", "No product matches", "Clear the filters to see every product."),
                    unsafe_allow_html=True)
        return
    chips = {"Out of stock": ("Out of stock", "lr-s-urgent", "⚠"), "Low": ("Low", "lr-s-urgent", "⚠"),
             "Excess": ("Excess", "lr-s-excess", "▣"), "OK": ("OK", "lr-s-ok", "✓")}
    keys = []
    for start in range(0, len(view), 3):
        for col, r in zip(st.columns(3), list(view.iloc[start:start + 3].itertuples())):
            key = f"card_pc_{ui.safe_key(r.product)}"
            keys.append(key)
            icon, name = ui.split_name(r.name)
            lead = int(rows.at[r.product, "lead_time"])
            horizon = max(lead * 2, 7)
            finite = np.isfinite(r.cover_days)
            lasts = f"{r.cover_days:.1f} days" if finite else "no sales expected"
            tone = "risk" if r.status in ("Low", "Out of stock") else "warn" if r.status == "Excess" else ""
            with col.container(border=True, key=key):
                st.markdown(
                    f'<div class="lr-pc"><div class="lr-avatar" aria-hidden="true">{escape(icon)}</div><div style="flex:1">'
                    f'<span class="lr-name">{escape(name)}</span><div class="meta">'
                    f'{escape(ui.category_of(r.product, ctx["inputs"]))}</div><div>{ui.chip(*chips[r.status])}'
                    f'{ui.action_chip(r.action)}{ui.must_chip(r.must)}'
                    f'{ui.chip("Expiry risk", "lr-s-expiry", "⌛") if r.expiry else ""}</div></div></div>'
                    + ui.product_spark(ctx, r.product, 300, 40)
                    + ui.meter((r.cover_days if finite else horizon) / horizon,
                               f"Stock lasts {lasts}; delivery takes {lead} days", tone, marker=lead / horizon,
                               anim=anim, legend=(f"Lasts {lasts}", f"delivery in {lead} d"))
                    + f'<div class="figs">Stock <b>{r.stock:,.0f}</b> · sold <b>{r.sold7:,.0f}</b> last week · order '
                      f'<b>{plan.at[r.product, "order_qty"]:,.0f}</b></div>', unsafe_allow_html=True)
                x, y = st.columns(2)
                with x:
                    ui.why_button(r.product, HERE, key=f"pc_why_{r.product}", label="Details")
                if y.button("Edit", key=f"pc_edit_{r.product}", width="stretch",
                            help="Edit the product or adjust its stock"):
                    edit_dialog(r.product)
    ui.enter(keys, anim)


def table():
    top = st.columns([3, 1.4], vertical_alignment="center")
    top[0].markdown('<span class="lr-muted">Edit any cell. Add a product with the <b>+</b> button at the top right '
                    "of the table, or select rows and press the bin to delete. Fully empty rows are ignored.</span>",
                    unsafe_allow_html=True)
    go = top[1].button("Update the plan", type="primary", icon=":material/auto_awesome:", width="stretch")
    edited = st.data_editor(
        planning.to_view(ss["inputs"]), key=f"products_{ss['inputs_ver']}", num_rows="dynamic", hide_index=True,
        width="stretch", column_config={
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
            st.error("Please fix these before updating the plan:\n\n" + "\n".join(f"- {e}" for e in errors))
            for w in warnings:
                st.warning(w)
        else:
            _apply(new, warnings)
            ui.open_tool("I")
            st.rerun()
    st.caption("New products have no sales history, so their forecast is a simple baseline from 'Sold last 7 days', "
               "not a trained-model prediction.")


if mode == "Catalogue":
    catalogue()
elif mode == "Edit table":
    table()
else:
    ui.require_plan(ctx)
    inventory.render(ctx)
