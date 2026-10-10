"""Proof: does LARIS work? The evaluation pipeline.py measured on held-out weeks (and the budget backtest),
shown as plain verdicts with the evidence underneath. Every number is read from metrics.json via
planning.proof_summary; nothing is recomputed or tuned here."""
from html import escape

import altair as alt
import pandas as pd
import streamlit as st

import laris_ui as ui
import planning

ctx = st.session_state["ctx"]
s = planning.proof_summary(ctx["metrics"])
GATE_CHIP = {"PASS": ("Pass", "lr-s-ok", "✓"), "FAIL": ("Fails", "lr-s-urgent", "✕"), "NOT RUN": ("Not run", "lr-s-info", "–")}
pct = lambda x: "–" if x is None else f"{x:.1%}"

st.markdown(ui.label("MEASURED", "measured") + '<span class="lr-muted">Every number below comes from weeks the model '
            "had not seen while training.</span>", unsafe_allow_html=True)

# ---------------- verdicts ----------------
ui.section("The four checks", "Fixed before seeing any results (LARIS_OVERVIEW.md). If one fails, we say so.")
cols = st.columns(4)
for col, g in zip(cols, ["G1", "G2", "G3", "G4"]):
    text, cls, ic = GATE_CHIP[s["gates"].get(g, "NOT RUN")]
    extra = ""
    if g == "G4" and s.get("sensitivity_failures"):
        extra = f"<div class='s bad'>Breaks when: {escape(', '.join(s['sensitivity_failures']))}</div>"
    col.markdown(f'<div class="lr-card lr-kpi"><div class="k">{g}</div><div style="margin:4px 0">{ui.chip(text, cls, ic)}'
                 f'</div><div class="s">{escape(planning.GATE_TEXT[g])}</div>{extra}</div>', unsafe_allow_html=True)

# ---------------- 1. forecast accuracy ----------------
ui.section("1. Is the AI forecast better than simple rules?",
           "Error of 7-day totals per store and product on held-out weeks (WAPE: lower is better).")
acc = pd.DataFrame(s["accuracy"])
if acc.empty:
    st.markdown(ui.empty("–", "Not measured yet", "Run pipeline.py to evaluate the forecast."), unsafe_allow_html=True)
else:
    a, b = st.columns([1.2, 1])
    acc["label"] = acc["method"].str.replace(" (gradient boosting)", "", regex=False)
    acc["who"] = acc["model"].map({True: "LARIS AI model", False: "Simple rule"})
    bars = alt.Chart(acc).mark_bar(cornerRadiusEnd=3).encode(
        x=alt.X("wape:Q", title="7-day error (WAPE)", axis=alt.Axis(format="%")),
        y=alt.Y("label:N", sort="x", title=None, axis=alt.Axis(labelLimit=240)),
        color=alt.Color("who:N", scale=alt.Scale(domain=["LARIS AI model", "Simple rule"], range=[ui.GREEN, "#B9C4BC"]),
                        legend=alt.Legend(orient="top", title=None)),
        tooltip=["method", alt.Tooltip("wape:Q", format=".1%", title="WAPE"), alt.Tooltip("mae:Q", format=",.1f", title="MAE")])
    text = alt.Chart(acc).mark_text(align="left", dx=4, fontSize=12, color=ui.CHARCOAL).encode(
        x="wape:Q", y=alt.Y("label:N", sort="x"), text=alt.Text("wape:Q", format=".1%"))
    a.altair_chart((bars + text).properties(height=190).configure_view(strokeWidth=0), width="stretch")
    with b:
        br = s.get("best_rule")
        if br:
            model = acc.loc[acc["model"], "wape"].iloc[0] if acc["model"].any() else None
            st.markdown(ui.kpi("AI model error", pct(model), f"vs {pct(br['wape'])} for the best simple rule "
                                                             f"({br['name'].lower()})",
                               "good" if s["gates"]["G1"] == "PASS" else "bad"), unsafe_allow_html=True)
            lo, hi = br["ci95"]
            st.caption(f"Difference {br['diff'] * 100:+.1f} points (95% CI {lo * 100:+.1f} to {hi * 100:+.1f}); "
                       f"clearly better than {s.get('beats_rules', 0)} of {s.get('n_rules', 0)} simple rules. Negative = "
                       "the AI model has less error.")
    un = s.get("unseen")
    if un and un.get("weekly_wape"):
        w = un["weekly_wape"]
        k = next((x for x in w if "never seen" in x), None)
        rules = {x: v for x, v in w.items() if x.startswith(("Seasonal", "28-day", "Same weekday"))}
        if k and rules:
            best = min(rules, key=rules.get)
            st.markdown(ui.label("MEASURED", "measured") + f'<span class="lr-muted">On {len(un.get("stores", []))} store(s) '
                        f"the model never saw in training: {pct(w[k])} error vs {pct(rules[best])} for the best simple "
                        "rule.</span>", unsafe_allow_html=True)

# ---------------- 2. honest range ----------------
ui.section("2. Is the forecast range honest?",
           "A 90% range should contain about 90% of what actually sold. Too few means it's overconfident.")
cov = s["coverage"]["by_horizon"]
k = st.columns(3)
for col, L in zip(k, (1, 3, 7)):
    v = cov.get(L)
    tone = None if v is None else "good" if 0.85 <= v <= 0.95 else "bad"
    col.markdown(ui.kpi(f"{L}-day total", pct(v), "inside the 90% range (target 85–95%)", tone), unsafe_allow_html=True)

