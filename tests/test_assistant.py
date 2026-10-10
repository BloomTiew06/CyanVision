"""The LARIS assistant: tools return real, JSON-safe figures; the AI loop only calls allowlisted tools; failures and
missing configuration fall back to labelled quick answers; actions are proposals that need confirmation."""
import json
from pathlib import Path

import pandas as pd
import pytest

import assistant as A
import assistant_tools as T
import laris_core as core
from inventory import load_settings

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs_mock"
pytestmark = pytest.mark.skipif(not (OUT / "metrics.json").exists(),
                                reason="run make_mock_data.py and pipeline.py --out outputs_mock first")


@pytest.fixture(scope="module")
def ctx():
    fc = pd.read_parquet(OUT / "forecasts.parquet")
    fc["date"], fc["store"] = pd.to_datetime(fc["date"]), fc["store"].astype(str)
    sig = pd.read_csv(OUT / "sigma.csv", dtype={"store": str}).set_index("sid")
    metrics = json.loads((OUT / "metrics.json").read_text())
    test = fc[fc["split"] == "test"]
    days = sorted(d for d in test["date"].unique() if d + pd.Timedelta(days=6) <= test["date"].max())
    store_id, as_of = sorted(fc["store"].unique())[0], pd.Timestamp(days[len(days) // 2])
    settings = load_settings(ROOT / "product_settings.csv")
    inputs, _ = core.default_inputs(core.week_view(fc, store_id, as_of), settings, sig, store_id)
    c = core.build_context(fc, sig, settings, store_id, as_of, inputs, 1000, unc=pd.read_csv(OUT / "uncertainty.csv"),
                           alert_cfg=metrics["alert_backtest"])
    return {**c, "metrics": metrics}


OFF = {"enabled": False}
ON = {"enabled": True, "api_key": "test", "model": "test-model", "base_url": "http://example.invalid"}


def test_every_tool_returns_json_safe_data(ctx):
    for name in T.TOOLS:
        args = {"product": "eggs", "quantity": 10} if name == "propose_order_change" else \
            {"product": "eggs"} if name == "get_product_details" else {"query": "milk"} if name == "search_products" else {}
        json.dumps(T.run_tool(ctx, name, args), allow_nan=False)


def test_tool_figures_match_the_shared_plan(ctx):
    plan = ctx["plan"]
    r = T.get_restock_recommendations(ctx, limit=50)
    assert r["order_total"] == pytest.approx(plan["order_rm"].sum(), abs=0.01)
    assert {i["name"] for i in r["items"]} == {T.plain(n) for n in plan.loc[plan["order_qty"] > 0, "name"]}
    b = T.get_budget_status(ctx)
    assert b["available_budget"] == pytest.approx(ctx["budget_rm"]) and b["order_total"] == pytest.approx(ctx["order_rm"])


def test_unknown_tools_and_extra_arguments_are_refused(ctx):
    assert "error" in T.run_tool(ctx, "os.system", {"cmd": "ls"})
    assert "matches" in T.run_tool(ctx, "search_products", {"query": "milk", "sql": "drop table"})


def test_order_change_is_only_a_validated_proposal(ctx):
    before = ctx["plan"]["order_qty"].copy()
    ok = T.propose_order_change(ctx, "eggs", 40)
    assert ok["status"] == "needs_confirmation" and ok["proposed_qty"] == 40
    for bad in (-1, 2.5, "lots", T.MAX_QTY + 1):
        assert T.propose_order_change(ctx, "eggs", bad)["status"] == "rejected"
    assert T.propose_order_change(ctx, "no such thing", 5)["status"] == "rejected"
    assert (ctx["plan"]["order_qty"] == before).all()       # nothing changed


def test_fallback_answers_and_follow_up(ctx):
    mem = {}
    r = A.ask("What should I restock this week?", [], ctx, OFF, mem)
    assert r["source"] == "fallback" and "RM" in r["text"] and mem["last_products"]
    f = A.ask("Which of those products is the most urgent?", [], ctx, OFF, mem)
    plan = ctx["plan"].assign(plain=ctx["plan"]["name"].map(T.plain))
    cands = plan[plan["plain"].isin(mem["last_products"])].assign(_u=lambda d: ~d["urgent"]).sort_values(
        ["_u", "cover_days"])
    assert cands.iloc[0]["plain"] in f["text"]
    p = A.ask("How much profit did I make this month?", [], ctx, OFF, mem)
    assert "not net profit" in p["text"]
    assert A.ask("what's the weather", [], ctx, OFF, mem)["text"] == A.HELP


def _fake(responses):
    calls = []

    def transport(cfg, payload):
        calls.append(payload)
        return responses[len(calls) - 1]
    return transport, calls


def test_ai_loop_calls_tools_and_returns_the_answer(ctx):
    transport, calls = _fake([
        {"choices": [{"message": {"content": "", "tool_calls": [
            {"id": "1", "type": "function", "function": {"name": "get_budget_status", "arguments": "{}"}}]}}]},
        {"choices": [{"message": {"content": "Spend about RM 996."}}]}])
    history = [{"role": "user", "content": f"q{i}"} for i in range(30)]
    r = A.ask("How much should I spend?", history, ctx, ON, {}, transport)
    assert r == {"text": "Spend about RM 996.", "source": "ai", "tools": ["get_budget_status"], "proposal": None}
    tool_msg = calls[1]["messages"][-1]
    assert tool_msg["role"] == "tool" and json.loads(tool_msg["content"])["available_budget"] == pytest.approx(1000)
    assert len([m for m in calls[0]["messages"] if m["role"] == "user"]) <= A.HISTORY_TURNS + 1   # bounded memory


def test_ai_proposal_is_passed_to_the_ui_not_executed(ctx):
    transport, _ = _fake([
        {"choices": [{"message": {"tool_calls": [{"id": "1", "function": {
            "name": "propose_order_change", "arguments": json.dumps({"product": "eggs", "quantity": 40})}}]}}]},
        {"choices": [{"message": {"content": "Press Confirm to change eggs to 40."}}]}])
    r = A.ask("set eggs to 40", [], ctx, ON, {}, transport)
    assert r["proposal"]["status"] == "needs_confirmation" and r["proposal"]["proposed_qty"] == 40


def test_provider_failure_keeps_a_useful_labelled_answer(ctx):
    def broken(cfg, payload):
        raise A.ProviderError("the AI service is busy or out of credit")
    r = A.ask("Which products are selling best?", [], ctx, ON, {}, broken)
    assert r["source"] == "error" and "busy or out of credit" in r["text"] and "RM" in r["text"]
    junk, _ = _fake([{"unexpected": True}])
    assert A.ask("hi", [], ctx, ON, {}, junk)["source"] == "error"


def test_missing_configuration_is_reported_not_crashed(monkeypatch):
    for k in ("AI_API_KEY", "AI_MODEL", "AI_BASE_URL"):
        monkeypatch.delenv(k, raising=False)
    cfg = A.config()
    assert not cfg["enabled"] and A.check_connection(cfg)[0] is False
    monkeypatch.setenv("AI_API_KEY", "k")
    assert not A.config()["enabled"]              # a key without a model is not enough
    monkeypatch.setenv("AI_MODEL", "m")
    assert not A.config()["enabled"]              # kill switch from conftest wins
    monkeypatch.delenv("LARIS_AI_DISABLED")
    assert A.config()["enabled"] and A.config()["base_url"].startswith("https://")


def test_home_chat_suggestion_answers_and_confirmation_is_verified(monkeypatch):
    from streamlit.testing.v1 import AppTest
    for k in ("AI_API_KEY", "AI_MODEL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SHELFSIGNAL_OUT", str(OUT))
    monkeypatch.setenv("LARIS_PAGE", "home.py")
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    at.run()
    at.chat_input(key="chat_in").set_value("What should I restock this week?").run()
    assert not at.exception and at.session_state["chat"][-1]["source"] == "fallback"
    at.chat_input(key="chat_in").set_value("set eggs to 40").run()
    msg = at.session_state["chat"][-1]
    assert msg["pending"] and msg["proposal"]["proposed_qty"] == 40
    assert at.session_state["ctx"]["plan"].set_index("product").loc[msg["proposal"]["product_id"], "order_qty"] != 40
    next(b for b in at.button if b.label == "Confirm").click().run()
    assert not at.exception
    pid = msg["proposal"]["product_id"]
    assert at.session_state["ctx"]["plan"].set_index("product").loc[pid, "order_qty"] == 40
    assert at.session_state["chat"][-1]["content"].startswith("Done:")
