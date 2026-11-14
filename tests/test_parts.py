"""Tests for keeping only some instruments of a score file (src/mscz/parts.py)."""

import os
import shutil
import stat
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

from dev.plugin_harness import find_musescore
from src.mscz import ScoreFile, ScoreFileError
from src.mscz.locate import (
    OpenPartError,
    locate_open_score,
    part_with_score_id,
    read_score_id,
    score_shape,
)
from src.mscz.parts import detach_part, keep_parts, part_name

QUARTET = (
    Path(__file__).resolve().parent.parent
    / "examples"
    / "string quartet"
    / "String Quartet.mscz"
)


@pytest.fixture
def quartet(tmp_path):
    path = tmp_path / "quartet.mscz"
    shutil.copy(QUARTET, path)
    return ScoreFile(path)


def text_element(tag, text):
    element = ET.Element(tag)
    ET.SubElement(element, "text").text = text
    return element


def add_system_items(score):
    """Add the system items to the first staff.

    Tempo and a rehearsal mark on beat 1 of bar 2, a mark on beat 2 of bar 3, a repeat and a line break, all
    on the first staff (where MuseScore stores them).
    """
    first = score.staves()[0].findall("Measure")
    voice = first[1].find("voice")
    position = next(
        i for i, c in enumerate(voice) if c.tag in ("Chord", "Rest")
    )
    voice.insert(position, text_element("Tempo", "q = 90"))
    voice.insert(position + 1, text_element("RehearsalMark", "A"))
    voice3 = first[2].find("voice")
    crs = [i for i, c in enumerate(voice3) if c.tag in ("Chord", "Rest")]
    voice3.insert(crs[1], text_element("RehearsalMark", "B"))
    ET.SubElement(first[1], "startRepeat")
    first[1].insert(0, first[1][-1])
    brk = ET.Element("LayoutBreak")
    ET.SubElement(brk, "subtype").text = "line"
    first[3].insert(0, brk)


def test_keeps_one_part_and_moves_the_system_items(quartet):
    add_system_items(quartet)
    cello_before = [
        ET.tostring(m) for m in quartet.staves()[3].findall("Measure")
    ]
    report = keep_parts(quartet, [3])
    assert (
        report["kept_parts"] == ["Violoncello"] and report["removed_parts"] == 3
    )
    assert report["system_texts"] == 3 and report["moved_earlier"] == []

    (staff,) = quartet.staves()
    assert staff.get("id") == "1"
    assert [c.tag for c in staff][0] == "VBox"  # the title frame stays
    measures = staff.findall("Measure")
    assert len(measures) == len(cello_before)
    bar2 = [c.tag for c in measures[1].find("voice")]
    assert (
        bar2.index("Tempo")
        < bar2.index("RehearsalMark")
        < bar2.index(next(t for t in bar2 if t in ("Chord", "Rest")))
    )
    assert measures[1].find("startRepeat") is not None
    assert measures[3].findtext("LayoutBreak/subtype") == "line"
    assert [p.findtext("trackName") for p in quartet.score.findall("Part")] == [
        "Violoncello"
    ]


def test_keeping_the_first_staff_needs_no_merge(quartet):
    report = keep_parts(quartet, [0])
    assert report["kept_parts"] == ["Violin 1"] and len(quartet.staves()) == 1


def test_invalid_staves_are_refused(quartet):
    with pytest.raises(ScoreFileError):
        keep_parts(quartet, [7])
    with pytest.raises(ScoreFileError):
        keep_parts(quartet, [])


def test_saved_files_keep_normal_permissions(tmp_path, quartet):
    keep_parts(quartet, [3])
    target = tmp_path / "copy.mscz"
    quartet.save(target)
    umask = os.umask(0)
    os.umask(umask)
    assert stat.S_IMODE(target.stat().st_mode) == 0o666 & ~umask
    os.chmod(quartet.path, 0o640)
    quartet.save()
    assert stat.S_IMODE(quartet.path.stat().st_mode) == 0o640