# ---------------- 3. alerts ----------------
ui.section("3. Do the stockout alerts catch problems without crying wolf?",
           "Actual future sales tested against a range of stock levels (the sales history has no stock records).")
al = pd.DataFrame(s["alerts"]["rows"])
if al.empty:
    st.markdown(ui.empty("–", "Alert backtest not run"), unsafe_allow_html=True)
else:
    a, b = st.columns([1.3, 1])
    show = al.assign(method=al["method"].str.replace(r" \(.*\)", "", regex=True))
    a.dataframe(show[["method", "recall", "precision", "false_alarm_rate"]], hide_index=True, width="stretch",
                column_config={"method": st.column_config.TextColumn("Method", width="medium"),
                               "recall": st.column_config.ProgressColumn("Stockouts caught", format="%.0f%%",
                                                                         min_value=0, max_value=1),
                               "precision": st.column_config.NumberColumn("Alerts that were right", format="%.2f"),
                               "false_alarm_rate": st.column_config.NumberColumn("False-alarm rate", format="%.2f")})
    rel = pd.DataFrame(s["alerts"]["reliability"])
    if len(rel):
        line = pd.DataFrame({"p": [0, 1]})
        chart = (alt.Chart(line).mark_line(strokeDash=[4, 4], color="#9AA397").encode(x="p:Q", y="p:Q")
                 + alt.Chart(rel).mark_line(point=True, color=ui.GREEN).encode(
                     x=alt.X("predicted:Q", title="Predicted chance of running out", axis=alt.Axis(format="%")),
                     y=alt.Y("observed:Q", title="How often it happened", axis=alt.Axis(format="%")),
                     tooltip=[alt.Tooltip("predicted:Q", format=".0%"), alt.Tooltip("observed:Q", format=".0%"), "cases"]))
        b.altair_chart(chart.properties(height=220, title="Are the probabilities honest? (on the line = yes)")
                       .configure_view(strokeWidth=0), width="stretch")
    st.markdown(ui.label("MEASURED", "measured") + '<span class="lr-muted">Thresholds were chosen on earlier weeks, then '
                "tested on later ones.</span>", unsafe_allow_html=True)

# ---------------- 4. decisions ----------------
ui.section("4. Does ordering with LARIS lose less money?",
           "Same cash, same suppliers, real past sales: lost profit plus waste, lower is better.")
tot = s["replay"]["totals"]
if not tot:
    st.markdown(ui.empty("–", "Backtest not available"), unsafe_allow_html=True)
else:
    rows = [{"budget": f"{b} of the cash needed", "policy": p, "loss": v["lost_margin_plus_waste_rm"],
             "short": v.get("must_have_short_units")} for b, ps in tot.items() for p, v in ps.items()
            if p.startswith(("LARIS", "Usual"))]
    df = pd.DataFrame(rows)
    df["who"] = df["policy"].map(lambda p: "LARIS" if p.startswith("LARIS") else "Usual way of ordering")
    df["policy"] = df["policy"].str.replace("LARIS (AI forecast + optimiser)", "LARIS", regex=False) \
        .str.replace("Usual: ", "", regex=False)
    chart = alt.Chart(df).mark_bar(cornerRadiusEnd=3).encode(
        y=alt.Y("policy:N", title=None, sort=alt.EncodingSortField("loss"), axis=alt.Axis(labelLimit=220)),
        x=alt.X("loss:Q", title="Lost profit + waste (RM, all tested stores)"),
        color=alt.Color("who:N", scale=alt.Scale(domain=["LARIS", "Usual way of ordering"], range=[ui.GREEN, "#C9D1C6"]),
                        legend=alt.Legend(orient="top", title=None)),
        row=alt.Row("budget:N", title=None, header=alt.Header(labelAngle=0, labelAlign="left", labelFontWeight="bold")),
        tooltip=["policy", alt.Tooltip("loss:Q", format=",.0f"), alt.Tooltip("short:Q", format=",.0f",
                                                                             title="Must-have units short")])
    st.altair_chart(chart.properties(height=110).configure_view(strokeWidth=0), width="stretch")
    st.markdown(ui.label("BACKTEST", "simulated") + '<span class="lr-muted">Real past sales, played back day by day with '
                "the same cash and suppliers for every method. "
                f"Stores tested: {', '.join(map(str, s['replay']['stores']))}. Uses your cost and margin settings; an "
                "estimate from past data, not measured savings.</span>", unsafe_allow_html=True)
    with st.expander("Assumptions behind the backtest"):
        for x in s["replay"]["assumptions"]:
            x = x.replace("are PLACEHOLDER settings", "come from the shop's settings").replace("reference replay",
                                                                                             "reference run")
            st.markdown(f"- {x}")

ui.section("About the model")
a, b = st.columns(2, gap="medium")
a.markdown("""
**How it forecasts.** A gradient-boosting model predicts each product's daily sales for the next 7 days from recent
sales, day of week, payday, public holidays and planned promotions. Every input uses sales at least 7 days old, so each
forecast could have been made in advance.

**How it was tested.** Trained on earlier weeks, tuned on the next six, and scored only on the final nine weeks, compared
with three simple rules (same day last week, 28-day average, same weekday average).
""")
b.markdown("""
**Training data.** Corporación Favorita grocery sales (Kaggle *Store Sales*, 2013–2017, daily sales by store and product
family). Shop-specific forecasts improve after retraining on the shop's own POS history.

**Limits.** Sales stand in for demand, so past stockouts hide some demand. Alert tests use a range of stock levels because
the sales history has no stock records. RM figures use your cost and margin settings.
""")
