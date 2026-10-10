import altair as alt
import pandas as pd
import streamlit as st

import laris_ui as ui

ctx = st.session_state["ctx"]
metrics, frontier, imp, per = ctx["metrics"], ctx["frontier"], ctx["imp"], ctx["per"]
s = metrics["splits"]

t1, t2, t3, t4, t5 = st.tabs(["Forecast accuracy", "Alert quality", "Robustness", "Decision quality",
                              "Assumptions and limits"])
with t1:
    st.markdown(ui.label("MEASURED", "measured") + f" Held-out test period {s['test'][0]} to {s['test'][1]}; the model "
                "never saw these dates. WAPE = total absolute error ÷ total sales (lower is better).",
                unsafe_allow_html=True)
    acc = pd.DataFrame([{"Method": m, "Daily WAPE": v["WMAPE"],
                         "7-day total WAPE": metrics["test_weekly_totals"][m]["WMAPE"],
                         "Daily MAE": v["MAE"], "Bias": v["bias"]}
                        for m, v in metrics["test_daily"].items()])
    best = acc.loc[acc["7-day total WAPE"].idxmin(), "Method"]
    model_row = acc[acc["Method"].str.startswith("Model")]
    c = st.columns(3)
    if len(model_row):
        m7 = float(model_row["7-day total WAPE"].iloc[0])
        base7 = acc[~acc["Method"].str.startswith("Model")]["7-day total WAPE"].min()
        c[0].markdown(ui.kpi("Forecast accuracy, 7-day totals", f"{1 - m7:.0%}", "1 − WAPE, test period"),
                      unsafe_allow_html=True)
        c[1].markdown(ui.kpi("Best simple rule", f"{1 - base7:.0%}", "same measure, same days",
                             "good" if m7 < base7 else "bad"), unsafe_allow_html=True)
    if "band_coverage_90" in metrics:
        c[2].markdown(ui.kpi("Actual sales inside the 90% range", f"{metrics['band_coverage_90']:.0%}",
                             "about 90% = honest range"), unsafe_allow_html=True)
    st.dataframe(acc.style.format({"Daily WAPE": "{:.1%}", "7-day total WAPE": "{:.1%}", "Daily MAE": "{:,.1f}",
                                   "Bias": "{:+.1%}"}), hide_index=True, use_container_width=True)
    if not best.startswith("Model"):
        st.warning(f"On 7-day totals, '{best}' beat the model on this test period.")
    ci = {k: v for k, v in metrics.get("model_vs_baselines_7day_ci", {}).items() if k != "label"}
    if ci:
        st.markdown("**Is the difference real?** Model minus each simple rule, 7-day totals, with a 95% "
                    "confidence interval from resampling products and stores (negative = the model is better).")
        st.dataframe(pd.DataFrame([{"Compared with": k, "WAPE difference": v["diff"], "95% CI low": v["ci95"][0],
                                    "95% CI high": v["ci95"][1],
                                    "Verdict": "model better" if v["ci95"][1] < 0 else
                                    ("rule better" if v["ci95"][0] > 0 else "no clear difference")}
                                   for k, v in ci.items()]).style.format(
            {"WAPE difference": "{:+.1%}", "95% CI low": "{:+.1%}", "95% CI high": "{:+.1%}"}),
            hide_index=True, use_container_width=True)
    if "test_by_volume_tier" in metrics:
        st.markdown("**Where does the model help?** Daily WAPE by sales volume (series split into thirds).")
        st.dataframe(pd.DataFrame(metrics["test_by_volume_tier"]).T.style.format("{:.1%}"), use_container_width=True)
    cov = metrics.get("lead_time_interval_coverage")
    if cov:
        st.markdown("**Is the uncertainty honest?** Share of actual sales totals that fell inside the forecast's "
                    "range on the test period (closer to the target level is better).")
        rows_cov = []
        for key, val in cov["conformal"].items():
            L, lv = key[1:].split("_")
            rows_cov.append({"Days ahead (total)": int(L), "Target": int(lv) / 100, "Validation-error range": val,
                             "Normal σ√L range": cov["normal"][key]})
        st.dataframe(pd.DataFrame(rows_cov).style.format({"Target": "{:.0%}", "Validation-error range": "{:.1%}",
                                                          "Normal σ√L range": "{:.1%}"}),
                     hide_index=True, use_container_width=True)
    a, b = st.columns(2)
    a.markdown("**Accuracy by product (test WAPE)**")
    a.dataframe(per.set_index("product").drop(columns="test_units").style.format("{:.1%}"), use_container_width=True)
    b.markdown("**What the AI relies on (permutation importance)**")
    b.altair_chart(alt.Chart(imp.head(10)).mark_bar(color=ui.GREEN).encode(
        x=alt.X("importance:Q", title="increase in error when shuffled"), y=alt.Y("feature:N", sort="-x", title=None)),
        use_container_width=True)
