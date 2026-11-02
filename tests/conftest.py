import pytest


@pytest.fixture(autouse=True)
def no_reopen_gap(monkeypatch):
    """The server spaces score reopens by a few seconds so MuseScore can settle; tests don't need to wait."""
    from src.tools import score_file
    monkeypatch.setattr(score_file, "REOPEN_GAP", 0.0)
