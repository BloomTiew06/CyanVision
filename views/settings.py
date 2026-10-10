import streamlit as st

import laris_core as core
import laris_ui as ui

ss = st.session_state


def _sync(dst, src):
    ss[dst] = ss[src]


def _load_pitch_scenario():
    ctx = ss["ctx"]
    store, day, rise = core.demo_week(ctx["fc"], ctx["settings"])
    if day is not None:
        ss["store"], ss["as_of"], ss["preset"] = store, day, "Tight budget"
        ss["pitch_note"] = (f"Store {store} (median sales volume), week of {day:%d %b %Y}: the AI predicted the largest "
                            f"rise in must-have demand of any Wednesday in the test period ({rise:+.0%} vs the week "
                            "before). Stock levels and budget come from the 'Tight budget' demo scenario.")


def _apply_edits():
    edits = ss["inputs_editor"].get("edited_rows", {})
    df = ss["inputs"].copy()
    for i, changes in edits.items():
        for col, val in changes.items():
            df.iat[int(i), df.columns.get_loc(col)] = val
    ss["inputs"] = df


a, b = st.columns(2)
with a:
    with st.container(border=True):
        st.markdown("**Your shop** " + ui.label("ILLUSTRATIVE", "placeholder"), unsafe_allow_html=True)
        st.text_input("Shop name", value=ss["shop_name"], key="shop_name_w", on_change=_sync,
                      args=("shop_name", "shop_name_w"))
        st.text_input("Location", value=ss["shop_place"], key="shop_place_w", on_change=_sync,
                      args=("shop_place", "shop_place_w"))
        st.text_input("Owner", value=ss["owner"], key="owner_w", on_change=_sync, args=("owner", "owner_w"))
with b:
    with st.container(border=True):
        st.markdown("**Demo and model settings**", unsafe_allow_html=True)
        st.button("Load the pitch scenario (tight-budget Wednesday)", on_click=_load_pitch_scenario,
                  help="Picks the store and week by a fixed rule, not by hand: the median-volume store and the "
                       "Wednesday with the largest predicted rise in must-have demand.")
        if ss.get("pitch_note"):
            st.caption(ss["pitch_note"])
        st.selectbox("Demo scenario (sets stock levels and budget)", list(core.PRESETS),
                     index=list(core.PRESETS).index(ss["preset"]), key="preset_w", on_change=_sync,
                     args=("preset", "preset_w"))
        st.number_input("Shop size (× Favorita store volume) · PLACEHOLDER", min_value=0.001, max_value=1.0,
                        value=float(ss["scale"]), step=0.01, format="%.3f", key="scale_w", on_change=_sync,
                        args=("scale", "scale_w"),
                        help="Scales forecasts and ranges to a smaller shop, for illustration. 1.0 = data scale.")
        st.select_slider("Service level for 'needs this order'", options=[0.90, 0.95, 0.98, 0.99],
                         value=ss["service"], key="service_w", on_change=_sync, args=("service", "service_w"),
                         format_func=lambda v: f"{v:.0%}")

st.markdown("**Stock and product settings** " + ui.label("PLACEHOLDER defaults: enter your own", "placeholder"),
            unsafe_allow_html=True)
st.data_editor(ss["inputs"], key="inputs_editor", on_change=_apply_edits, hide_index=True,
               use_container_width=True, disabled=["product", "Name"],
               column_config={"product": None,
                              "Must-have": st.column_config.CheckboxColumn("Must-have"),
                              "Unit cost (RM)": st.column_config.NumberColumn(format="%.2f"),
                              "Margin (RM)": st.column_config.NumberColumn(format="%.2f")})
st.caption("Stock levels start as a demo mix (days of forecast cover, set by the demo scenario). Costs, margins, "
           "shelf lives, lead times and pack sizes come from product_settings.csv and are placeholders.")