with t2:
    st.markdown(ui.label("MEASURED on real sales, SIMULATED stock levels", "measured"), unsafe_allow_html=True)
    ab = metrics.get("alert_backtest")
    if ab:
        res = pd.DataFrame(ab["test"]).T
        match = next((k for k in res.index if "same recall" in k), None)
        rule = next((k for k in res.index if k.startswith("Min-stock")), None)
        if match and rule:
            m, r = res.loc[match], res.loc[rule]
            st.markdown(
                f"**False alarms.** With its alert level set on earlier weeks to catch as many stockouts as a "
                f"typical min-stock rule, LARIS caught **{m['recall']:.0%}** of the stockouts (rule: {r['recall']:.0%}) "
                f"and raised a false alarm in **{m['false_alarm_rate']:.0%}** of the cases with no stockout "
                f"(rule: {r['false_alarm_rate']:.0%}). Precision {m['precision']:.0%} vs {r['precision']:.0%}.")
        st.dataframe(res[["precision", "recall", "false_alarm_rate", "alerts", "false_alarms", "missed"]].style.format(
            {"precision": "{:.0%}", "recall": "{:.0%}", "false_alarm_rate": "{:.1%}", "alerts": "{:,.0f}",
             "false_alarms": "{:,.0f}", "missed": "{:,.0f}"}), use_container_width=True)
        a2, b2 = st.columns(2)
        with a2:
            st.markdown("**Ranking quality (Prioritize).** Share of the real lost margin found in the top 20% of "
                        "cases, ranked by each method.")
            st.dataframe(pd.Series(ab["test_rm_loss_captured_top20pct"], name="RM loss captured").to_frame()
                         .style.format("{:.0%}"), use_container_width=True)
            st.caption(f"PR-AUC (higher is better): " + ", ".join(f"{k} {v:.2f}" for k, v in ab["test_pr_auc"].items()))
        with b2:
            st.markdown(f"**Are the probabilities honest?** Predicted vs actual stockout rate on the test period "
                        f"({ab['uncertainty_model']} uncertainty, chosen on validation; Brier {ab['test_brier']:.3f}).")
            rel = pd.DataFrame(ab["reliability"])
            st.altair_chart(
                alt.Chart(rel).mark_line(point=True, color=ui.GREEN).encode(
                    x=alt.X("predicted:Q", title="predicted chance of stockout", scale=alt.Scale(domain=[0, 1])),
                    y=alt.Y("observed:Q", title="actual share that ran out", scale=alt.Scale(domain=[0, 1])),
                    tooltip=["predicted", "observed", "cases"])
                + alt.Chart(pd.DataFrame({"x": [0, 1], "y": [0, 1]})).mark_line(strokeDash=[4, 4], color="#9AA59F")
                .encode(x="x:Q", y="y:Q"), use_container_width=True)
        st.caption(ab["label"] + ". " + " ".join(ab["notes"]))
    else:
        st.info("Not run yet. Rerun pipeline.py to backtest the alerts (precision, recall and false-alarm rate "
                "vs a min-stock rule).")
