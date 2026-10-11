import pytest


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path, monkeypatch):
    """Tests never touch the real state/laris_state.json."""
    monkeypatch.setenv("LARIS_STATE", str(tmp_path / "laris_state.json"))
    monkeypatch.setenv("LARIS_AI_DISABLED", "1")   # never call a real AI service from tests
    monkeypatch.setenv("LARIS_TODAY", "2026-10-12")   # fixed planning week, so holidays and dates are repeatable
