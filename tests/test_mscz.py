"""Tests for writing measure-repeat signs into score files (src/mscz)."""

import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from dev.plugin_harness import find_musescore
from src.mscz import ScoreFile, apply_measure_repeats

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "jazz piano" / "Jazz Piano.mscz"


def chord(pitch, duration="quarter", tie=None):
    """A chord; tie="next"/"prev" adds a tie that crosses the barline in that direction."""
    tie_xml = ""
    if tie:
        tie_xml = (f'<Spanner type="Tie"><Tie/><{tie}><location><measures>{1 if tie == "next" else -1}'
                   f'</measures></location></{tie}></Spanner>')
    return f"<Chord><durationType>{duration}</durationType><Note>{tie_xml}<pitch>{pitch}</pitch></Note></Chord>"


def bar(pitch, timesig=None, tie_out=False, tie_in=False, voice2=False, count=None, length=None):
    head = f"<TimeSig><sigN>{timesig[0]}</sigN><sigD>{timesig[1]}</sigD></TimeSig>" if timesig else ""
    beats = timesig[0] if timesig else 4
    notes = [chord(pitch, tie="prev" if tie_in and i == 0 else ("next" if tie_out and i == beats - 1 else None))
             for i in range(beats)]
    extra = f"<voice>{chord(pitch + 12, 'whole')}</voice>" if voice2 else ""
    rc = f"<measureRepeatCount>{count}</measureRepeatCount>" if count else ""
    attr = f' len="{length}"' if length else ""
    return f"<Measure{attr}>{rc}<voice>{head}{''.join(notes)}<BarLine/></voice>{extra}</Measure>"


def write_score(tmp_path, staff2_bars, staff1_bars=None):
    staff1_bars = staff1_bars or [bar(60, (4, 4) if i == 0 else None) for i in range(len(staff2_bars))]
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?><museScore version="4.70"><Score>'
        '<Part id="1"><Staff id="1"/><trackName>Piano</trackName></Part>'
        '<Part id="2"><Staff id="2"/><trackName>Drums</trackName></Part>'
        f'<Staff id="1">{"".join(staff1_bars)}</Staff>'
        f'<Staff id="2">{"".join(staff2_bars)}</Staff>'
        "</Score></museScore>"
    )
    path = tmp_path / "score.mscx"
    path.write_text(xml)
    return path


def drum_bars(path):
    return ScoreFile(path).staves()[1].findall("Measure")


def first_staff_bars(path):
    return ScoreFile(path).staves()[0].findall("Measure")


def apply(path, groups, staff=1):
    score = ScoreFile(path)
    report = apply_measure_repeats(score, staff, groups)
    score.save()
    return report


def voice_tags(measure):
    return [[c.tag for c in v] for v in measure.findall("voice")]


def test_one_bar_repeat_replaces_content_and_keeps_barline(tmp_path):
    path = write_score(tmp_path, [bar(36, (4, 4)), bar(36), bar(36, voice2=True), bar(38)])
    report = apply(path, [(2, 1), (3, 1)])
    assert [g["start"] for g in report["applied"]] == [2, 3]
    m2, m3 = drum_bars(path)[1:3]
    assert m2.findtext("measureRepeatCount") == "1"
    assert voice_tags(m3) == [["MeasureRepeat", "BarLine"]]  # voice 2 removed
    assert m3.findtext("voice/MeasureRepeat/subtype") == "1"
    assert m3.findtext("voice/MeasureRepeat/duration") == "4/4"
    assert first_staff_bars(path)[1].find("LayoutBreak") is None
    assert {"measure": 3, "items": ["voice 2"]} in report["dropped"]


def test_two_bar_repeat_layout(tmp_path):
    path = write_score(tmp_path, [bar(36, (4, 4)), bar(38), bar(36), bar(38)])
    apply(path, [(3, 2)])
    m3, m4 = drum_bars(path)[2:4]
    assert (m3.findtext("measureRepeatCount"), m4.findtext("measureRepeatCount")) == ("1", "2")
    assert voice_tags(m3) == [["MeasureRepeat"]]  # sign in the first bar, no end barline inside the group
    assert m3.findtext("voice/MeasureRepeat/subtype") == "2"
    assert voice_tags(m4) == [["Rest", "BarLine"]]
    assert m4.findtext("voice/Rest/durationType") == "measure"
    staff1 = first_staff_bars(path)
    assert staff1[2].findtext("LayoutBreak/subtype") == "nobreak"
    assert staff1[3].find("LayoutBreak") is None


def test_four_bar_repeat_puts_sign_in_second_bar(tmp_path):
    path = write_score(tmp_path, [bar(36 + i % 4, (4, 4) if i == 0 else None) for i in range(8)])
    apply(path, [(5, 4)])
    group = drum_bars(path)[4:8]
    assert [m.findtext("measureRepeatCount") for m in group] == ["1", "2", "3", "4"]
    assert [voice_tags(m)[0][0] for m in group] == ["Rest", "MeasureRepeat", "Rest", "Rest"]
    assert group[1].findtext("voice/MeasureRepeat/subtype") == "4"
    breaks = [m.findtext("LayoutBreak/subtype") for m in first_staff_bars(path)[4:8]]
    assert breaks == ["nobreak", "nobreak", "nobreak", None]