with t3:
    st.markdown(ui.label("MEASURED", "measured"), unsafe_allow_html=True)
    us = metrics.get("unseen_stores")
    if us:
        st.markdown(f"**Shops the AI has never seen.** A second model was trained without stores "
                    f"{', '.join(us['stores'])} ({us['n_series']} product series) and scored on their test period. "
                    "This is the closest test we have of how LARIS would do in a new shop.")
        st.dataframe(pd.DataFrame({"Daily WAPE": us["daily_wape"], "7-day total WAPE": us["weekly_wape"]})
                     .style.format("{:.1%}"), use_container_width=True)
        ci = us.get("unseen_model_vs_baselines_7day_ci", {})
        if ci:
            st.dataframe(pd.DataFrame([{"Unseen-store model vs": k, "WAPE difference": v["diff"],
                                        "95% CI": f"{v['ci95'][0]:+.1%} to {v['ci95'][1]:+.1%}",
                                        "Verdict": "model better" if v["ci95"][1] < 0 else
                                        ("rule better" if v["ci95"][0] > 0 else "no clear difference")}
                                       for k, v in ci.items()]).style.format({"WAPE difference": "{:+.1%}"}),
                         hide_index=True, use_container_width=True)
    else:
        st.info("Unseen-store test not run yet (pipeline.py --holdout-stores).")
    st.info("Noisy-data test not run yet.")
    dq = metrics.get("data_quality")
    if dq:
        st.markdown(f"**Data quality:** {dq['suspect_zero_days']:,} suspect zero-sales days in "
                    f"{dq['series_with_suspect_zeros']} series were excluded from training and evaluation "
                    f"({dq['rule']}).")
