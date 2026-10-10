"""I · Inventory: current stock, what's low or out, what's excess, stock value, and explicit stock counts."""
import numpy as np
import pandas as pd
import streamlit as st

import laris_ui as ui
import planning
import store

REASONS = ["Stock count", "Damaged or expired", "Delivery received", "Correction", "Other"]


def render(ctx):
    inv = planning.inventory_table(ctx)
    counts = inv["status"].value_counts()
    out_n, low_n, ex_n = counts.get("Out of stock", 0), counts.get("Low", 0), counts.get("Excess", 0)
    missing = int(inv["value_rm"].isna().sum())
    ui.kpi_row(ui.kpi("Out of stock", f"{out_n}", "products", "bad" if out_n else None),
               ui.kpi("Low", f"{low_n}", "may run out before a delivery", "bad" if low_n else None),
               ui.kpi("Excess", f"{ex_n}", "more than sells in time", "warn" if ex_n else None),
               ui.kpi("Stock value at cost", ui.money(inv["value_rm"].sum(skipna=True)),
                      f"{missing} product(s) without a cost price" if missing else "at your cost prices"))

    show_status = st.segmented_control("Show", ["All", "Out of stock", "Low", "Excess", "OK"],
                                       label_visibility="collapsed", **ui.sticky("in_filter", "All")) or "All"
    cat = ui.category_filter(ctx, "in_cat")
    t = ui.in_category(inv if show_status == "All" else inv[inv["status"] == show_status], cat)
    if t.empty:
        st.info("No products match these filters.")
    else:
        st.caption("Click a product for its details.")
        ui.product_table(t.assign(lasts=t["cover_days"].map(lambda c: f"{c:.1f} days" if np.isfinite(c) else "–")),
                         "in_table", "views/laris.py",
                         column_order=["name", "group", "status", "stock", "daily", "lasts", "reorder_point", "max_level",
                                       "value_rm"],
                         column_config={"name": st.column_config.TextColumn("Product", width="medium"),
                                        "group": "Category", "status": "Status",
                                        "stock": st.column_config.NumberColumn("Stock", format="%d"),
                                        "daily": st.column_config.NumberColumn("Sells a day", format="%.1f"),
                                        "lasts": "Lasts",
                                        "reorder_point": st.column_config.NumberColumn("Reorder at", format="%d"),
                                        "max_level": st.column_config.NumberColumn("Order up to", format="%d"),
                                        "value_rm": st.column_config.NumberColumn("Value at cost (RM)", format="%.0f")})
    st.caption(f"Reorder at = expected sales during the delivery time + safety stock for a {ctx['service']:.0%} chance "
               "of not running out. Order up to = expected sales until the following delivery (capped by shelf life) "
               "+ the same safety stock. Value is blank where there's no cost price.")
    _adjust(ctx)


def _save_count(product, name, before, after, reason, note):
    ss = st.session_state
    inp = ss["inputs"].copy()
    mask = inp["product"] == product
    if mask.sum() != 1:
        ss["in_msg"] = ("error", "That product is no longer in your list; nothing was changed.")
        return
    inp.loc[mask, "On hand"] = float(after)
    ss["inputs"], ss["inputs_dirty"] = inp, True
    log = store.get("stock_log", [])
    log.append({"at": store.now(), "product": product, "name": name, "before": before, "after": after,
                "reason": reason, "note": note})
    store.put("stock_log", log[-200:])
    ss["in_msg"] = ("ok", f"Saved: {name} stock is now {after:,.0f} (was {before:,.0f}). The plan has been updated.")
    ss["in_confirm"] = False


def _adjust(ctx):
    ss = st.session_state
    ui.section("Record a stock count", "Set the stock you actually have. LARIS saves it only after you confirm.")
    rows = ctx["rows"].set_index("product")
    names = dict(zip(rows.index, rows["name"]))
    a, b, c = st.columns([2.2, 1, 1.4])
    p = a.selectbox("Product", list(names), format_func=names.get, **ui.sticky("in_prod", list(names)[0]))
    if p not in names:
        p = list(names)[0]
    before = float(rows.at[p, "on_hand"])
    after = b.number_input("Stock now (units)", min_value=0.0, step=1.0, format="%.0f", value=before,
                           key=f"in_count_{p}")
    reason = c.selectbox("Reason", REASONS, key="in_reason")
    note = st.text_input("Note (optional)", key="in_note")
    diff = after - before
    ok = after == int(after) and after >= 0
    if not ok:
        st.error("Stock must be a whole number of 0 or more.")
    st.markdown(f"**{names[p]}**: {before:,.0f} → **{after:,.0f}** ({diff:+,.0f} units).")
    st.checkbox("I've checked this count", key="in_confirm")
    st.button("Save stock count", type="primary", disabled=not (ok and ss.get("in_confirm") and diff != 0),
              on_click=_save_count, args=(p, names[p], before, after, reason, note))
    msg = ss.pop("in_msg", None)
    if msg:
        (st.success if msg[0] == "ok" else st.error)(msg[1])
    log = store.get("stock_log", [])
    if log:
        with st.expander(f"Recent stock changes ({len(log)})"):
            st.dataframe(pd.DataFrame(log[::-1][:20])[["at", "name", "before", "after", "reason", "note"]],
                         hide_index=True, use_container_width=True)
