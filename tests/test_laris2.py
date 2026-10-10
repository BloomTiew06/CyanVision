"""LARIS 2.0: shared-context logic behind every page, plus cross-page behaviour in the running app."""
import json
from pathlib import Path
from urllib.parse import unquote

import numpy as np
import pandas as pd
import pytest

import laris_core as core
import planning
import store
from inventory import load_settings

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs_mock"
pytestmark = pytest.mark.skipif(not (OUT / "metrics.json").exists(),
                                reason="run make_mock_data.py and pipeline.py --out outputs_mock first")


@pytest.fixture(scope="module")
def data():
    fc = pd.read_parquet(OUT / "forecasts.parquet")
    fc["date"], fc["store"] = pd.to_datetime(fc["date"]), fc["store"].astype(str)
    sig = pd.read_csv(OUT / "sigma.csv", dtype={"store": str}).set_index("sid")
    unc = pd.read_csv(OUT / "uncertainty.csv")
    metrics = json.loads((OUT / "metrics.json").read_text())
    test = fc[fc["split"] == "test"]
    days = sorted(d for d in test["date"].unique() if d + pd.Timedelta(days=6) <= test["date"].max())
    store_id, as_of = sorted(fc["store"].unique())[0], pd.Timestamp(days[len(days) // 2])
    settings = load_settings(ROOT / "product_settings.csv")
    inputs, _ = core.default_inputs(core.week_view(fc, store_id, as_of), settings, sig, store_id)
    return dict(fc=fc, sig=sig, unc=unc, metrics=metrics, store=store_id, as_of=as_of, settings=settings,
                inputs=inputs)


def make_ctx(d, inputs=None, budget=None, adjust=None, protect=True):
    ctx = core.build_context(d["fc"], d["sig"], d["settings"], d["store"], d["as_of"],
                             d["inputs"] if inputs is None else inputs, budget, unc=d["unc"],
                             alert_cfg=d["metrics"]["alert_backtest"], protect_must_have=protect, adjust=adjust)
    return {**ctx, "metrics": d["metrics"], "ref": planning.order_ref(d["store"], d["as_of"]), "shop": "Kedai Maju"}


# ---------------- shared context ----------------
def test_sample_shop_shows_all_four_actions(data):
    assert set(make_ctx(data)["plan"]["action"]) == {"RESTOCK", "REDUCE", "STOP", "MAINTAIN"}


def test_budget_constrains_the_order_and_full_budget_covers_it(data):
    full = make_ctx(data)
    assert not full["budget_limited"] and abs(full["totals"]["spent_rm"] - full["ideal_rm"]) < 1e-6
    tight = make_ctx(data, budget=full["ideal_rm"] * 0.4)
    assert tight["budget_limited"] and tight["totals"]["spent_rm"] <= tight["budget_rm"] + 1e-6
    assert (tight["plan"]["qty"] <= tight["plan"]["ideal"]).all()


def test_negative_budget_is_treated_as_zero(data):
    ctx = make_ctx(data, budget=-100)
    assert ctx["budget_rm"] == 0 and ctx["totals"]["spent_rm"] == 0


def test_order_adjustment_changes_order_not_recommendation(data):
    base = make_ctx(data)
    p = base["plan"]["product"].iloc[0]
    ctx = make_ctx(data, adjust={p: 999})
    row = ctx["plan"].set_index("product").loc[p]
    assert row["order_qty"] == 999 and row["qty"] == base["plan"].set_index("product").loc[p, "qty"] and row["adjusted"]
    assert ctx["order_rm"] == pytest.approx(ctx["plan"]["order_rm"].sum())


def test_both_strategies_are_real_and_respect_the_budget(data):
    ctx = make_ctx(data, budget=make_ctx(data)["ideal_rm"] * 0.5)
    cmp = planning.strategy_compare(ctx)
    assert set(cmp) == {"essentials", "value"}
    assert all(v["spent"] <= ctx["budget_rm"] + 1e-6 for v in cmp.values())
    assert cmp["essentials"]["must_short"] <= cmp["value"]["must_short"] + 1e-6


def test_empty_product_list_does_not_crash(data):
    ctx = make_ctx(data, inputs=data["inputs"].iloc[0:0])
    assert ctx["empty"] and ctx["plan"].empty and ctx["order_rm"] == 0


def test_new_product_uses_baseline_and_is_flagged(data):
    new = {**data["inputs"].iloc[0].to_dict(), "product": "Kopi O", "Name": "Kopi O", "Sales last 7 days": 14}
    ctx = make_ctx(data, inputs=pd.concat([data["inputs"], pd.DataFrame([new])], ignore_index=True))
    r = ctx["rows"].set_index("product").loc["Kopi O"]
    assert r["ratio"] == 0 and r["low_confidence"] and r["demand_7d"] == pytest.approx(14)


def test_product_explanations_exist_for_every_product(data):
    ctx = make_ctx(data)
    assert ctx["plan"]["why"].str.len().gt(20).all() and ctx["plan"]["risk"].str.len().gt(10).all()
    assert all({t for t, _ in w} >= {"AI forecast", "Calculation", "Your setting"} for w in ctx["rows"]["why"])


# ---------------- page logic ----------------
def test_alerts_follow_the_plan(data):
    ctx = make_ctx(data)
    al = planning.alert_table(ctx)
    assert set(al["level"]) <= {"URGENT", "WARNING", "MONITOR"}
    assert set(al.loc[al["level"] == "URGENT", "product"]) == set(ctx["plan"].loc[ctx["plan"]["urgent"], "product"])
    ranks = list(al["level"].map(planning.LEVEL_RANK))
    assert ranks == sorted(ranks)


def test_look_ahead_options_are_ordered_and_recommended(data):
    la = planning.look_ahead_table(make_ctx(data))
    opts = la[la["options"].map(len) > 0]
    assert len(opts)
    for r in opts.itertuples():
        assert r.options["full"] >= r.options["part"] >= r.options["skip"] and r.recommended in r.options


def test_waste_skips_reorder_for_dead_stock(data):
    ctx = make_ctx(data)
    w = planning.waste_table(ctx).set_index("product")
    stop = ctx["plan"].loc[ctx["plan"]["action"] == "STOP", "product"]
    assert len(stop) and all(w.loc[p, "choice"] == "skip" for p in stop)


def test_insights_counts_match_the_data(data):
    ctx = make_ctx(data, budget=make_ctx(data)["ideal_rm"] * 0.5)
    found = planning.insights(ctx)
    urgent_must = ctx["plan"][ctx["plan"]["urgent"] & ctx["plan"]["must_have"]]
    if len(urgent_must):
        assert any(t.startswith(f"{len(urgent_must)} must-have") for _, t, _ in found)
    assert any("budget" in t for _, t, _ in found)


def test_reorder_levels_are_consistent(data):
    lv = planning.reorder_levels(make_ctx(data))
    assert (lv["reorder_point"] <= lv["max_level"] + 1).all() and (lv["reorder_point"] >= 0).all()


# ---------------- sales & profitability ----------------
def test_revenue_and_gross_profit_formulas(data):
    ctx = make_ctx(data)
    df, tot = planning.sales_summary(ctx, 28)
    rows = ctx["rows"].set_index("product")
    for r in df.itertuples():
        cost = rows.at[r.product, "unit_cost"]
        assert r.revenue == pytest.approx(r.units * (cost + rows.at[r.product, "margin"]))
        assert r.gross_profit == pytest.approx(r.revenue - r.units * cost)
    assert tot["gross_profit"] == pytest.approx(tot["revenue"] - tot["cogs"])


def test_seven_day_sales_match_the_products_table(data):
    df, _ = planning.sales_summary(make_ctx(data), 7)
    sold = data["inputs"].set_index("product")["Sales last 7 days"]
    assert np.allclose(df.set_index("product")["units"], sold.loc[df["product"]].to_numpy(), atol=1e-6)


def test_zero_revenue_and_missing_cost_are_not_ranked(data):
    inp = data["inputs"].copy()
    inp.loc[0, "Sales last 7 days"] = 0
    inp.loc[1, "Unit cost (RM)"] = 0
    df, tot = planning.sales_summary(make_ctx(data, inputs=inp), 7)
    by = df.set_index("product")
    assert np.isnan(by.loc[inp.loc[0, "product"], "margin_pct"])
    assert np.isnan(by.loc[inp.loc[1, "product"], "gross_profit"]) and tot["no_cost"] == 1


def test_new_product_has_no_long_history(data):
    new = {**data["inputs"].iloc[0].to_dict(), "product": "Kopi O", "Name": "Kopi O", "Sales last 7 days": 14}
    ctx = make_ctx(data, inputs=pd.concat([data["inputs"], pd.DataFrame([new])], ignore_index=True))
    df28, tot = planning.sales_summary(ctx, 28)
    assert not df28.set_index("product").loc["Kopi O", "has_history"] and tot["no_history"] == 1
    assert planning.sales_summary(ctx, 7)[0].set_index("product").loc["Kopi O", "units"] == 14


# ---------------- my products ----------------
def test_product_validation_reports_problems(data):
    bad = planning.to_view(data["inputs"]).astype({"Product": object})
    bad.loc[0, "Stock"] = -5
    bad.loc[1, "Product"] = None
    bad.loc[2, "Product"] = bad.loc[3, "Product"]
    bad.loc[4, "Delivery days"] = 0
    new, errors, _ = planning.validate_products(bad, data["inputs"], core.INPUT_COLUMNS)
    text = " ".join(errors)
    assert new is None
    assert "negative" in text and "name" in text and "more than once" in text and "at least 1 day" in text


def test_product_validation_accepts_adds_and_deletes(data):
    view = planning.to_view(data["inputs"]).iloc[1:]           # delete the first product
    blank = pd.DataFrame([{c: None for c in view.columns}])
    added = pd.DataFrame([{"product": None, "Product": "Kopi O", "Stock": 5, "Sold last 7 days": 14,
                           "Cost price (RM)": 3.0, "Selling price (RM)": 2.5, "Delivery days": 2,
                           "Shelf life (days)": 180, "Must-have": False}])
    new, errors, warnings = planning.validate_products(pd.concat([view, added, blank], ignore_index=True),
                                                       data["inputs"], core.INPUT_COLUMNS)
    assert not errors and len(new) == len(data["inputs"])
    assert "Kopi O" in set(new["product"]) and data["inputs"]["product"].iloc[0] not in set(new["product"])
    assert any("below cost" in w for w in warnings) and any("empty row" in w for w in warnings)


def test_lookup_search(data):
    ctx = make_ctx(data)
    name = ctx["plan"]["name"].iloc[0]
    assert name in set(planning.lookup_table(ctx, name[2:6].lower())["name"])


def test_forecast_column_is_filled_and_missing_is_explicit(data):
    """Regression: the screen's 'Forecast' column was blank because its header sat on a reliability note.
    Every model product must show its canonical 7-day forecast; a product with no forecast says so; a real
    forecast of 0 shows 0, not 'unavailable'."""
    inp = data["inputs"].copy()
    zero = inp.loc[0, "product"]
    inp.loc[0, "Sales last 7 days"] = 0                                      # model product, sold 0 -> forecast 0
    new = {**inp.iloc[1].to_dict(), "product": "Kopi O", "Name": "Kopi O", "Sales last 7 days": 0}
    ctx = make_ctx(data, inputs=pd.concat([inp, pd.DataFrame([new])], ignore_index=True))
    lt = planning.lookup_table(ctx).set_index("product")
    model = lt[lt["source"] == "AI model"]
    assert len(model) == len(inp) and model["forecast"].str.len().gt(0).all()
    assert lt.loc[zero, "forecast"] == "0" and lt.loc[zero, "source"] == "AI model"
    assert lt.loc["Kopi O", "forecast"] == "Forecast unavailable" and np.isnan(lt.loc["Kopi O", "forecast_7d"])
    plan = ctx["plan"].set_index("product")
    assert np.allclose(model["forecast_7d"], plan.loc[model.index, "forecast_7d"])


# ---------------- send & sync ----------------
def test_whatsapp_link_is_encoded_and_only_lists_ordered_items(data):
    ctx = make_ctx(data)
    plan = ctx["plan"].copy()
    plan.loc[0, "name"] = "Kopi & Teh #1"
    msg = planning.order_message(plan, "Kedai Maju", data["as_of"], ctx["ref"])
    url = planning.whatsapp_url(msg, "+60 12-345 6789")
    assert url.startswith("https://wa.me/60123456789?text=")
    text = url.split("text=", 1)[1]
    assert "&" not in text and "#" not in text and "\n" not in text and unquote(text) == msg
    assert all(n in msg for n in plan.loc[plan["order_qty"] > 0, "name"])
    assert not any(f"x {n}\n" in msg for n in plan.loc[plan["order_qty"] == 0, "name"])


def test_store_round_trip():
    store.put("prefs", {"muted": ["EGGS"]})
    store.update("alerts", "KM-1|EGGS", {"status": "Reviewed"})
    assert store.get("prefs")["muted"] == ["EGGS"] and store.get("alerts")["KM-1|EGGS"]["status"] == "Reviewed"
    store._path().write_text("{broken")
    assert store.get("prefs", {}) == {}


# ---------------- the running app ----------------
def _app(monkeypatch, page="home.py", tool=None):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("SHELFSIGNAL_OUT", str(OUT))
    monkeypatch.setenv("LARIS_PAGE", page)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    if tool:
        at.session_state["tool"] = tool
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def test_budget_and_week_are_shared_across_pages(monkeypatch):
    at = _app(monkeypatch)
    week = at.session_state["as_of"]
    at.session_state["budget_rm"] = 300.0
    at.session_state["tool"] = "R"
    at.switch_page("views/laris.py").run()
    assert not at.exception and at.session_state["ctx"]["budget_rm"] == 300.0
    at.switch_page("views/orders.py").run()
    assert at.session_state["ctx"]["budget_rm"] == 300.0 and at.session_state["as_of"] == week
    assert at.session_state["ctx"]["totals"]["spent_rm"] <= 300.0 + 1e-6


def test_labels_and_no_claims_of_sending(monkeypatch):
    for page, tool in (("home.py", None), ("orders.py", None), ("laris.py", "S"), ("laris.py", "R"),
                       ("settings.py", None)):
        at = _app(monkeypatch, page, tool)
        assert any("MOCK DATA" in e.value for e in at.error)
        text = " ".join(m.value for m in at.markdown) + " " + " ".join(c.value for c in at.caption)
        for phrase in ("message sent", "sent automatically", "order was placed", "order has been placed", "synced with"):
            assert phrase not in text.lower()
        if page == "orders.py":
            assert "NOT CONNECTED" in text and "can't see whether it was sent" in text
        if tool == "S":
            assert "not net profit" in text
        if tool == "R":
            assert "SIMULATED" in text or "budget replay hasn't been run" in text


def test_reset_is_explicit_and_edits_survive_a_week_change(monkeypatch):
    at = _app(monkeypatch, "settings.py")
    assert next(b for b in at.button if b.label == "Reset to sample shop").disabled
    inp = at.session_state["inputs"].copy()
    inp.loc[0, "On hand"] = 12345
    at.session_state["inputs"], at.session_state["inputs_dirty"] = inp, True
    week = at.selectbox(key="set_week")
    target = week.options[0] if week.value != week.options[0] else week.options[1]
    at.selectbox(key="set_week").set_value(target).run()
    assert str(at.session_state["as_of"].date()) in target or at.session_state["inputs_key"][1] != str(week.value)
    assert not at.exception and at.session_state["inputs"].loc[0, "On hand"] == 12345


def test_app_never_imports_the_training_pipeline():
    src = (ROOT / "app.py").read_text() + "".join(p.read_text() for p in (ROOT / "views").glob("*.py"))
    assert "import pipeline" not in src and "from pipeline" not in src