with t4:
    sim = metrics["simulation"]
    st.markdown(ui.label("SIMULATED", "simulated") + " **Ordering from the AI forecast vs a moving-average rule** "
                f"(no cash limit; lead time {sim['lead_time_days']} days, ordering every {sim['review_days']} days).",
                unsafe_allow_html=True)
    h = sim.get("headline_matched_fill_rate")
    if h:
        chg = h["stock_change_pct"]
        st.markdown(f"To reach the same **{h['matched_fill_rate']:.1%} fill rate**, ordering from the AI forecast held "
                    f"**{h['model_days_of_cover']:.2f} days** of stock vs **{h['baseline_days_of_cover']:.2f}** for "
                    f"the moving-average rule ({abs(chg):.0%} {'less' if chg < 0 else 'more'}).")
    fr = frontier.assign(policy=frontier["policy"].map({"model": "AI forecast (LARIS)",
                                                        "baseline": "28-day average + safety stock"}))
    st.altair_chart(alt.Chart(fr).mark_line(point=True).encode(
        x=alt.X("days_of_cover:Q", title="average stock held (days of demand)", scale=alt.Scale(zero=False)),
        y=alt.Y("fill_rate:Q", title="share of demand served", axis=alt.Axis(format="%"), scale=alt.Scale(zero=False)),
        color=alt.Color("policy:N", title=None,
                        scale=alt.Scale(domain=["AI forecast (LARIS)", "28-day average + safety stock"],
                                        range=[ui.GREEN, "#9AA59F"]),
                        legend=alt.Legend(orient="bottom")),
        tooltip=["policy", "z", "fill_rate", "days_of_cover"]), use_container_width=True)
    st.caption("Each point is one service-level setting. Up and to the left is better: more demand served with less stock.")
    st.markdown("**Assumptions**\n" + "\n".join(f"- {x}" for x in sim["assumptions"]))
    bs = metrics.get("budget_simulation")
    st.divider()
    st.markdown(ui.label("SIMULATED", "simulated") + " **Same cash, different decisions.** "
                + (f"Replay of the test period ({bs['period'][0]} to {bs['period'][1]}) for stores "
                   f"{', '.join(bs['stores'])}, real sales as demand." if bs else ""), unsafe_allow_html=True)
    if bs:
        pct = st.segmented_control("Cash available (share of the ideal order)", list(bs["totals_by_budget"]),
                                   default="75%" if "75%" in bs["totals_by_budget"] else None, key="sim_pct")
        pct = pct or list(bs["totals_by_budget"])[0]
        tb = pd.DataFrame(bs["totals_by_budget"][pct]).T
        tb = tb.assign(family=["LARIS" if i.startswith("LARIS") else "Usual practice" if i.startswith("Usual")
                               else "Partial LARIS" for i in tb.index])
        st.altair_chart(alt.Chart(tb.reset_index(names="policy")).mark_bar().encode(
            x=alt.X("lost_margin_plus_waste_rm:Q", title="lost margin + expiry waste (RM, all stores)"),
            y=alt.Y("policy:N", sort="x", title=None, axis=alt.Axis(labelLimit=320)),
            color=alt.Color("family:N", title=None, scale=alt.Scale(domain=["LARIS", "Partial LARIS", "Usual practice"],
                                                                     range=[ui.GREEN, "#7FB89A", "#B9C2BD"])),
            tooltip=["policy", alt.Tooltip("lost_margin_rm:Q", format=",.0f"), alt.Tooltip("waste_rm:Q", format=",.0f"),
                     alt.Tooltip("must_have_short_units:Q", format=",.0f"), alt.Tooltip("fill_rate:Q", format=".1%")])
            .properties(height=260), use_container_width=True)
        st.dataframe(tb[["lost_margin_rm", "waste_rm", "must_have_short_units", "fill_rate", "stockout_days",
                         "spent_rm", "ending_stock_rm"]].style.format(
            {"lost_margin_rm": "{:,.0f}", "waste_rm": "{:,.0f}", "must_have_short_units": "{:,.0f}",
             "fill_rate": "{:.1%}", "stockout_days": "{:,.0f}", "spent_rm": "{:,.0f}", "ending_stock_rm": "{:,.0f}"}),
            use_container_width=True)
        wins = bs["laris_win_rate_by_store"].get(pct, {})
        if wins:
            st.markdown("**Stores where LARIS had lower lost margin + waste:** "
                        + "; ".join(f"{k}: {v:.0%}" for k, v in wins.items()))
        st.markdown("**Does it hold if the placeholder settings are wrong?** (75% cash)")
        sens = pd.DataFrame([{"Scenario": k, "LARIS lowest vs every usual rule": "yes" if v["laris_lowest_vs_usual"]
                              else "no", **{f"wins vs {u.replace('Usual: ', '')}": w
                                            for u, w in v["win_rate_vs_usual"].items()}}
                             for k, v in bs["sensitivity_75pct"].items()])
        st.dataframe(sens.style.format({c: "{:.0%}" for c in sens.columns if c.startswith("wins")}),
                     hide_index=True, use_container_width=True)
        if not bs["conclusion_holds_in_all_scenarios"]:
            failed = [k for k, v in bs["sensitivity_75pct"].items() if not v["laris_lowest_vs_usual"]]
            st.warning("The advantage does not hold in every scenario: " + ", ".join(failed) + ".")
        st.markdown("**Assumptions**\n" + "\n".join(f"- {x}" for x in bs["assumptions"]))
    else:
        st.info("Budget replay not run yet (pipeline.py, or pipeline.py --sim-only on existing outputs).")
with t5:
    st.markdown(f"""
- **Training and test data:** {metrics['data_source']}. Not Malaysian. Results show the method works on real
  retail data; they are not a claim about any Malaysian shop.
- **Splits:** train to {s['train_end']}, validation {s['val'][0]} to {s['val'][1]} (used only for the error
  spread), test {s['test'][0]} to {s['test'][1]}.
- **Leakage control:** every feature uses sales from 7+ days earlier, plus calendar, holidays and planned promotions.
- **Not in the data:** stock levels, stockouts, prices, supplier lead times, shelf lives. These come from your inputs
  (PLACEHOLDER defaults); historical sales stand in for demand and may be lower than true demand where shelves ran empty.
- **Not yet demonstrable:** performance on Malaysian shops, real savings, and whether owners find the advice clear.
  These need a pilot.
""")
