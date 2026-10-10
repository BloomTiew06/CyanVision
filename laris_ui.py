"""LARIS look and feel: one design system (tokens from the original LARIS Dashboard HTML) plus small shared
components, so every page looks and behaves the same. Business numbers never come from here; they come from the
shared context (laris_core) and planning.py.

Tokens: cream #F7F5EE page, white surfaces with #E2E6DF borders and 8px corners, forest #174D3A / deep #10382B
for brand and the hero panel, lime #C7ED72 for the primary action and active state, charcoal #252923 text,
muted #626860 secondary text, Manrope for text and JetBrains Mono for small uppercase eyebrows.
"""
from html import escape

import altair as alt
import pandas as pd
import streamlit as st

import planning

GREEN, DARK, LIME, CREAM, CHARCOAL, MUTED, MIST, RISK = ("#174D3A", "#10382B", "#C7ED72", "#F7F5EE", "#252923",
                                                       "#626860", "#E7ECE5", "#A04A2A")
Z90 = 1.645
ACTIONS = ("RESTOCK", "REDUCE", "STOP", "MAINTAIN")

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap');
html, body, .stApp, .stMarkdown, button, input, textarea, label, [data-testid="stWidgetLabel"] p
  {font-family: 'Manrope', sans-serif;}
[data-testid="stIconMaterial"], [data-testid="stIconMaterial"] * {font-family: 'Material Symbols Rounded' !important;}
.stApp {background: #F7F5EE; color: #252923;}
.block-container {padding-top: 5.2rem; padding-bottom: 3rem; max-width: 1180px;}

/* header = the original sidebar: deep green, cream text, active item on forest */
header[data-testid="stHeader"] {background: #10382B; border-bottom: none; height: 3.75rem;}
[data-testid="stTopNavLink"], [data-testid="stTopNavSection"] {border-radius: 6px;}
[data-testid="stTopNavLink"] *, [data-testid="stTopNavSection"] * {color: #B7C8BD !important;}
[data-testid="stTopNavLink"]:hover, [data-testid="stTopNavSection"]:hover {background: #174D3A;}
[data-testid="stTopNavLink"][aria-current="page"] {background: #174D3A;}
[data-testid="stTopNavLink"][aria-current="page"] * {color: #F7F5EE !important; font-weight: 700;}
[data-testid="stToolbarActions"] *, [data-testid="stMainMenu"] *, [data-testid="stAppDeployButton"] button,
[data-testid="stBaseButton-header"] {color: #F7F5EE !important;}

/* buttons: lime primary with deep text; quiet white secondary that firms up on hover */
.stButton > button, .stLinkButton a, .stDownloadButton > button, .stFormSubmitButton > button, [data-testid="stPopover"] button
  {border-radius: 6px; font-weight: 700; border: 1px solid #C9D1C6; background: #FFFFFF; color: #174D3A;
   transition: border-color .12s, background .12s;}
.stButton > button:hover, .stLinkButton a:hover, [data-testid="stPopover"] button:hover
  {border-color: #174D3A; color: #174D3A; background: #FFFFFF;}
.stButton > button[kind="primary"], .stLinkButton a[kind="primary"], .stFormSubmitButton > button[kind="primary"],
.stDownloadButton > button[kind="primary"] {background: #C7ED72; color: #10382B; border: none; font-weight: 800;}
.stButton > button[kind="primary"]:hover, .stLinkButton a[kind="primary"]:hover,
.stFormSubmitButton > button[kind="primary"]:hover {background: #B8E25A; color: #10382B;}

/* surfaces */
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) {border-radius: 8px;}
div[data-testid="stExpander"] details {background: #FFFFFF; border: 1px solid #E2E6DF; border-radius: 8px;}
div[data-testid="stExpander"] summary p {font-weight: 700; color: #174D3A;}
[data-testid="stDataFrame"], [data-testid="stDataEditor"] {border: 1px solid #E2E6DF; border-radius: 8px;}
[data-baseweb="input"], [data-baseweb="select"] > div, [data-baseweb="textarea"] {border-radius: 6px;}

/* type */
.lr-eyebrow {font-family: 'JetBrains Mono', monospace; color: #174D3A; font-size: 12px; font-weight: 700;
             letter-spacing: 0.06em; margin-bottom: 2px; text-transform: uppercase;}
[data-testid="stMarkdownContainer"] p.lr-title {font-size: 30px; line-height: 1.15; font-weight: 800; color: #174D3A;
                                                letter-spacing: -0.025em; margin: 0;}
.lr-sub {font-size: 14px; color: #626860; margin: 4px 0 12px;}
.lr-section {font-size: 16px; font-weight: 800; color: #174D3A; margin: 22px 0 2px;}
.lr-help {font-size: 13px; color: #626860; margin: 0 0 8px;}
.lr-muted {color: #626860; font-size: 13px;}
.lr-impact {font-size: 13px; font-weight: 700; color: #174D3A;}
.lr-big {font-size: 28px; font-weight: 800; color: #174D3A; line-height: 1.1;}
.lr-big small {font-size: 14px; font-weight: 600; color: #626860;}
.lr-shopline {font-size: 13px; color: #252923; line-height: 1.4;}
.lr-shopline b {font-size: 14px;}
.lr-shopline span {color: #626860;}

/* chips: always carry text, never colour alone */
.lr-chip {display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 800;
          letter-spacing: 0.03em; margin: 0 6px 2px 0; white-space: nowrap; text-transform: uppercase;}
.lr-a-restock {background: #C7ED72; color: #10382B;}
.lr-a-reduce {background: #E7ECE5; color: #174D3A;}
.lr-a-stop {background: #F1F0EA; color: #626860;}
.lr-a-maintain {background: #FFFFFF; color: #626860; border: 1px dashed #9AA397;}
.lr-s-urgent {background: #F6E3DA; color: #A04A2A;}
.lr-s-warning {background: #FCEBCF; color: #7A4A00;}
.lr-s-monitor, .lr-s-info {background: #EEF1EC; color: #4A5048;}
.lr-s-ok {background: #E7ECE5; color: #174D3A;}
.lr-must {background: #FFFFFF; color: #174D3A; border: 1px solid #174D3A;}
.lr-label {display: inline-block; font-family: 'JetBrains Mono', monospace; font-size: 10.5px; font-weight: 700;
           padding: 1px 7px; border-radius: 4px; margin-right: 6px; vertical-align: 1px;}
.lr-measured {background: #E7ECE5; color: #174D3A;}
.lr-estimated {background: #EEF1EC; color: #4A5048;}
.lr-simulated {background: #FCEBCF; color: #7A4A00;}
.lr-placeholder {background: #F1F0EA; color: #626860;}
.lr-planned {background: #FFFFFF; color: #626860; border: 1px dashed #9AA397;}

/* hero panel: the original 'Ikut bajet' card, deep green with lime accents, slightly floating */
.lr-hero {background: #174D3A; color: #F7F5EE; border-radius: 10px; padding: 24px 28px;
          box-shadow: 0 10px 28px rgba(16, 56, 43, .18); margin: 6px 0 18px;}
.lr-hero .eyebrow {font-family: 'JetBrains Mono', monospace; font-size: 12px; font-weight: 700; color: #C7ED72;
                   letter-spacing: 0.06em;}
.lr-hero .top {display: flex; flex-wrap: wrap; justify-content: space-between; gap: 12px; align-items: flex-start;}
.lr-hero .lead {font-size: 15px; color: #B7C8BD; margin-top: 4px;}
.lr-hero .big {font-size: 40px; font-weight: 800; letter-spacing: -0.03em; line-height: 1.05; text-align: right;}
.lr-hero .big small {display: block; font-size: 12px; font-weight: 500; color: #B7C8BD; letter-spacing: 0;}
.lr-hero .bar {position: relative; height: 12px; background: #10382B; border-radius: 4px; overflow: hidden; margin: 16px 0 6px;}
.lr-hero .bar i {position: absolute; top: 0; bottom: 0; left: 0; background: #C7ED72;}
.lr-hero .bar b {position: absolute; top: 0; bottom: 0; width: 2px; background: #F7F5EE;}
.lr-hero .legend {font-size: 12px; color: #B7C8BD;}
.lr-hero .stats {display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); border-top: 1px solid #3B6E5B;
                 margin-top: 16px;}
.lr-hero .stats > div {padding: 14px 16px 0; border-left: 1px solid #3B6E5B;}
.lr-hero .stats > div:first-child {border-left: none; padding-left: 0;}
.lr-hero .stats span {display: block; font-size: 12px; color: #B7C8BD;}
.lr-hero .stats b {display: block; font-size: 22px; font-weight: 800; line-height: 1.2;}
.lr-hero .stats em {display: block; font-style: normal; font-size: 12px; color: #B7C8BD;}
.lr-hero .stats b.lime {color: #C7ED72;}
.lr-hero .stats b.risk {color: #F4B79B;}

/* letter strip: five tiles; lime when active */
[class*="st-key-letter_"] button {height: 74px; flex-direction: column; background: #FFFFFF; border: 1px solid #E2E6DF;
                                  color: #626860; font-weight: 600;}
[class*="st-key-letter_"] button p {font-size: 12px; line-height: 1.25; margin: 0;}
[class*="st-key-letter_"] button strong {display: block; font-size: 26px; font-weight: 800; color: #174D3A;
                                         letter-spacing: -0.02em; line-height: 1.1;}
[class*="st-key-letter_"] button:hover {border-color: #174D3A; background: #F3F6F1;}
[class*="st-key-letter_"] button[kind="primary"] {background: #C7ED72; border-color: #C7ED72; color: #10382B;}
[class*="st-key-letter_"] button[kind="primary"] strong {color: #10382B;}

/* rows, kpis, cards */
[class*="st-key-row_"] {border-top: 1px solid #EEF1EC; padding: 8px 4px 8px; transition: background .12s;}
[class*="st-key-row_"]:hover {background: #F3F6F1;}
.lr-name {font-weight: 700; font-size: 14.5px; color: #252923;}
.lr-qty {font-family: 'JetBrains Mono', monospace; font-size: 14px; font-weight: 700; color: #252923;}
.lr-qty span {font-family: 'Manrope', sans-serif; font-weight: 500; color: #626860; font-size: 12.5px;}
.lr-card {background: #FFFFFF; border: 1px solid #E2E6DF; border-radius: 8px; padding: 14px 16px; height: 100%;}
.lr-kpi .k {font-family: 'JetBrains Mono', monospace; font-size: 11px; font-weight: 700; color: #626860;
            text-transform: uppercase;}
.lr-kpi .v {font-size: 24px; font-weight: 800; color: #174D3A; line-height: 1.25;}
.lr-kpi .s {font-size: 12px; color: #626860;}
.lr-insight {padding: 10px 14px; border-left: 3px solid #C9D1C6; background: #FFFFFF; margin-bottom: 6px;
             border-radius: 0 6px 6px 0; font-size: 14px;}
.lr-insight.urgent {border-left-color: #A04A2A;}
.lr-insight.warning {border-left-color: #C98A1B;}
.lr-insight.info {border-left-color: #174D3A;}
.lr-tagbox {display: inline-block; font-family: 'JetBrains Mono', monospace; font-size: 10.5px; padding: 1px 6px;
            border-radius: 4px; margin-right: 6px; border: 1px solid #C9D1C6; color: #626860; background: #F7F5EE;
            min-width: 84px; text-align: center;}
.lr-why {background: #F7F5EE; border-radius: 6px; padding: 14px 16px; line-height: 1.55;}
.lr-why h4 {font-family: 'JetBrains Mono', monospace; font-size: 11px; letter-spacing: .06em; margin: 12px 0 2px;
            color: #174D3A; text-transform: uppercase;}
.lr-why h4:first-child {margin-top: 0;}
.lr-why p {margin: 0 0 4px;}

/* chat */
[data-testid="stChatMessage"] {background: transparent; padding: 6px 0;}
[data-testid="stChatInput"] textarea {font-size: 14px;}
@media (max-width: 640px) {
  .block-container {padding-left: 1rem; padding-right: 1rem;}
  [data-testid="stMarkdownContainer"] p.lr-title {font-size: 24px;}
  .lr-hero .big {font-size: 30px; text-align: left;}
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
    return chip(level, f"lr-s-{level.lower().replace(' ', '-')}")


def must_chip(must):
    return chip("Must-have", "lr-must") if must else ""


def label(text, kind):
    """Provenance badge: measured / estimated / simulated / placeholder / planned."""
    return f'<span class="lr-label lr-{kind}">{escape(text)}</span>'


def kpi(k, v, s="", tone=None):
    color = {"bad": RISK, "warn": "#7A4A00", "good": GREEN}.get(tone, MUTED)
    return (f'<div class="lr-card lr-kpi"><div class="k">{escape(k)}</div><div class="v">{escape(v)}</div>'
            f'<div class="s" style="color:{color}">{escape(s)}</div></div>')


def page_header(eyebrow, title, subtitle):
    top = f'<div class="lr-eyebrow">{escape(eyebrow)}</div>' if eyebrow else ""
    sub = f'<p class="lr-sub">{escape(subtitle)}</p>' if subtitle else ""
    return f'{top}<p class="lr-title">{escape(title)}</p>{sub}'


def section(title, helptext=None):
    st.markdown(f'<div class="lr-section">{escape(title)}</div>'
                + (f'<p class="lr-help">{escape(helptext)}</p>' if helptext else ""), unsafe_allow_html=True)


def evidence(pairs):
    return "<br>".join(f'<span class="lr-tagbox">{escape(t)}</span>{escape(x)}' for t, x in pairs)


def require_plan(ctx):
    """Every planning page needs at least one product."""
    if ctx["empty"]:
        st.info("You have no products yet. Add them in Products, then LARIS can plan your order.")
        st.page_link("views/products.py", label="Go to Products", icon=":material/inventory_2:")
        st.stop()


# ---------------- state that survives page and tool switches ----------------
def sticky(key, default=None):
    """Widget kwargs whose value survives the widget being off-screen (Streamlit drops widget state when a widget
    isn't drawn, e.g. after switching LARIS tools). Usage: st.text_input("Search", **ui.sticky("lu_q", ""))."""
    ss, keep = st.session_state, f"_keep_{key}"
    if key not in ss:
        ss[key] = ss.get(keep, default)
    return {"key": key, "on_change": lambda: ss.__setitem__(keep, ss[key])}


def bind(widget_key, state_key, on_change=None):
    """Widget kwargs for a widget that edits a plain session value (state_key) shared across pages."""
    ss = st.session_state
    ss[widget_key] = ss.get(state_key)

    def _sync():
        ss[state_key] = ss[widget_key]
        if on_change:
            on_change()
    return {"key": widget_key, "on_change": _sync}


# ---------------- navigation and order helpers (callbacks; app.py performs page switches) ----------------
def _open(product, back):
    st.session_state.update(sel=product, back_to=back, goto="views/product.py")


def why_button(product, back, key, label="Why?"):
    st.button(label, key=key, on_click=_open, args=(product, back), use_container_width=True)


def goto(path):
    st.session_state["goto"] = path


def open_tool(letter):
    """Jump to a LARIS tool from anywhere (Home insights, assistant links)."""
    st.session_state.update(tool=letter, goto="views/laris.py")


def tool_button(letter, label, key):
    st.button(label, key=key, on_click=open_tool, args=(letter,), use_container_width=True)


def set_qty_value(product, qty):
    """Owner's quantity override for the shared order; the recommendation itself is kept."""
    st.session_state.setdefault("order_adj", {})[product] = float(qty)


def set_qty_from(product, key):
    set_qty_value(product, st.session_state[key])


def clear_qty(product):
    st.session_state.setdefault("order_adj", {}).pop(product, None)


# ---------------- hero panel ----------------
def hero(eyebrow, lead, big, big_note, fill=None, marker=None, legend="", stats=()):
    """The deep-green panel. fill/marker: 0..1 positions on the bar (e.g. order vs budget). stats: (label, value,
    note, tone) with tone in {None, 'lime', 'risk'}. All text is escaped."""
    bar = ""
    if fill is not None:
        bar = (f'<div class="bar"><i style="width:{max(0, min(1, fill)) * 100:.1f}%"></i>'
               + (f'<b style="left:calc({max(0, min(1, marker)) * 100:.1f}% - 1px)"></b>' if marker is not None else "")
               + f'</div><div class="legend">{escape(legend)}</div>')
    cells = "".join(f'<div><span>{escape(k)}</span><b class="{tone or ""}">{escape(v)}</b><em>{escape(n)}</em></div>'
                    for k, v, n, tone in stats)
    return (f'<div class="lr-hero"><div class="top"><div><div class="eyebrow">{escape(eyebrow)}</div>'
            f'<div class="lead">{escape(lead)}</div></div><div class="big">{escape(big)}<small>{escape(big_note)}'
            f'</small></div></div>{bar}<div class="stats">{cells}</div></div>')


# ---------------- forecast chart (Look Up, Product detail) ----------------
def range_note(ctx):
    cov = ctx["metrics"].get("band_coverage_90")
    note = ("Shaded band: approximate range (forecast ± 1.645 × the model's typical daily error on validation weeks), "
            "not a guaranteed interval.")
    if cov is not None:
        note += f" On held-out test weeks, {cov:.0%} of actual days fell inside a band built this way."
    return note


def forecast_chart(ctx, product, height=260):
    r, week = ctx["rows"].set_index("product").loc[product], ctx["week"]
    source = r["forecast_source"]
    daily = planning.daily_forecast(ctx, product)
    if source == "model":
        sub = week["sub"]
        h = sub[(sub["product"] == product) & (sub["date"] >= week["as_of"] - pd.Timedelta(days=28))
                & (sub["date"] < week["as_of"])]
        hist = pd.DataFrame({"date": h["date"], "units": h["y"] * ctx["scale"] * r["ratio"], "series": "Recorded sales"})
    else:
        hist = pd.DataFrame({"date": pd.Series(dtype="datetime64[ns]"), "units": pd.Series(dtype=float),
                             "series": pd.Series(dtype=str)})
    fut = pd.DataFrame({"date": pd.date_range(week["as_of"], week["end"]), "units": daily, "series": "Forecast"})
    fut["lo"], fut["hi"] = (fut["units"] - Z90 * r["sigma"]).clip(lower=0), fut["units"] + Z90 * r["sigma"]
    color = alt.Color("series:N", scale=alt.Scale(domain=["Recorded sales", "Forecast"], range=["#9AA397", GREEN]),
                      legend=alt.Legend(orient="top", title=None))
    x = alt.X("date:T", title=None, axis=alt.Axis(format="%d %b", grid=False))
    layers = [alt.Chart(pd.concat([hist, fut[["date", "units", "series"]]])).mark_line(point=True).encode(
        x=x, y=alt.Y("units:Q", title="Units per day"), color=color,
        tooltip=[alt.Tooltip("date:T", format="%a %d %b"), alt.Tooltip("units:Q", format=",.1f"), "series"])]
    if source != "unavailable":
        layers.insert(0, alt.Chart(fut).mark_area(opacity=0.16, color=GREEN).encode(x=x, y="lo:Q", y2="hi:Q"))
    note = {"model": range_note(ctx),
            "baseline": "No model forecast for this product: the forecast repeats last week's sales, so treat it as rough.",
            "unavailable": "Forecast unavailable: no sales history and nothing recorded as sold last week."}[source]
    return alt.layer(*layers).properties(height=height).configure_view(strokeWidth=0), note
