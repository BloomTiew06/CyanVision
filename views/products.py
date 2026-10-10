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
mode = "Table"

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
