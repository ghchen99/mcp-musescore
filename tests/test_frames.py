"""Tests for editing the frames of score files (src/mscz/frames.py).

The title frame and the end-notes frame.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from dev.plugin_harness import find_musescore
from src.mscz import ScoreFile
from src.mscz.frames import (
    end_notes,
    header_texts,
    plain_text,
    set_end_notes,
    set_header,
    set_structure_page,
    structure_table,
)

EXAMPLE = (
    Path(__file__).resolve().parent.parent
    / "examples"
    / "jazz piano"
    / "Jazz Piano.mscz"
)


@pytest.fixture
def score(tmp_path):
    path = tmp_path / "score.mscz"
    shutil.copy(EXAMPLE, path)
    return ScoreFile(path)


def end_frames(score):
    return [c for c in score.staves()[0] if c.tag == "TBox"]


def test_header_set_add_and_remove(score):
    assert header_texts(score) == {
        "title": "Jazz Piano",
        "composer": "Claude Sonnet 5.5",
    }
    changes = set_header(
        score,
        title="Hold The Line",
        subtitle="Drum chart",
        composer="",
        part_name="Drums",
    )
    assert changes == {
        "title": "set",
        "subtitle": "added",
        "composer": "removed",
        "part_name": "added",
    }
    assert header_texts(score) == {
        "title": "Hold The Line",
        "subtitle": "Drum chart",
        "part_name": "Drums",
    }

    score.save()
    assert header_texts(ScoreFile(score.path)) == {
        "title": "Hold The Line",
        "subtitle": "Drum chart",
        "part_name": "Drums",
    }


def test_header_keeps_fields_left_out(score):
    assert set_header(score, subtitle=None, part_name="") == {}
    assert header_texts(score)["title"] == "Jazz Piano"


def test_header_creates_a_title_frame_when_missing(score):
    staff = score.staves()[0]
    staff.remove(staff.find("VBox"))
    set_header(score, title="New")
    assert staff[0].tag == "VBox" and header_texts(score) == {"title": "New"}


def test_end_notes_are_added_replaced_and_removed(score):
    set_end_notes(
        score,
        "Changes from the original",
        ["Intro: x4, then x2", "Verses: x9 & fills kept"],
    )
    (frame,) = end_frames(score)
    text = frame.find("Text/text")
    assert frame.findtext("Text/style") == "frame"
    assert text.find("b").text == "Changes from the original"
    assert [c.tag for c in text] == ["b", "br", "br"]
    assert (
        plain_text(text)
        == "Changes from the original\nIntro: x4, then x2\nVerses: x9 & fills kept"
    )
    assert list(score.staves()[0])[-1] is frame  # after the last measure

    report = set_end_notes(score, "Changes", ["One line"])
    assert (report["replaced"], report["lines"]) == (1, 1)
    assert report["previous"] == [
        "Changes from the original",
        "Intro: x4, then x2",
        "Verses: x9 & fills kept",
    ]
    (frame,) = end_frames(score)
    assert plain_text(frame.find("Text/text")) == "Changes\nOne line"

    assert set_end_notes(score, "", [])["replaced"] == 1
    assert end_frames(score) == []


STRUCTURE = [
    {
        "section": "Intro",
        "bars": 9,
        "groove": "Main shuffle, 4 + 2",
        "fill": "Snare/tom pickup with flams",
    },
    {
        "section": "Verse 1",
        "bars": 16,
        "groove": "Verse shuffle x4, x4",
        "fill": "Snare fill into the chorus",
        "notes": "ignored: there is no notes column",
    },
]


def page_breaks(element):
    return [b.findtext("subtype") for b in element.findall("LayoutBreak")]


def test_structure_page_goes_after_the_end_notes(score):
    set_structure_page(score, "Song structure", STRUCTURE)
    staff = score.staves()[0]
    *_, last_measure, page = list(staff)
    assert (
        last_measure.tag == "Measure"
        and page_breaks(last_measure) == ["page"]
        and page.tag == "TBox"
    )
    text = plain_text(page.find("Text/text"))
    assert (
        text.startswith(
            "Song structure\nJazz Piano \u2013 Claude Sonnet 5.5\n\nSection"
        )
        and "Total: 25 bars" in text
    )
    assert "Notes" not in text and "ignored" not in text

    set_end_notes(score, "Notes", ["Roll: crash + crash 2"])
    *_, last_measure, notes, page2 = list(staff)
    assert (
        page2 is page
        and page_breaks(last_measure) == []
        and page_breaks(notes) == ["page"]
    )
    assert plain_text(notes.find("Text/text")) == "Notes\nRoll: crash + crash 2"

    # re-running either replaces it, never duplicates
    set_structure_page(score, "Song structure", STRUCTURE[:1])
    set_end_notes(score, "Notes", ["Roll: bars 92-93"])
    assert [c.tag for c in staff][-3:] == ["Measure", "TBox", "TBox"]
    assert "Total: 9 bars" in plain_text(list(staff)[-1].find("Text/text"))
    set_end_notes(score, "", [])
    assert (
        page_breaks(list(staff)[-2]) == ["page"]
        and list(staff)[-2].tag == "Measure"
    )
    set_structure_page(score, "Song structure", [])
    assert (
        list(staff)[-1].tag == "Measure" and page_breaks(list(staff)[-1]) == []
    )


def test_structure_table_fits_the_line():
    rows = STRUCTURE + [
        {
            "section": "Solo",
            "bars": "16",
            "groove": "Main shuffle with the open hi-hat on every third eighth",
            "fill": "Snare and tom fills every two bars, flams on the snare",
        }
    ]
    lines = structure_table(rows, width=84)
    assert all(len("  ".join(cells[:4]).rstrip()) <= 84 for cells in lines)
    assert [c.strip() for c in lines[0]] == [
        "Section",
        "Bars",
        "Groove",
        "Fills",
    ]


def test_structure_table_shows_counts_and_totals_the_bars(score):
    rows = [
        {"section": "Intro", "bars": 8, "count": "2+4+2", "groove": "Shuffle"},
        {
            "section": "Verse",
            "bars": 10,
            "groove": "Shuffle",
        },  # no count: 10 in fours
        {"section": "Chorus", "bars": "3x4+2", "groove": "Shuffle"},
    ]  # a label as bars
    assert [line[1].strip() for line in structure_table(rows)[1:]] == [
        "2+4+2",
        "2x4+2",
        "3x4+2",
    ]
    set_header(score, composer="", subtitle="Toto")
    report = set_structure_page(score, "Song structure", rows)
    assert report["artist"] == "Toto"  # no composer: the subtitle is the artist
    page = list(score.staves()[0])[-1].find("Text/text")
    assert "Total: 32 bars" in plain_text(page)
    # half a line of space between rows: a spacer line in a small font before each row
    assert sum(1 for f in page.iter("font") if f.get("size") == "5") == 3


def test_structure_page_song_and_artist_can_be_given(score):
    report = set_structure_page(
        score, "Song structure", STRUCTURE, song="Hold the Line", artist="Toto"
    )
    assert (report["song"], report["artist"]) == ("Hold the Line", "Toto")
    text = plain_text(list(score.staves()[0])[-1].find("Text/text"))
    assert text.startswith("Song structure\nHold the Line \u2013 Toto\n\n")


@pytest.mark.skipif(find_musescore() is None, reason="MuseScore not installed")
def test_musescore_keeps_the_frames(tmp_path, score):
    set_header(
        score, title="Hold The Line", subtitle="Drum chart", part_name="Drums"
    )
    set_end_notes(
        score,
        "Changes from the original",
        ["Intro: x4, then x2", "Dropped: open-hat endings"],
    )
    score.save()

    out_dir = tmp_path / "out"  # the CLI clears the folder it writes .mscx into
    out_dir.mkdir()
    out = out_dir / "roundtrip.mscx"
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    musescore = find_musescore()
    assert musescore is not None
    subprocess.run(
        [musescore, "-o", str(out), str(score.path)],
        env=env,
        timeout=300,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    reread = ScoreFile(out)
    assert header_texts(reread) == {
        "title": "Hold The Line",
        "subtitle": "Drum chart",
        "part_name": "Drums",
        "composer": "Claude Sonnet 5.5",
    }
    (frame,) = end_frames(reread)
    assert plain_text(frame.find("Text/text")) == (
        "Changes from the original\nIntro: x4, then x2\nDropped: open-hat endings"
    )


def test_end_notes_can_be_kept_and_extended(score):
    set_end_notes(
        score,
        "Changes from the original",
        ["Verses: x4", "Ghost notes removed"],
    )
    report = set_end_notes(
        score,
        "Changes from the original",
        ["Bars 24-25 merged", "Verses: x4"],
        append=True,
    )
    assert report["previous"] == [
        "Changes from the original",
        "Verses: x4",
        "Ghost notes removed",
    ]
    assert end_notes(score) == [
        "Changes from the original",
        "Verses: x4",
        "Ghost notes removed",
        "Bars 24-25 merged",
    ]
    report = set_end_notes(score, "Changes", ["Only this"])
    assert report["previous"][-1] == "Bars 24-25 merged" and end_notes(
        score
    ) == ["Changes", "Only this"]
