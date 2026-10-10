"""UI layer (laris_ui and the L·A·R·I·S tools): filters, figures that animate only on real changes, the motion and
accessibility rules in the stylesheet, and the honesty of feedback in the running app."""
import re
from pathlib import Path

import pandas as pd
import pytest
import streamlit as st

import laris_ui as ui
import store

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs_mock"
needs_outputs = pytest.mark.skipif(not (OUT / "metrics.json").exists(),
                                   reason="run make_mock_data.py and pipeline.py --out outputs_mock first")


@pytest.fixture(autouse=True)
def _fresh_session():
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    yield


# ---------------- pure helpers ----------------
def test_match_searches_name_id_and_brand_and_filters_categories():
    df = pd.DataFrame({"product": ["DAIRY", "GROCERY I", "SKU-77"], "name": ["🥛 Fresh milk 1L", "🛒 Maggi Curry",
                                                                          "Kopi O"]})
    inputs = pd.DataFrame({"product": ["DAIRY", "GROCERY I", "SKU-77"], "Brand": ["Farm Fresh", "Maggi", None]})
    assert list(ui.match(df, "MILK")["product"]) == ["DAIRY"]
    assert list(ui.match(df, "farm fresh", inputs=inputs)["product"]) == ["DAIRY"]           # brand
    assert list(ui.match(df, "sku-77")["product"]) == ["SKU-77"]                              # product id / SKU
    assert list(ui.match(df, "", ["Pantry & Groceries"])["product"]) == ["GROCERY I"]
    assert list(ui.match(df, "", ["Other"])["product"]) == ["SKU-77"]                         # user-added product
    assert ui.match(df, "zzz").empty and len(ui.match(df)) == 3


def test_category_prefers_the_catalogue_column():
    inputs = pd.DataFrame({"product": ["X"], "Category": ["Healthcare"]})
    assert ui.category_of("X", inputs) == "Healthcare"
    assert ui.category_of("DAIRY") == "Dairy & Beverages" and ui.category_of("NEW THING") == "Other"


def test_split_name_and_safe_key():
    assert ui.split_name("🥛 Fresh milk 1L") == ("🥛", "Fresh milk 1L")
    assert ui.split_name("Kopi O") == ("📦", "Kopi O")
    assert ui.safe_key("BREAD/BAKERY x") == "BREAD_BAKERY_x"


def test_counts_animate_only_on_first_sight_or_a_real_change():
    first = ui.count(3, "k")
    assert "lr-run" in first and "--from:0;--to:3" in first and '<span class="lr-sr">3</span>' in first
    assert "lr-run" not in ui.count(3, "k")                      # same value: no animation on a rerun
    changed = ui.count(5, "k")
    assert "lr-run" in changed and "--from:3;--to:5" in changed


def test_change_chip_shows_the_real_difference_and_nothing_on_first_sight():
    assert ui.delta_chip("o", 100.0) == ""
    chip = ui.delta_chip("o", 140.0)
    assert "▲ RM 40" in chip and "lr-pop" in chip
    kept = ui.delta_chip("o", 140.0)                              # stays visible, without replaying the animation
    assert "▲ RM 40" in kept and "lr-pop" not in kept
    assert "▼ RM 90" in ui.delta_chip("o", 50.0)


def test_entrance_plays_once_per_scope():
    assert ui.first_view("page:x") and not ui.first_view("page:x") and ui.first_view("page:y")


def test_html_helpers_escape_text():
    assert "<script>" not in ui.empty("!", "<script>", "x") and "&lt;script&gt;" in ui.empty("!", "<script>")
    assert "&lt;b&gt;" in ui.kpi("<b>", "1") and "&lt;b&gt;" in ui.chip("<b>", "c")
    assert 'aria-label="Stock lasts 2 days"' in ui.meter(0.5, "Stock lasts 2 days")


# ---------------- stylesheet rules ----------------
def _motion_block(css):
    i = css.index("@media (prefers-reduced-motion: no-preference)")
    depth, j = 0, css.index("{", i)
    for k in range(j, len(css)):
        depth += {"{": 1, "}": -1}.get(css[k], 0)
        if depth == 0:
            return css[i:k + 1], css[:i] + css[k + 1:]
    raise AssertionError("unbalanced motion block")


