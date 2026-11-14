import os

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--no-musescore",
        action="store_true",
        help="Skip the tests that need MuseScore, even when it is installed (the commit hook uses this)",
    )


def pytest_configure(config):
    """Apply --no-musescore by setting MUSESCORE_BIN=none.

    Runs before the tests are collected, where the MuseScore tests decide whether to skip themselves.
    """
    if config.getoption("--no-musescore"):
        os.environ["MUSESCORE_BIN"] = "none"


@pytest.fixture(autouse=True)
def no_reopen_gap(monkeypatch):
    """Turn off the wait between score reopens.

    The server spaces score reopens by a few seconds so MuseScore can settle; tests don't need to wait.
    """
    from src.tools import score_file

    monkeypatch.setattr(score_file, "REOPEN_GAP", 0.0)