@pytest.mark.skipif(find_musescore() is None, reason="MuseScore not installed")
def test_musescore_opens_the_copy(tmp_path, quartet):
    add_system_items(quartet)
    keep_parts(quartet, [3])
    quartet.save()
    out_dir = tmp_path / "out"  # the CLI clears the folder it writes .mscx into
    out_dir.mkdir()
    out = out_dir / "roundtrip.mscx"
    musescore = find_musescore()
    assert musescore is not None
    result = subprocess.run(
        [musescore, "-o", str(out), str(quartet.path)],
        timeout=300,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    assert result.returncode == 0
    reread = ScoreFile(out)
    (staff,) = reread.staves()
    texts = [
        "".join(t.findall("text")[0].itertext())
        for t in staff.iter("RehearsalMark")
    ]
    assert texts == ["A", "B"]
    tempos = [
        "".join(t.findall("text")[0].itertext())
        for t in staff.findall("Measure")[1].iter("Tempo")
    ]
    assert "q = 90" in tempos


def score_with_part(tmp_path, score_id="mcp-part-1"):
    """The quartet with a cello part whose metadata holds `score_id`.

    The part is stored as MuseScore stores parts (Excerpts/, links to the full score), as after the plugin
    ran in the part's tab and saved.
    """
    full = tmp_path / "Quartet.mscz"
    shutil.copy(QUARTET, full)
    part = ScoreFile(full)
    keep_parts(part, [3])
    part.score.insert(0, ET.Element("name"))
    part.score[0].text = "Player | Cello"
    tag = ET.SubElement(part.score, "metaTag", {"name": "mcpScoreId"})
    tag.text = score_id
    chord = part.staves()[0].findall("Measure/voice/Chord")[0]
    ET.SubElement(chord, "linkedTo").text = "Abc123"
    entry = "Excerpts/0_Cello/0_Cello.mscx"
    with zipfile.ZipFile(full, "a") as z:
        z.writestr(entry, part.to_bytes())
        z.writestr("Excerpts/0_Cello/0_Cello.mss", "<museScore/>")
    return full, entry


def test_a_part_tab_is_found_and_detached(tmp_path):
    full, entry = score_with_part(tmp_path)
    assert (
        read_score_id(full) is None
        and part_with_score_id(full, "mcp-part-1") == entry
    )
    with pytest.raises(OpenPartError) as found:
        locate_open_score("mcp-part-1", 1, 4, known=[full])
    assert (found.value.path, found.value.entry) == (full, entry)
    assert part_name(full, entry) == "Player | Cello"

    target = detach_part(full, entry, tmp_path / "Quartet - Cello.mscz")
    score = ScoreFile(target)
    assert len(score.staves()) == 1 and not list(score.root.iter("linkedTo"))
    with zipfile.ZipFile(target) as z:
        assert sorted(z.namelist()) == [
            "META-INF/container.xml",
            "Quartet - Cello.mscx",
            "score_style.mss",
        ]


def test_multi_measure_rests_are_not_counted_as_bars(tmp_path):
    """Multi-measure rests are not counted as bars.

    With multi-measure rests on, MuseScore saves each one as an extra <Measure> holding <multiMeasureRest>
    (seen in a saved drum part: 72 <Measure>s for 71 bars).
    """
    full = tmp_path / "Quartet.mscz"
    shutil.copy(QUARTET, full)
    score = ScoreFile(full)
    bars = len(score.staves()[0].findall("Measure"))
    for staff in score.staves():
        mm_rest = ET.Element("Measure")
        ET.SubElement(mm_rest, "multiMeasureRest").text = "2"
        staff.insert(
            list(staff).index(staff.findall("Measure")[1]) + 1, mm_rest
        )
    score.save()
    reread = ScoreFile(full)
    assert reread.multi_measure_rests == len(reread.staves())
    assert [len(s.findall("Measure")) for s in reread.staves()] == [bars] * len(
        reread.staves()
    )
    assert score_shape(full) == (len(reread.staves()), bars)


@pytest.mark.skipif(find_musescore() is None, reason="MuseScore not installed")
def test_musescore_opens_a_detached_part(tmp_path):
    full, entry = score_with_part(tmp_path)
    target = detach_part(full, entry, tmp_path / "Quartet - Cello.mscz")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    out = out_dir / "roundtrip.mscx"
    musescore = find_musescore()
    assert musescore is not None
    result = subprocess.run(
        [musescore, "-o", str(out), str(target)],
        timeout=300,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    assert result.returncode == 0 and len(ScoreFile(out).staves()) == 1