def test_everything_that_moves_respects_reduced_motion():
    block, rest = _motion_block(ui.CSS)
    rest = re.sub(r"@keyframes[^{]+\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", "", rest)   # keyframe definitions are inert
    assert "animation" not in rest.replace("animation-delay", "")
    assert not re.search(r"(?<![-\w])transform:", rest)
    assert ".lr-in" in block and ".lr-grow" in block and ".lr-num.lr-run" in block


def test_focus_is_visible_and_status_never_colour_only():
    assert ":focus-visible" in ui.CSS
    for level in ("URGENT", "WARNING", "OK"):
        html = ui.status_chip(level)
        assert level in html and 'class="i"' in html                # text plus an icon, not colour alone


def test_colours_come_from_tokens():
    body = ui.CSS.split(":root {", 1)[1].split("}", 1)[1]
    loose = set(re.findall(r"#[0-9A-Fa-f]{6}\b", body))
    assert len(loose) <= 12, f"too many hard-coded colours outside :root: {sorted(loose)}"


# ---------------- the running app ----------------
def _sections(at):
    """Expander labels (AppTest lists an expander that has an icon as a status block)."""
    return [e.label for e in at.expander] + [s.label for s in at.status]


def _app(monkeypatch, page="laris.py", tool=None):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("SHELFSIGNAL_OUT", str(OUT))
    monkeypatch.setenv("LARIS_PAGE", page)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    if tool:
        at.session_state["tool"] = tool
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


@needs_outputs
def test_saving_an_alert_moves_it_to_handled_and_confirms(monkeypatch):
    at = _app(monkeypatch, tool="A")
    status = next(s for s in at.selectbox if s.key and s.key.startswith("al_status_"))
    product = status.key.removeprefix("al_status_")
    status.set_value("Resolved")
    next(b for b in at.button if b.key == f"al_save_{product}").click().run()
    assert not at.exception
    ref = at.session_state["ctx"]["ref"]
    assert store.get("alerts", {})[f"{ref}|{product}"]["status"] == "Resolved"
    assert any("Saved:" in t.value for t in at.toast)
    assert any("Handled or snoozed" in label for label in _sections(at))


@needs_outputs
def test_a_failed_save_shows_no_success(monkeypatch):
    at = _app(monkeypatch, tool="A")
    status = next(s for s in at.selectbox if s.key and s.key.startswith("al_status_"))
    product = status.key.removeprefix("al_status_")

    def broken(*a, **k):
        raise OSError("read-only")
    monkeypatch.setattr(store, "update", broken)
    next(b for b in at.button if b.key == f"al_save_{product}").click().run()
    assert not at.exception
    toasts = [t.value for t in at.toast]
    assert any("Couldn't save" in t for t in toasts) and not any(t.startswith("Saved:") for t in toasts)


@needs_outputs
def test_muted_products_stay_visible_in_alerts(monkeypatch):
    at = _app(monkeypatch, tool="A")
    urgent = at.session_state["ctx"]["plan"].query("urgent")["product"].iloc[0]
    store.put("prefs", {"muted": [urgent]})
    at.run()
    assert not at.exception
    assert any(label.startswith("Muted, still at risk") for label in _sections(at))


@needs_outputs
def test_a_delivery_cannot_be_recorded_twice_by_accident(monkeypatch):
    at = _app(monkeypatch, tool="S")
    next(b for b in at.button if b.label == "I've sent it").click().run()
    assert store.get("orders", {})[at.session_state["ctx"]["ref"]]["status"] == "Shared"
    next(b for b in at.button if b.label == "Record delivery").click().run()
    assert not at.exception
    assert store.get("orders", {})[at.session_state["ctx"]["ref"]]["status"] in ("Received", "Partly received")
    labels = [b.label for b in at.button]
    assert "Record delivery" not in labels and "Record another delivery for this order" in labels