def test_measure_length_follows_time_signature_and_len(tmp_path):
    path = write_score(tmp_path, [bar(36, (3, 4)), bar(36, (3, 4)), bar(36, (3, 4), length="1/4"), bar(36, (3, 4))])
    apply(path, [(2, 1), (3, 1)])
    m2, m3 = drum_bars(path)[1:3]
    assert m2.findtext("voice/MeasureRepeat/duration") == "3/4"
    assert m3.findtext("voice/MeasureRepeat/duration") == "1/4"
    assert m2.find("voice/TimeSig") is not None  # leading time signature is kept


def test_bars_with_crossing_ties_are_skipped(tmp_path):
    path = write_score(tmp_path, [bar(36, (4, 4)), bar(36, tie_out=True), bar(36, tie_in=True), bar(36)])
    report = apply(path, [(2, 1), (3, 1), (4, 1)])
    assert [g["start"] for g in report["skipped"]] == [2, 3]
    assert "tie crosses its barline" in report["skipped"][0]["reason"]
    assert [g["start"] for g in report["applied"]] == [4]
    assert drum_bars(path)[1].find("measureRepeatCount") is None


def test_invalid_groups_are_skipped(tmp_path):
    path = write_score(tmp_path, [bar(36, (4, 4)), bar(36), bar(36), bar(36)])
    report = apply(path, [(1, 1), (2, 3), (4, 2), (3, 1), (3, 1)])
    reasons = {(g["start"], g["bars"]): g["reason"] for g in report["skipped"]}
    assert "before it" in reasons[(1, 1)]
    assert "1, 2 or 4" in reasons[(2, 3)]
    assert "only 4 measures" in reasons[(4, 2)]
    assert "another requested group" in reasons[(3, 1)]


def test_applying_twice_changes_nothing(tmp_path):
    path = write_score(tmp_path, [bar(36, (4, 4)), bar(38), bar(36), bar(38)])
    apply(path, [(3, 2)])
    before = path.read_bytes()
    report = apply(path, [(3, 2)])
    assert report["unchanged"] == [{"start": 3, "end": 4, "bars": 2}] and not report["applied"]
    assert path.read_bytes() == before


def test_partial_overlap_with_existing_group_is_skipped(tmp_path):
    path = write_score(tmp_path, [bar(36, (4, 4)), bar(38), bar(36), bar(38), bar(36)])
    apply(path, [(3, 2)])
    report = apply(path, [(4, 1)])
    assert "existing 2-bar repeat at bars 3-4" in report["skipped"][0]["reason"]
    report = apply(path, [(3, 1), (4, 1)])  # covering the whole old group replaces it
    assert len(report["applied"]) == 2
    assert [m.findtext("measureRepeatCount") for m in drum_bars(path)[2:4]] == ["1", "1"]


def test_mscz_keeps_other_entries(tmp_path):
    path = tmp_path / "piano.mscz"
    shutil.copy(EXAMPLE, path)
    score = ScoreFile(path)
    report = apply_measure_repeats(score, 1, [(2, 1)])
    score.save()
    assert report["applied"]

    with zipfile.ZipFile(EXAMPLE) as original, zipfile.ZipFile(path) as edited:
        assert original.namelist() == edited.namelist()
        for name in original.namelist():
            if name != "Jazz Piano.mscx":
                assert original.read(name) == edited.read(name), name
    measure = ScoreFile(path).staves()[1].findall("Measure")[1]
    assert measure.findtext("voice/MeasureRepeat/duration") == "3/4"


@pytest.mark.skipif(find_musescore() is None, reason="MuseScore not installed")
def test_musescore_reads_the_groups_back(tmp_path):
    """MuseScore loads the edited file and writes the same groups back."""
    path = tmp_path / "piano.mscz"
    shutil.copy(EXAMPLE, path)
    score = ScoreFile(path)
    apply_measure_repeats(score, 1, [(2, 1), (3, 2), (5, 4)])
    score.save()

    out = tmp_path / "roundtrip.mscx"
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    subprocess.run([find_musescore(), "-o", str(out), str(path)], env=env, timeout=300,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    assert out.exists()

    def layout(p):
        return [(m.findtext("measureRepeatCount"), m.findtext("voice/MeasureRepeat/subtype"))
                for m in ScoreFile(p).staves()[1].findall("Measure")[:8]]

    assert layout(out) == layout(path) == [
        (None, None), ("1", "1"), ("1", "2"), ("2", None), ("1", None), ("2", "4"), ("3", None), ("4", None),
    ]
