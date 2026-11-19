"""Tests for the plugin harness (dev/plugin_harness.py), without MuseScore."""

import os

from dev.plugin_harness import find_musescore, refused_actions


def test_musescore_bin_none_means_no_musescore(monkeypatch, tmp_path):
    # On Windows the PATH only finds programs with an extension such as .exe
    musescore = tmp_path / ("mscore.exe" if os.name == "nt" else "mscore")
    musescore.write_text("#!/bin/sh\n")
    musescore.chmod(0o755)
    monkeypatch.delenv(
        "MUSESCORE_BIN", raising=False
    )  # also when pytest runs with --no-musescore
    monkeypatch.setenv("PATH", str(tmp_path))
    # normcase: Windows may give the extension in capitals (.EXE)
    assert os.path.normcase(find_musescore()) == os.path.normcase(
        str(musescore)
    )  # found on the PATH
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
    assert os.access(chosen, os.X_OK)


def test_refused_actions_are_read_from_the_log():
    log = "\n".join(
        [
            "12:00:00 | INFO  | ActionsDispatcher::doDispatch | try call action: tie",
            "12:00:01 | WARN  | ActionsDispatcher::dispatch | not a registered action: undo",
            "12:00:02 | INFO  | ActionsDispatcher::doDispatch | no one can handle the action: insert-measure",
        ]
    )
    assert refused_actions(log) == ["undo", "insert-measure"]
    assert refused_actions(log, unknown_only=True) == ["undo"]
    assert refused_actions("try call action: tie") == []