@needs_outputs
def test_look_ahead_choice_updates_the_shared_order(monkeypatch):
    at = _app(monkeypatch, tool="L")
    radio = next((r for r in at.radio if r.key and r.key.startswith("la_opt_")), None)
    if radio is None:
        pytest.skip("no stock-up options this week")
    product = radio.key.removeprefix("la_opt_")
    before = at.session_state["ctx"]["plan"].set_index("product").at[product, "order_qty"]
    radio.set_value("skip" if radio.value != "skip" else "full").run()
    use = next(b for b in at.button if b.key == f"la_use_{product}")
    assert not use.disabled
    qty = float(use.label.split()[1].replace(",", ""))
    use.click().run()
    after = at.session_state["ctx"]["plan"].set_index("product").at[product, "order_qty"]
    assert after == qty and after != before
    assert any("this week's order is now" in t.value for t in at.toast)


@needs_outputs
def test_home_counts_match_the_tools(monkeypatch):
    import planning
    at = _app(monkeypatch, page="home.py")
    att = planning.attention(at.session_state["ctx"])
    head = " ".join(m.value for m in at.markdown if "lr-title" in m.value)
    if att["total"]:
        assert f"{att['total']} product" in head
    tile = _app(monkeypatch, tool="A")
    labels = " ".join(b.label for b in tile.button)
    assert (f"Alert · {len(att['urgent'])} run out soon" in labels) or not att["urgent"]
    assert (f"Reduce Waste · {len(att['waste'])} may go to waste" in labels) or not att["waste"]


# ---------------- prediction signatures and the header ----------------
def test_sparkline_is_valid_svg_with_a_label():
    import xml.etree.ElementTree as ET
    svg = ui.sparkline([5, 6, 7, 5, 8], [6, 7, 9, 8, 7, 6, 7], [4, 5, 6, 5, 5, 4, 5], [8, 9, 12, 11, 9, 8, 9],
                       label="Eggs <tray>")
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg") and root.get("role") == "img" and root.get("aria-label") == "Eggs <tray>"
    assert root.find("{*}polygon") is not None or root.find("polygon") is not None      # the forecast range band
    assert ui.sparkline([], [1, 2, 3], [0, 1, 2], [2, 3, 4]).startswith("<svg")         # no history still draws


def test_header_hides_running_text_and_deploy():
    assert '[data-testid="stAppDeployButton"]' in ui.CSS and '[data-testid="stStatusWidget"] * {display: none' in ui.CSS


@needs_outputs
def test_forecast_grid_matches_the_plan(monkeypatch):
    import numpy as np
    import planning
    at = _app(monkeypatch, page="home.py")
    ctx = at.session_state["ctx"]
    grid, days = planning.forecast_grid(ctx)
    assert len(days) == 7 and len(grid) == len(ctx["plan"])
    demand = ctx["rows"].set_index("product")["demand_7d"]
    assert np.allclose(grid.set_index("product")[days].sum(axis=1), demand.loc[grid["product"]].to_numpy(), atol=1e-6)
    assert np.allclose(grid["total"], grid[days].sum(axis=1))


def test_purchase_order_and_activity_log():
    import planning
    plan = pd.DataFrame({"name": ["🥛 Dutch Lady 1L", "Kopi O"], "order_qty": [12.0, 0.0], "unit_cost": [6.2, 3.0],
                         "order_rm": [74.4, 0.0]})
    po = planning.purchase_order(plan, "KM-1-20170809", "2017-08-09", "Dairy distributor")
    assert list(po["Product"]) == ["Dutch Lady 1L"] and po["Line total (RM)"].iloc[0] == 74.4
    state = {"alerts": {"KM|EGGS": {"status": "Action planned", "choice": "topup", "at": "2026-10-10 10:00"}},
             "orders": {"KM": {"history": [{"status": "Shared", "at": "2026-10-10 11:00", "note": ""}]}},
             "stock_log": [{"at": "2026-10-10 09:00", "name": "Eggs", "before": 4, "after": 10, "reason": "Stock count"}]}
    log = planning.activity(state, {"EGGS": "Eggs"})
    assert list(log["Area"]) == ["S · Order", "A · Alert", "Stock count"] and log.loc[1, "Product"] == "Eggs"
