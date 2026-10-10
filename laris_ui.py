"""LARIS look and feel: theme CSS plus small shared components, so every page looks and behaves the same.
Business numbers never come from here; they come from the shared context (laris_core) and planning.py."""
from html import escape

import altair as alt
import pandas as pd
import streamlit as st

import planning

GREEN, DARK, LIME, CREAM, CHARCOAL, MUTED, MIST = "#174D3A", "#10382B", "#C7ED72", "#F7F5EE", "#252923", \
    "#777D75", "#E7ECE5"
Z90 = 1.645
ACTIONS = ("RESTOCK", "REDUCE", "STOP", "MAINTAIN")

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap');
html, body, .stApp, .stMarkdown, button, input, label {font-family: 'Manrope', sans-serif;}
[data-testid="stIconMaterial"], [data-testid="stIconMaterial"] * {font-family: 'Material Symbols Rounded' !important;}
.block-container {padding-top: 4.2rem; max-width: 1180px;}
header[data-testid="stHeader"] {background: #FFFFFF; border-bottom: 1px solid #E2E6DF;}
.stButton > button[kind="primary"], .stLinkButton a[kind="primary"], .stDownloadButton > button[kind="primary"],
.stFormSubmitButton > button[kind="primary"] {background: #174D3A; color: #FFFFFF; font-weight: 700; border: none;}
.stButton > button[kind="primary"]:hover, .stLinkButton a[kind="primary"]:hover {background: #10382B; color: #FFFFFF;}
/* top bar */
.lr-shopline {font-size: 14px; color: #252923; line-height: 1.35;}
.lr-shopline b {font-size: 15px;}
.lr-shopline span {color: #777D75;}
/* headings and text */
.lr-eyebrow {font-family: 'JetBrains Mono', monospace; color: #174D3A; font-size: 12px; font-weight: 700;
             letter-spacing: 0.06em; margin-bottom: 2px;}
[data-testid="stMarkdownContainer"] p.lr-title {font-size: 30px; line-height: 1.15; font-weight: 800; color: #174D3A;
                                                letter-spacing: -0.025em; margin: 0;}
.lr-sub {font-size: 15px; color: #5B6158; margin: 2px 0 10px;}
.lr-section {font-size: 18px; font-weight: 800; color: #252923; margin: 18px 0 2px; padding-top: 12px;
             border-top: 1px solid #E2E6DF;}
.lr-help {font-size: 13px; color: #5B6158; margin: 0 0 8px;}
.lr-muted {color: #5B6158; font-size: 13px;}
.lr-impact {font-size: 13px; font-weight: 700; color: #174D3A;}
.lr-big {font-size: 28px; font-weight: 800; color: #174D3A; line-height: 1.1;}
.lr-big small {font-size: 15px; font-weight: 600; color: #5B6158;}
/* chips: always text, never colour alone */
.lr-chip {display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 800;
          letter-spacing: 0.04em; margin: 0 6px 2px 0; white-space: nowrap; text-transform: uppercase;}
.lr-a-restock {background: #174D3A; color: #FFFFFF;}
.lr-a-reduce {background: #E7ECE5; color: #174D3A;}
.lr-a-stop {background: #F1F0EA; color: #4F544C; border: 1px solid #C9CCC4;}
.lr-a-maintain {background: #FFFFFF; color: #5B6158; border: 1px solid #D5D9D1;}
.lr-s-urgent {background: #FBE4DF; color: #A3341F;}
.lr-s-warning {background: #FCEBCF; color: #7A4A00;}
.lr-s-monitor, .lr-s-info {background: #EEF0EC; color: #4A5048;}
.lr-s-ok {background: #E3F1E5; color: #1F6B3A;}
.lr-must {background: #FFFFFF; color: #174D3A; border: 1px solid #174D3A;}
/* provenance labels */
.lr-label {display: inline-block; font-family: 'JetBrains Mono', monospace; font-size: 10.5px; font-weight: 700;
           padding: 1px 7px; border-radius: 4px; margin-right: 6px; vertical-align: 1px;}
.lr-measured {background: #E3F1E5; color: #1F6B3A;}
.lr-estimated {background: #EEF0EC; color: #4A5048;}
.lr-simulated {background: #FCEBCF; color: #7A4A00;}
.lr-placeholder {background: #F1F0EA; color: #5B6158;}
.lr-planned {background: #FFFFFF; color: #777D75; border: 1px dashed #B5BAB1;}
/* insights */
.lr-insight {padding: 10px 14px; border-left: 4px solid #C9CCC4; background: #FFFFFF; margin-bottom: 6px;
             border-radius: 0 6px 6px 0; font-size: 14.5px;}
.lr-insight.urgent {border-left-color: #A3341F;}
.lr-insight.warning {border-left-color: #C98A1B;}
.lr-insight.info {border-left-color: #174D3A;}
/* product rows: one compact row each, separated by hairlines */
[class*="st-key-row_"] {border-bottom: 1px solid #E2E6DF; padding: 6px 0 8px;}
.lr-name {font-weight: 800; font-size: 15px; color: #252923;}
.lr-qty {font-size: 15px; font-weight: 800; color: #252923;}
.lr-qty span {font-weight: 500; color: #5B6158; font-size: 13px;}
.lr-kpi .k {font-family: 'JetBrains Mono', monospace; font-size: 11px; font-weight: 700; color: #5B6158;}
.lr-kpi .v {font-size: 24px; font-weight: 800; color: #174D3A; line-height: 1.25;}
.lr-kpi .s {font-size: 12px; color: #5B6158;}
.lr-card {background: #FFFFFF; border: 1px solid #E2E6DF; border-radius: 8px; padding: 12px 14px; height: 100%;}
.lr-tagbox {display: inline-block; font-family: 'JetBrains Mono', monospace; font-size: 10.5px; padding: 1px 6px;
            border-radius: 4px; margin-right: 6px; border: 1px solid #C9D1C6; color: #5B6158; background: #F7F5EE;
            min-width: 84px; text-align: center;}
.lr-why h4 {font-size: 14px; margin: 12px 0 2px; color: #174D3A;}
.lr-why p {margin: 0 0 4px;}
@media (max-width: 640px) {
  .block-container {padding-left: 1rem; padding-right: 1rem;}
  [data-testid="stMarkdownContainer"] p.lr-title {font-size: 24px;}
}
</style>
"""


def money(x, dp=0):
    return "RM –" if x is None or pd.isna(x) else f"RM {x:,.{dp}f}"


def chip(text, cls):
    return f'<span class="lr-chip {cls}">{escape(str(text))}</span>'


def action_chip(action):
    return chip(planning.ACTION_LABEL[action], f"lr-a-{action.lower()}")


def status_chip(level):
    return chip(level, f"lr-s-{level.lower()}")


def must_chip(must):
    return chip("Must-have", "lr-must") if must else ""


def label(text, kind):
    """Provenance badge: measured / estimated / simulated / placeholder / planned."""
    return f'<span class="lr-label lr-{kind}">{escape(text)}</span>'


def kpi(k, v, s="", tone=None):
    color = {"bad": "#A3341F", "warn": "#7A4A00", "good": "#1F6B3A"}.get(tone, "#5B6158")
    return (f'<div class="lr-card lr-kpi"><div class="k">{escape(k)}</div><div class="v">{escape(v)}</div>'
            f'<div class="s" style="color:{color}">{escape(s)}</div></div>')


def page_header(eyebrow, title, subtitle):
    top = f'<div class="lr-eyebrow">{escape(eyebrow)}</div>' if eyebrow else ""
    return f'{top}<p class="lr-title">{escape(title)}</p><p class="lr-sub">{escape(subtitle)}</p>'


def section(title, helptext=None):
    st.markdown(f'<div class="lr-section">{escape(title)}</div>'
                + (f'<p class="lr-help">{escape(helptext)}</p>' if helptext else ""), unsafe_allow_html=True)


def evidence(pairs):
    return "<br>".join(f'<span class="lr-tagbox">{escape(t)}</span>{escape(x)}' for t, x in pairs)


def require_plan(ctx):
    """Every planning page needs at least one product."""
    if ctx["empty"]:
        st.info("You have no products yet. Add them in My Products, then generate a stock plan.")
        st.page_link("views/products.py", label="Go to My Products", icon=":material/inventory_2:")
        st.stop()


# ---------------- navigation and order helpers (callbacks; app.py performs page switches) ----------------
def _open(product, back):
    st.session_state.update(sel=product, back_to=back, goto="views/product.py")


def why_button(product, back, key, label="Why?"):
    st.button(label, key=key, on_click=_open, args=(product, back), use_container_width=True)


def goto(path):
    st.session_state["goto"] = path


def set_qty_value(product, qty):
    """Owner's quantity override for the shared order; the recommendation itself is kept."""
    st.session_state.setdefault("order_adj", {})[product] = float(qty)


def set_qty_from(product, key):
    set_qty_value(product, st.session_state[key])


def clear_qty(product):
    st.session_state.setdefault("order_adj", {}).pop(product, None)


# ---------------- forecast chart (Look Ahead, Product Intelligence) ----------------
def range_note(ctx):
    cov = ctx["metrics"].get("band_coverage_90")
    note = ("Shaded band: approximate range (forecast ± 1.645 × the model's typical daily error on validation weeks), "
            "not a guaranteed interval.")
    if cov is not None:
        note += f" On held-out test weeks, {cov:.0%} of actual days fell inside a band built this way."
    return note


def forecast_chart(ctx, product, height=260):
    r, week = ctx["rows"].set_index("product").loc[product], ctx["week"]
    daily = planning.daily_forecast(ctx, product)
    if r["ratio"] > 0:
        sub = week["sub"]
        h = sub[(sub["product"] == product) & (sub["date"] >= week["as_of"] - pd.Timedelta(days=28))
                & (sub["date"] < week["as_of"])]
        hist = pd.DataFrame({"date": h["date"], "units": h["y"] * ctx["scale"] * r["ratio"], "series": "Recorded sales"})
    else:
        hist = pd.DataFrame({"date": pd.Series(dtype="datetime64[ns]"), "units": pd.Series(dtype=float),
                             "series": pd.Series(dtype=str)})
    fut = pd.DataFrame({"date": pd.date_range(week["as_of"], week["end"]), "units": daily, "series": "Forecast"})
    fut["lo"], fut["hi"] = (fut["units"] - Z90 * r["sigma"]).clip(lower=0), fut["units"] + Z90 * r["sigma"]
    color = alt.Color("series:N", scale=alt.Scale(domain=["Recorded sales", "Forecast"], range=[MUTED, GREEN]),
                      legend=alt.Legend(orient="top", title=None))
    x = alt.X("date:T", title=None, axis=alt.Axis(format="%d %b"))
    chart = (alt.Chart(fut).mark_area(opacity=0.18, color=GREEN).encode(x=x, y="lo:Q", y2="hi:Q")
             + alt.Chart(pd.concat([hist, fut[["date", "units", "series"]]])).mark_line(point=True).encode(
                 x=x, y=alt.Y("units:Q", title="Units per day"), color=color,
                 tooltip=[alt.Tooltip("date:T", format="%a %d %b"), alt.Tooltip("units:Q", format=",.1f"), "series"]))
    note = (range_note(ctx) if r["ratio"] > 0 else
            "No recorded sales history for this product: the forecast is a flat baseline at last week's sales, "
            "not a trained-model prediction, so treat it as rough.")
    return chart.properties(height=height), note
