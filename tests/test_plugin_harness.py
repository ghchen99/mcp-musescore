"""Tests for finding MuseScore (dev/plugin_harness.py), without MuseScore."""

import os

from dev.plugin_harness import find_musescore


def test_musescore_bin_none_means_no_musescore(monkeypatch, tmp_path):
    musescore = tmp_path / "mscore"
    musescore.write_text("#!/bin/sh\n")
    musescore.chmod(0o755)
    monkeypatch.delenv("MUSESCORE_BIN", raising=False)  # also when pytest runs with --no-musescore
    monkeypatch.setenv("PATH", str(tmp_path))
    assert find_musescore() == str(musescore)  # found on the PATH
    monkeypatch.setenv("MUSESCORE_BIN", "none")
    assert find_musescore() is None


def test_musescore_bin_wins_over_the_path(monkeypatch, tmp_path):
    on_path, chosen = tmp_path / "mscore", tmp_path / "chosen"
    for path in (on_path, chosen):
        path.write_text("#!/bin/sh\n")
        path.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setenv("MUSESCORE_BIN", str(chosen))
    assert find_musescore() == str(chosen)
    assert os.access(find_musescore(), os.X_OK)
