import pytest


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path, monkeypatch):
    """Tests never touch the real state/laris_state.json."""
    monkeypatch.setenv("LARIS_STATE", str(tmp_path / "laris_state.json"))
