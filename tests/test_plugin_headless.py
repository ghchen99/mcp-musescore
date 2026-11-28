"""Tests of the real QML plugin, run headless in MuseScore.

They use dev/plugin_harness.py, and are skipped without MuseScore.
"""

import shutil
import zipfile
from pathlib import Path

import pytest

from dev.plugin_harness import find_musescore, run

JAZZ = (
    Path(__file__).resolve().parent.parent
    / "examples"
    / "jazz piano"
    / "Jazz Piano.mscz"
)

pytestmark = pytest.mark.skipif(
    find_musescore() is None, reason="MuseScore not installed"
)


def results_by_action(results):
    return {entry["action"]: entry["result"] for entry in results}


def text_lines(path):
    with zipfile.ZipFile(path) as z:
        name = next(
            n for n in z.namelist() if n.endswith(".mscx") and "/" not in n
        )
        return z.read(name).decode("utf-8").count('<Spanner type="TextLine">')


def test_score_reading_reports_parts_and_ranges():
    results = results_by_action(
        run(
            [
                {
                    "action": "getScore",
                    "params": {
                        "startMeasure": 2,
                        "endMeasure": 3,
                        "staves": [1],
                    },
                },
            ],
            JAZZ,
        )
    )
    analysis = results["getScore"]["analysis"]
    assert [m["measure"] for m in analysis["measures"]] == [2, 3]
    assert analysis["measures"][0]["durationTicks"] == 1440  # 3/4
    assert analysis["staves"] == [
        {
            **analysis["staves"][0],
            "index": 1,
            "partName": "Piano",
            "isDrums": False,
        }
    ]
    assert analysis["measures"][0]["elements"]["staff1"]


def test_highlights_are_added_to_the_score(tmp_path):
    out = tmp_path / "out.mscz"
    results = results_by_action(
        run(
            [
                {
                    "action": "highlightNotes",
                    "params": {
                        "startMeasure": 1,
                        "endMeasure": 1,
                        "startStaff": 0,
                        "endStaff": 1,
                    },
                },
                {
                    "action": "highlightSymbols",
                    "params": {"startMeasure": 1, "endMeasure": 1},
                },
                {
                    "action": "addHighlight",
                    "params": {
                        "startMeasure": 2,
                        "endMeasure": 2,
                        "startStaff": 1,
                        "endStaff": 2,
                    },
                },
            ],
            JAZZ,
            out=out,
        )
    )
    assert results["highlightNotes"]["boxes"] >= 1
    assert results["highlightSymbols"]["found"]["time_signatures"] == 2
    assert results["addHighlight"]["placedSegments"] == 1
    boxes = (
        results["highlightNotes"]["boxes"]
        + results["highlightSymbols"]["boxes"]
        + 1
    )
    assert (
        text_lines(out) == 2 * boxes
    )  # every line is stored with a start and an end tag


def test_clear_highlights_removes_them(tmp_path):
    out = tmp_path / "out.mscz"
    results = run(
        [
            {
                "action": "highlightNotes",
                "params": {
                    "startMeasure": 1,
                    "endMeasure": 2,
                    "startStaff": 0,
                    "endStaff": 1,
                },
            },
            {
                "action": "clearHighlights",
                "params": {"startMeasure": 1, "endMeasure": 2},
            },
        ],
        JAZZ,
        out=out,
    )
    assert results[1]["result"]["removed"] == results[0]["result"]["boxes"]
    assert text_lines(out) == 0


def test_held_lyrics_add_no_empty_lyrics(tmp_path):
    out = tmp_path / "out.mscz"
    results = results_by_action(
        run(
            [
                {"action": "goToBeginningOfScore", "params": {}},
                {
                    "action": "addLyrics",
                    "params": {"lyrics": ["Glo-", "ri", "_", "a"]},
                },
                {
                    "action": "getScore",
                    "params": {
                        "startMeasure": 1,
                        "endMeasure": 2,
                        "staves": [0],
                    },
                },
            ],
            JAZZ,
            out=out,
        )
    )
    assert (
        results["addLyrics"]["addedCount"] == 3
        and results["addLyrics"]["heldCount"] == 1
    )
    with zipfile.ZipFile(out) as z:
        name = next(
            n for n in z.namelist() if n.endswith(".mscx") and "/" not in n
        )
        mscx = z.read(name).decode("utf-8")
    assert mscx.count("<Lyrics>") == 3
    assert "<text></text>" not in mscx


def test_go_to_measure_moves_the_cursor_there():
    results = results_by_action(
        run(
            [
                {"action": "goToMeasure", "params": {"measure": 3}},
                {
                    "action": "setTimeSignature",
                    "params": {"numerator": 2, "denominator": 4},
                },
                {
                    "action": "getScore",
                    "params": {
                        "startMeasure": 1,
                        "endMeasure": 3,
                        "includeElements": False,
                    },
                },
            ],
            JAZZ,
        )
    )
    selection = results["goToMeasure"]["currentSelection"]
    assert selection["startTick"] == 2 * 1440  # bars 1-2 are in 3/4
    assert (selection["startStaff"], selection["endStaff"]) == (0, 2)
    measures = results["getScore"]["analysis"]["measures"]
    assert [m["durationTicks"] for m in measures] == [1440, 1440, 960]


def test_next_staff_after_go_to_measure_moves_to_the_second_staff():
    results = run(
        [
            {"action": "goToMeasure", "params": {"measure": 2}},
            {"action": "nextStaff", "params": {}},
            {"action": "nextElement", "params": {}},
        ],
        JAZZ,
    )
    # go_to_measure selects the bar on both staves; next_staff goes to the second
    staff = results[1]["result"]["currentSelection"]
    assert (staff["startStaff"], staff["endStaff"]) == (1, 2)
    assert staff["startTick"] == 1440
    after = results[2]["result"]["currentSelection"]
    assert after["startStaff"] == 1


def test_staff_navigation_past_the_outer_staves_is_an_error():
    results = run(
        [
            {"action": "goToMeasure", "params": {"measure": 2}},
            {"action": "prevStaff", "params": {}},
            {"action": "nextStaff", "params": {}},
            {"action": "nextStaff", "params": {}},
            {"action": "prevStaff", "params": {}},
        ],
        JAZZ,
    )
    assert "first staff" in results[1]["result"]["error"]
    assert results[2]["result"]["currentSelection"]["startStaff"] == 1
    assert "last staff" in results[3]["result"]["error"]
    assert results[4]["result"]["currentSelection"]["startStaff"] == 0


def test_select_custom_range_end_staff_is_exclusive():
    """EndStaff stops before that staff, as MuseScore's selectRange() does.

    The element map was built with an inclusive loop, so it reported a staff
    MuseScore had not selected. With startStaff == endStaff it selected nothing
    at all while still reporting success, and the edits that followed went to
    staff 0 instead of the staff that was asked for.
    """
    one_staff, empty = run(
        [
            {
                "action": "selectCustomRange",
                "params": {
                    "startTick": 0,
                    "endTick": 1440,  # bar 1 is in 3/4
                    "startStaff": 1,
                    "endStaff": 2,
                },
            },
            {
                "action": "selectCustomRange",
                "params": {
                    "startTick": 0,
                    "endTick": 1440,
                    "startStaff": 1,
                    "endStaff": 1,
                },
            },
        ],
        JAZZ,
    )
    selection = one_staff["result"]["currentSelection"]
    assert list(selection["elements"]) == ["staff1"]
    assert (selection["startStaff"], selection["endStaff"]) == (1, 2)
    assert "endStaff is exclusive" in empty["result"]["error"]


def test_a_staff_step_that_cannot_move_stops_a_sequence():
    (result,) = run(
        [
            {
                "action": "processSequence",
                "params": {
                    "sequence": [
                        {"action": "goToMeasure", "params": {"measure": 2}},
                        {"action": "prevStaff", "params": {}},
                        {"action": "nextElement", "params": {}},
                    ]
                },
            }
        ],
        JAZZ,
    )
    error = result["result"]["error"]
    assert error.startswith("Step 2 of 3 (prevStaff) failed")


def test_errors_come_back_as_results():
    (result,) = run(
        [{"action": "colorRange", "params": {"startMeasure": 99}}], JAZZ
    )
    assert "Invalid measure range" in result["result"]["error"]


def test_bars_are_numbered_as_played():
    results = results_by_action(
        run(
            [
                {
                    "action": "setRepeatBarlines",
                    "params": {
                        "startMeasure": 2,
                        "endMeasure": 3,
                        "playCount": 3,
                    },
                },
                {"action": "numberAsPlayed", "params": {}},
                {
                    "action": "getScore",
                    "params": {
                        "startMeasure": 1,
                        "endMeasure": 6,
                        "includeElements": False,
                    },
                },
            ],
            JAZZ,
        )
    )
    assert [
        (o["measure"], o["addToNumber"])
        for o in results["numberAsPlayed"]["offsets"]
    ] == [(4, 4)]
    measures = results["getScore"]["analysis"]["measures"]
    assert [m["number"] for m in measures] == [1, 2, 3, 8, 9, 10]
    assert measures[1]["repeatStart"] is True and measures[2]["repeatEnd"] == 3


def test_add_text_is_styled(tmp_path):
    out = tmp_path / "out.mscz"
    (entry,) = run(
        [
            {
                "action": "addText",
                "params": {
                    "measure": 2,
                    "text": "Cue",
                    "fontSize": 8,
                    "italic": True,
                    "color": "#9E9E9E",
                    "placement": "below",
                },
            }
        ],
        JAZZ,
        out=out,
    )
    assert entry["result"]["success"]
    with zipfile.ZipFile(out) as z:
        name = next(
            n for n in z.namelist() if n.endswith(".mscx") and "/" not in n
        )
        xml = z.read(name).decode("utf-8")
    staff_text = xml[xml.index("<StaffText>") : xml.index("</StaffText>")]
    assert "<size>8</size>" in staff_text and "<italic>1</italic>" in staff_text
    assert '<color r="158" g="158" b="158"' in staff_text
    assert "<placement>below</placement>" in staff_text and "Cue" in staff_text


def test_added_texts_and_marks_can_be_removed():
    results = run(
        [
            {"action": "setTempo", "params": {"bpm": 146, "measure": 1}},
            {
                "action": "addRehearsalMark",
                "params": {"measure": 2, "text": "Verse"},
            },
            {
                "action": "addText",
                "params": {
                    "measure": 1,
                    "text": "* crash on 1st time only",
                    "fontSize": 8,
                    "italic": True,
                },
            },
            {"action": "addText", "params": {"measure": 3, "text": "**"}},
            {
                "action": "addLabel",
                "params": {"measure": 5, "text": "Groove x7"},
            },
            {
                "action": "addVolta",
                "params": {"startMeasure": 6, "endMeasure": 6},
            },
            {
                "action": "removeAnnotations",
                "params": {
                    "startMeasure": 1,
                    "endMeasure": 8,
                    "kinds": ["texts"],
                    "contains": "**",
                },
            },
            {
                "action": "removeAnnotations",
                "params": {
                    "startMeasure": 1,
                    "endMeasure": 8,
                    "kinds": [
                        "texts",
                        "labels",
                        "rehearsal_marks",
                        "tempo",
                        "voltas",
                    ],
                },
            },
            {
                "action": "getScore",
                "params": {"startMeasure": 1, "endMeasure": 8, "staves": [0]},
            },
        ],
        JAZZ,
    )
    assert results[6]["result"]["removed"]["texts"] == 1
    assert results[7]["result"]["removed"] == {
        "texts": 1,
        "labels": 1,
        "rehearsal_marks": 1,
        "tempo": 1,
        "voltas": 1,
        "markers": 0,
        "jumps": 0,
        "chord_symbols": 0,
        "breaks": 0,
    }
    assert not any(
        m["markings"] for m in results[8]["result"]["analysis"]["measures"]
    )


def test_articulations_and_ghost_notes(tmp_path):
    out = tmp_path / "out.mscz"
    results = results_by_action(
        run(
            [
                {
                    "action": "addArticulation",
                    "params": {
                        "startMeasure": 1,
                        "endMeasure": 1,
                        "symbol": "half_open",
                    },
                },
                {
                    "action": "getScore",
                    "params": {
                        "startMeasure": 1,
                        "endMeasure": 1,
                        "staves": [0],
                    },
                },
                {
                    "action": "removeArticulations",
                    "params": {"startMeasure": 1, "endMeasure": 1},
                },
                {
                    "action": "ghostNotes",
                    "params": {
                        "startMeasure": 1,
                        "endMeasure": 8,
                        "mode": "list",
                    },
                },
            ],
            JAZZ,
            out=out,
        )
    )
    assert results["addArticulation"]["added"] > 0
    chords = [
        e
        for e in results["getScore"]["analysis"]["measures"][0]["elements"][
            "staff0"
        ]
        if e["name"] == "Chord"
    ]
    assert all(e.get("articulations") == ["half_open"] for e in chords)
    assert (
        results["removeArticulations"]["removed"]
        == results["addArticulation"]["added"]
    )
    assert results["ghostNotes"] == {
        "success": True,
        "ghostNotes": 0,
        "bars": [],
    }


def test_remove_parts_keeps_system_texts_of_the_removed_top_staff(tmp_path):
    """Removing the top staff keeps its system texts.

    make_part_score(in_place=True) relies on MuseScore moving tempo/rehearsal
    marks/repeats to the kept staff.
    """
    from src.mscz import ScoreFile
    from tests.test_parts import QUARTET, add_system_items

    source = tmp_path / "quartet.mscz"
    shutil.copy(QUARTET, source)
    score = ScoreFile(source)
    add_system_items(score)
    score.save()
    out_dir = tmp_path / "out"  # the CLI clears the folder it writes into
    out_dir.mkdir()
    out = out_dir / "out.mscz"
    results = results_by_action(
        run(
            [{"action": "removeParts", "params": {"keepStaves": [3]}}],
            source,
            out=out,
        )
    )
    assert results["removeParts"]["numStaves"] == 1
    (staff,) = ScoreFile(out).staves()

    def texts(tag):
        return [
            "".join(e.findall("text")[0].itertext()) for e in staff.iter(tag)
        ]

    assert texts("RehearsalMark") == ["A", "B"] and "q = 90" in texts("Tempo")
    assert (
        staff[0].tag == "VBox"
        and staff.findall("Measure")[1].find("startRepeat") is not None
    )


def test_export_makes_a_musicxml_copy_without_saving(tmp_path):
    """Exporting makes a MusicXML copy without saving.

    make_part_score(in_place=True) backs up the full score this way (writeScore
    can't write .mscz in 4.7).
    """
    export = tmp_path / "full.mxl"
    results = results_by_action(
        run(
            [
                {"action": "exportScore", "params": {"path": str(export)}},
                {
                    "action": "exportScore",
                    "params": {"path": str(tmp_path / "full.mscz")},
                },
            ],
            JAZZ,
        )
    )
    assert results["exportScore"]["error"].startswith(
        "MuseScore files cannot be exported"
    )  # the last result wins
    with zipfile.ZipFile(export) as z:
        assert any(
            name.endswith(".xml") and "META-INF" not in name
            for name in z.namelist()
        )


def test_coloring_includes_flams(tmp_path):
    """Coloring includes flams.

    A flam is a grace note (acciaccatura) attached to the main chord: it takes
    the chord's colour.
    """
    from src.mscz import ScoreFile
    from tests.test_rolls import chord, write_score

    flam = "<Chord><acciaccatura/><durationType>eighth</durationType><Note><pitch>38</pitch><tpc>16</tpc></Note></Chord>"
    source = write_score(
        tmp_path, [flam + chord("quarter", 38) + chord("quarter", 36) * 3]
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    out = out_dir / "out.mscz"
    results = results_by_action(
        run(
            [
                {
                    "action": "colorRange",
                    "params": {
                        "startMeasure": 1,
                        "endMeasure": 1,
                        "endBeat": 1,
                        "color": "#2ca02c",
                    },
                }
            ],
            source,
            out=out,
        )
    )
    assert (
        results["colorRange"]["colored"] == 2
    )  # the snare and its flam, not the kicks after beat 1
    chords = (
        ScoreFile(out).staves()[0].findall("Measure/voice")[0].findall("Chord")
    )
    grace, main, kick = chords[:3]
    assert grace.find("acciaccatura") is not None
    for colored in (grace, main):
        assert colored.findall("Note/color")[0].attrib == {
            "r": "44",
            "g": "160",
            "b": "44",
            "a": "255",
        }
    assert kick.find("Note/color") is None


def test_beam_over_rests_inside_dotted_quarter_groups(tmp_path):
    """Rests inside a dotted-quarter group are beamed over.

    12/8: a rest between two eighths of a dotted-quarter group is beamed over; a
    rest that starts or ends a group is not.
    """
    from src.mscz import ScoreFile
    from tests.test_rolls import chord, write_score

    rest = "<Rest><durationType>eighth</durationType></Rest>"
    hat, kick = chord("eighth", 42), chord("eighth", 36, 42)
    source = write_score(
        tmp_path,
        [
            kick
            + rest
            + hat
            + rest
            + hat
            + hat
            + kick
            + hat
            + hat
            + kick
            + hat
            + rest
        ],
    )
    source.write_text(
        source.read_text().replace(
            "<sigN>4</sigN><sigD>4</sigD>", "<sigN>12</sigN><sigD>8</sigD>"
        )
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    out = out_dir / "out.mscz"
    results = results_by_action(
        run(
            [{"action": "beamOverRests", "params": {"startMeasure": 1}}],
            source,
            out=out,
        )
    )
    assert results["beamOverRests"]["changed"] == 1
    rests = (
        ScoreFile(out).staves()[0].findall("Measure/voice")[0].findall("Rest")
    )
    assert [r.findtext("BeamMode") for r in rests] == ["mid", None, None]


def test_section_counts_sit_next_to_the_section_label(tmp_path):
    """Section counts sit next to the section label.

    A bold red count right of the rehearsal mark, placed by offset (autoplace
    off); running it again replaces it, and other staff texts (e.g. a "*" crash
    mark) stay.
    """
    from src.mscz import ScoreFile
    from tests.test_rolls import chord, write_score

    mark = "<RehearsalMark><text>Verse 1</text></RehearsalMark><StaffText><text>*</text></StaffText>"
    source = write_score(
        tmp_path,
        [mark + chord("quarter", 36, 42) * 4, chord("quarter", 36, 42) * 4],
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    out = out_dir / "out.mscz"
    beside = {"mode": "beside"}
    results = run(
        [
            {
                "action": "addSectionCounts",
                "params": {
                    "counts": [{"measure": 1, "text": "2x4+2"}],
                    **beside,
                },
            },
            {
                "action": "addSectionCounts",
                "params": {
                    "counts": [{"measure": 1, "text": "(3x4)"}],
                    **beside,
                },
            },
        ],
        source,
        out=out,
    )
    assert [r["result"]["removed"] for r in results] == [0, 1]
    texts = (
        ScoreFile(out)
        .staves()[0]
        .findall("Measure/voice")[0]
        .findall("StaffText")
    )
    plain = ["".join(t.findall("text")[0].itertext()) for t in texts]
    assert sorted(plain) == ["*", "3x4"]
    count = texts[plain.index("3x4")]
    assert (
        count.findtext("autoplace") == "0" and count.find("offset") is not None
    )
    assert count.findtext("bold") == "1" and count.findall("color")[
        0
    ].attrib == {"r": "214", "g": "39", "b": "40", "a": "255"}


def test_section_counts_in_the_label_replace_counts_beside_it(tmp_path):
    from src.mscz import ScoreFile
    from tests.test_rolls import chord, write_score

    mark = "<RehearsalMark><text>Chorus 4</text></RehearsalMark>"
    stale = "<StaffText><bold>1</bold><text>4+2</text></StaffText>"  # a count left on another bar earlier
    source = write_score(
        tmp_path,
        [
            mark + chord("quarter", 36, 42) * 4,
            stale + chord("quarter", 36, 42) * 4,
        ],
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    out = out_dir / "out.mscz"
    run(
        [
            {
                "action": "addSectionCounts",
                "params": {
                    "counts": [{"measure": 1, "text": "4"}],
                    "mode": "beside",
                },
            },
            {
                "action": "addSectionCounts",
                "params": {"counts": [{"measure": 1, "text": "2x4"}]},
            },
            {
                "action": "addSectionCounts",
                "params": {
                    "counts": [{"measure": 1, "text": "(4+2)"}],
                    "clearAll": True,
                },
            },
        ],
        source,
        out=out,
    )
    staff = ScoreFile(out).staves()[0]
    assert (
        "".join(staff.findall("Measure/voice/RehearsalMark/text")[0].itertext())
        == "Chorus 4 (4+2)"
    )
    assert not list(staff.iter("StaffText"))


def test_delete_measures_inside_a_multi_measure_rest(tmp_path):
    """Measures inside a multi-measure rest can be deleted.

    With multi-measure rests on, deleting empty bars used to report success and
    delete nothing (seen live).
    """
    from tests.test_rolls import chord, write_score

    rest = "<Rest><durationType>measure</durationType><duration>4/4</duration></Rest>"
    source = write_score(
        tmp_path, [chord("whole", 49)] + [rest] * 4 + [chord("whole", 38)]
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    results = results_by_action(
        run(
            [
                {
                    "action": "setStyle",
                    "params": {"key": "createMultiMeasureRests", "value": True},
                },
                {
                    "action": "deleteMeasures",
                    "params": {"startMeasure": 3, "endMeasure": 4},
                },
                {
                    "action": "getScore",
                    "params": {
                        "startMeasure": 1,
                        "endMeasure": 1,
                        "includeElements": False,
                    },
                },
            ],
            source,
            out=out_dir / "out.mscz",
        )
    )
    assert results["deleteMeasures"]["numMeasures"] == 4
    assert results["getScore"]["analysis"]["numMeasures"] == 4


TPC_BY_PITCH_CLASS = [14, 21, 16, 23, 18, 13, 20, 15, 22, 17, 24, 19]


def xml_note(pitch, ahead=None, back=None):
    """Make a note, optionally tied ahead or back.

    It is tied to the note `ahead` or from the note `back` (fractions of a
    whole, e.g. "1/4").
    """
    ties = ""
    if ahead:
        ties += f'<Spanner type="Tie"><Tie/><next><location><fractions>{ahead}</fractions></location></next></Spanner>'
    if back:
        ties += f'<Spanner type="Tie"><prev><location><fractions>-{back}</fractions></location></prev></Spanner>'
    return f"<Note>{ties}<pitch>{pitch}</pitch><tpc>{TPC_BY_PITCH_CLASS[pitch % 12]}</tpc></Note>"


def xml_chord(duration, *notes):
    """A chord of `notes` (xml_note strings, or plain pitches)."""
    notes = [n if isinstance(n, str) else xml_note(n) for n in notes]
    return f"<Chord><durationType>{duration}</durationType>{''.join(notes)}</Chord>"


def tie_score(tmp_path, *bars):
    """A one-staff 4/4 score file with the given bars (voice-1 contents)."""
    from tests.test_rolls import write_score

    return write_score(tmp_path, list(bars))


def bars_of(get_score_result):
    """The elements of every measure in a getScore result, in time order."""
    return [
        sorted(m["elements"]["staff0"], key=lambda e: e["startTick"])
        for m in get_score_result["analysis"]["measures"]
    ]


def ties(element):
    """{pitch: (tieForward, tieBack)} for a chord element from getScore."""
    return {
        n["pitchMidi"]: (n.get("tieForward", False), n.get("tieBack", False))
        for n in element["notes"]
    }


def test_get_score_reports_ties_per_note(tmp_path):
    """The getScore action reports ties per note.

    Ties belong to notes. getScore used to read them from the chord, so isTie
    was always false.
    """
    # Bar 1: C-E-G with only C and E tied into C-E-A, then a D tied across the barline into bar 2
    source = tie_score(
        tmp_path,
        xml_chord(
            "quarter", xml_note(60, ahead="1/4"), xml_note(64, ahead="1/4"), 67
        )
        + xml_chord(
            "quarter", xml_note(60, back="1/4"), xml_note(64, back="1/4"), 69
        )
        + xml_chord("half", xml_note(62, ahead="1/2")),
        xml_chord("whole", xml_note(62, back="1/2")),
    )
    (entry,) = run(
        [
            {
                "action": "getScore",
                "params": {"startMeasure": 1, "endMeasure": 2},
            }
        ],
        source,
    )
    bar_1, bar_2 = bars_of(entry["result"])

    assert ties(bar_1[0]) == {
        60: (True, False),
        64: (True, False),
        67: (False, False),
    }
    assert ties(bar_1[1]) == {
        60: (False, True),
        64: (False, True),
        69: (False, False),
    }
    assert ties(bar_1[2]) == {62: (True, False)}
    assert ties(bar_2[0]) == {62: (False, True)}
    assert [e["isTie"] for e in bar_1 + bar_2] == [True, False, True, False]


def test_add_tie_partial_chord_then_across_the_barline(tmp_path):
    source = tie_score(
        tmp_path,
        xml_chord("quarter", 60, 64, 67)
        + xml_chord("quarter", 60, 64, 69)
        + xml_chord("half", 62),
        xml_chord("whole", 62),
    )
    results = run(
        [
            {
                "action": "addTie",
                "params": {"pitches": [60, 64]},
            },  # the cursor starts on the first chord
            {
                "action": "nextElement",
                "params": {},
            },  # addTie left the cursor on C-E-A; move on to the D
            {"action": "addTie", "params": {}},
            {
                "action": "getScore",
                "params": {"startMeasure": 1, "endMeasure": 2},
            },
        ],
        source,
    )
    partial, _, across, score = (r["result"] for r in results)
    assert (partial["tiedPitches"], partial["skippedPitches"]) == ([60, 64], [])
    assert across["tiedPitches"] == [62]
    bar_1, bar_2 = bars_of(score)
    assert ties(bar_1[0]) == {
        60: (True, False),
        64: (True, False),
        67: (False, False),
    }
    assert ties(bar_1[1]) == {
        60: (False, True),
        64: (False, True),
        69: (False, False),
    }
    assert ties(bar_1[2]) == {62: (True, False)} and ties(bar_2[0]) == {
        62: (False, True)
    }
    assert [e["durationTicks"] for e in bar_1 + bar_2] == [
        480,
        480,
        960,
        1920,
    ]  # no notes inserted


def test_add_tie_default_pitches_skip_the_ones_not_in_the_next_chord(tmp_path):
    source = tie_score(
        tmp_path,
        xml_chord("quarter", 60, 64, 67)
        + xml_chord("quarter", 60, 64, 69)
        + xml_chord("half", 62),
    )
    added, score = (
        r["result"]
        for r in run(
            [
                {"action": "addTie", "params": {}},
                {
                    "action": "getScore",
                    "params": {"startMeasure": 1, "endMeasure": 1},
                },
            ],
            source,
        )
    )
    assert (added["tiedPitches"], added["skippedPitches"]) == ([60, 64], [67])
    (bar,) = bars_of(score)
    assert ties(bar[0]) == {
        60: (True, False),
        64: (True, False),
        67: (False, False),
    }


def test_add_tie_chain(tmp_path):
    source = tie_score(tmp_path, xml_chord("quarter", 60) * 4)
    results = run(
        [{"action": "addTie", "params": {}}] * 3
        + [
            {
                "action": "getScore",
                "params": {"startMeasure": 1, "endMeasure": 1},
            }
        ],
        source,
    )
    (bar,) = bars_of(results[-1]["result"])
    assert [ties(e)[60] for e in bar] == [
        (True, False),
        (True, True),
        (True, True),
        (False, True),
    ]
    # Each addTie reports the chord it moved the cursor to: the one it tied to
    assert [
        r["result"]["currentSelection"]["startTick"] for r in results[:3]
    ] == [480, 960, 1440]
    (reported,) = results[0]["result"]["currentSelection"]["elements"]["staff0"]
    assert ties(reported) == {
        60: (False, True)
    }  # the reported chord already shows its tie back


def test_add_tie_errors_leave_the_music_unchanged(tmp_path):
    """add_tie errors leave the music unchanged.

    MuseScore's tie command would insert a new tied note here and overwrite the
    next one.
    """
    rest = "<Rest><durationType>quarter</durationType></Rest>"
    source = tie_score(
        tmp_path,
        xml_chord("quarter", 60)
        + xml_chord("quarter", 62)
        + xml_chord("quarter", 64)
        + rest,
    )
    results = run(
        [
            {"action": "addTie", "params": {}},  # C, then D: no matching pitch
            {
                "action": "addTie",
                "params": {"pitches": [62]},
            },  # D is not in the chord at the cursor
            {"action": "nextElement", "params": {"numElements": 2}},
            {"action": "addTie", "params": {}},  # E, then a rest
            {
                "action": "getScore",
                "params": {"startMeasure": 1, "endMeasure": 1},
            },
        ],
        source,
    )
    no_match, not_in_chord, _, before_rest, score = (
        r["result"] for r in results
    )
    assert no_match["error"].startswith(
        "No pitch to tie: the chord at the cursor has [60], the next chord has [62]"
    )
    assert "requested [62]" in not_in_chord["error"]
    assert "rest" in before_rest["error"]
    (bar,) = bars_of(score)
    assert [(e["name"], e["durationTicks"]) for e in bar] == [
        ("Chord", 480)
    ] * 3 + [("Rest", 480)]
    assert not any(e["isTie"] for e in bar)


REST_BAR = (
    "<Rest><durationType>measure</durationType><duration>4/4</duration></Rest>"
)
QUARTER, EIGHTH, HALF = ({"numerator": 1, "denominator": d} for d in (4, 8, 2))


def add_note(pitch, duration=QUARTER, advance=True, add_to_chord=False):
    return {
        "action": "addNote",
        "params": {
            "pitch": pitch,
            "duration": duration,
            "advanceCursorAfterAction": advance,
            "addToChord": add_to_chord,
        },
    }


def add_tied_note(duration, advance=True, **params):
    return {
        "action": "addTiedNote",
        "params": {
            "duration": duration,
            "advanceCursorAfterAction": advance,
            **params,
        },
    }


def chord_c_e_g():
    return [
        add_note(60, advance=False),
        add_note(64, advance=False, add_to_chord=True),
        add_note(67, add_to_chord=True),
    ]


def test_add_tied_note_chain_after_add_note(tmp_path):
    results = run(
        [
            add_note(60),
            add_tied_note(EIGHTH),
            add_tied_note(EIGHTH),
            {
                "action": "getScore",
                "params": {"startMeasure": 1, "endMeasure": 1},
            },
        ],
        tie_score(tmp_path, REST_BAR, REST_BAR),
    )
    (bar,) = bars_of(results[-1]["result"])
    chords = [e for e in bar if e["name"] == "Chord"]
    assert [(e["durationTicks"], ties(e)[60]) for e in chords] == [
        (480, (True, False)),
        (240, (True, True)),
        (240, (False, True)),
    ]
    assert [
        r["result"]["currentSelection"]["startTick"] for r in results[1:3]
    ] == [720, 960]  # after each new note


def test_add_tied_note_partial_chord_with_an_extra_pitch(tmp_path):
    """A tied chord with an extra pitch writes that pitch first.

    C-E-G into C-E-A: the A is written with the chord, before the tie (see the
    next test for why).
    """
    results = run(
        chord_c_e_g()
        + [
            add_tied_note(QUARTER, pitches=[60, 64], extraPitches=[69]),
            {
                "action": "getScore",
                "params": {"startMeasure": 1, "endMeasure": 1},
            },
        ],
        tie_score(tmp_path, REST_BAR, REST_BAR),
    )
    added = results[-2]["result"]
    assert (
        added["tiedPitches"] == [60, 64]
        and added["currentSelection"]["startTick"] == 960
    )
    (bar,) = bars_of(results[-1]["result"])
    assert ties(bar[0]) == {
        60: (True, False),
        64: (True, False),
        67: (False, False),
    }
    assert ties(bar[1]) == {
        60: (False, True),
        64: (False, True),
        69: (False, False),
    }


def test_add_to_chord_after_a_tie_extends_the_tied_chord(tmp_path):
    """A pitch added to the second of two tied chords is added to the first too.

    MuseScore treats tied chords as one: a pitch added to the second chord is
    added, tied, to the first too.

    This is why add_tied_note takes extraPitches, and why add_tie should be used
    once both chords are complete.
    """
    results = run(
        chord_c_e_g()
        + [
            add_tied_note(QUARTER, advance=False, pitches=[60, 64]),
            add_note(69, add_to_chord=True),
            {
                "action": "getScore",
                "params": {"startMeasure": 1, "endMeasure": 1},
            },
        ],
        tie_score(tmp_path, REST_BAR, REST_BAR),
    )
    (bar,) = bars_of(results[-1]["result"])
    assert ties(bar[0]) == {
        60: (True, False),
        64: (True, False),
        67: (False, False),
        69: (True, False),
    }
    assert ties(bar[1]) == {
        60: (False, True),
        64: (False, True),
        69: (False, True),
    }


def test_add_tied_note_longer_than_the_rest_of_the_bar(tmp_path):
    """A tied note longer than the rest of the bar is split.

    MuseScore splits the note at the barline into tied notes; the cursor skips
    both parts.
    """
    results = run(
        [
            add_note(62),
            add_note(62),
            add_note(60),
            add_tied_note(HALF),
            add_note(64),
            {
                "action": "getScore",
                "params": {"startMeasure": 1, "endMeasure": 2},
            },
        ],
        tie_score(tmp_path, REST_BAR, REST_BAR),
    )
    assert results[3]["result"]["currentSelection"]["startTick"] == 2400
    bar_1, bar_2 = bars_of(results[-1]["result"])
    assert [(e["startTick"], ties(e)) for e in bar_1[2:]] == [
        (960, {60: (True, False)}),
        (1440, {60: (True, True)}),
    ]
    assert [(e["startTick"], ties(e)) for e in bar_2[:2]] == [
        (1920, {60: (False, True)}),
        (2400, {64: (False, False)}),
    ]


def test_add_tied_note_errors_write_nothing(tmp_path):
    rest = {
        "action": "addRest",
        "params": {"duration": QUARTER, "advanceCursorAfterAction": True},
    }
    results = run(
        [
            add_tied_note(QUARTER),  # nothing before the cursor
            add_note(60),
            rest,
            add_tied_note(QUARTER),  # a rest before the cursor
            add_note(64),
            add_tied_note(
                QUARTER, pitches=[62]
            ),  # D is not in the chord before
            {
                "action": "getScore",
                "params": {"startMeasure": 1, "endMeasure": 1},
            },
        ],
        tie_score(tmp_path, REST_BAR, REST_BAR),
    )
    errors = [
        r["result"].get("error", "")
        for r in results
        if r["action"] == "addTiedNote"
    ]
    assert (
        errors[0]
        == errors[1]
        == "No note or chord before the cursor to tie from"
    )
    assert errors[2].startswith(
        "Pitch 62 is not in the chord before the cursor [64]"
    )
    (bar,) = bars_of(results[-1]["result"])
    assert [(e["name"], e["durationTicks"]) for e in bar] == [
        ("Chord", 480),
        ("Rest", 480),
        ("Chord", 480),
        ("Rest", 480),
    ]
    assert not any(e["isTie"] for e in bar)


def test_add_note_reports_the_position_after_the_note(tmp_path):
    results = run(
        [
            {"action": "goToMeasure", "params": {"measure": 1}},
            add_note(60),
            add_note(62, advance=False),
        ],
        tie_score(tmp_path, REST_BAR, REST_BAR),
    )
    assert results[1]["result"]["currentSelection"]["startTick"] == 480
    # Without advancing, the cursor stays on the note it wrote
    assert results[2]["result"]["currentSelection"]["startTick"] == 480


def test_a_sequence_of_notes_reports_the_position_after_the_last(tmp_path):
    (result,) = run(
        [
            {
                "action": "processSequence",
                "params": {
                    "sequence": [
                        {"action": "goToMeasure", "params": {"measure": 1}},
                        add_note(60),
                        add_note(62),
                    ]
                },
            }
        ],
        tie_score(tmp_path, REST_BAR, REST_BAR),
    )
    assert result["result"]["currentSelection"]["startTick"] == 960


def test_add_note_across_the_barline_moves_past_the_tied_part(tmp_path):
    results = run(
        [
            {"action": "goToMeasure", "params": {"measure": 1}},
            add_note(60),
            add_note(62),
            add_note(64),
            add_note(65, HALF),  # beat 4: split into two tied quarters
            add_note(67),
            get_measures(1, 2),
        ],
        tie_score(tmp_path, REST_BAR, REST_BAR),
    )
    assert results[4]["result"]["currentSelection"]["startTick"] == 2400
    first, second = bars_of(results[-1]["result"])
    # The tied quarter of the F is kept; the G follows it
    assert [(e["name"], e["durationTicks"]) for e in second[:2]] == [
        ("Chord", 480),
        ("Chord", 480),
    ]
    assert [n["pitchMidi"] for e in second[:2] for n in e["notes"]] == [65, 67]


def test_add_note_at_the_end_of_the_score_appends_a_bar(tmp_path):
    results = run(
        [
            {"action": "goToMeasure", "params": {"measure": 1}},
            add_note(60, {"numerator": 1, "denominator": 1}),
            add_note(62, {"numerator": 1, "denominator": 1}),
            get_measures(1, 2),
        ],
        tie_score(tmp_path, REST_BAR),
    )
    assert results[1]["result"]["currentSelection"]["startTick"] == 1920
    pitches = [
        [
            n["pitchMidi"]
            for e in bar
            if e["name"] == "Chord"
            for n in e["notes"]
        ]
        for bar in bars_of(results[-1]["result"])
    ]
    assert pitches == [[60], [62]]


def add_tuplet(advance):
    return {
        "action": "addTuplet",
        "params": {
            "duration": QUARTER,
            "ratio": {"numerator": 3, "denominator": 2},
            "advanceCursorAfterAction": advance,
        },
    }


def test_a_tuplet_is_filled_from_its_first_slot(tmp_path):
    results = run(
        [
            {"action": "goToMeasure", "params": {"measure": 1}},
            add_tuplet(advance=False),
            add_note(60, EIGHTH),
            add_note(62, EIGHTH),
            add_note(64, EIGHTH),
            get_measures(1, 1),
        ],
        tie_score(tmp_path, REST_BAR),
    )
    assert results[1]["result"]["currentSelection"]["startTick"] == 0
    assert results[4]["result"]["currentSelection"]["startTick"] == 480
    (bar,) = bars_of(results[-1]["result"])
    chords = [e for e in bar if e["name"] == "Chord"]
    assert [(e["startTick"], e["durationTicks"]) for e in chords] == [
        (0, 160),
        (160, 160),
        (320, 160),
    ]
    assert all(e["isTuplet"] for e in chords)


def test_advancing_past_a_tuplet_moves_after_it(tmp_path):
    results = run(
        [
            {"action": "goToMeasure", "params": {"measure": 1}},
            add_tuplet(advance=True),
        ],
        tie_score(tmp_path, REST_BAR),
    )
    assert results[1]["result"]["currentSelection"]["startTick"] == 480


def test_a_tuplet_reports_its_ratio_and_written_value(tmp_path):
    from src.utils.lilypond_converter import process_element

    for actual, written in ((5, "r16*4/5"), (7, "r16*4/7")):
        results = run(
            [
                {"action": "goToMeasure", "params": {"measure": 1}},
                {
                    "action": "addTuplet",
                    "params": {
                        "duration": QUARTER,
                        "ratio": {"numerator": actual, "denominator": 4},
                        "advanceCursorAfterAction": False,
                    },
                },
                get_measures(1, 1),
            ],
            tie_score(tmp_path, REST_BAR),
        )
        (bar,) = bars_of(results[-1]["result"])
        first = bar[0]
        assert first["tuplet"] == {
            "actual": actual,
            "normal": 4,
            "writtenTicks": 120,
        }
        assert process_element(first) == written


def tuplet_step(actual, normal, numerator, denominator):
    return {
        "action": "addTuplet",
        "params": {
            "duration": {"numerator": numerator, "denominator": denominator},
            "ratio": {"numerator": actual, "denominator": normal},
            "advanceCursorAfterAction": False,
        },
    }


@pytest.mark.parametrize("actual", [3, 5, 6, 7])
def test_a_tuplet_is_filled_note_by_note(tmp_path, actual):
    from src.utils.lilypond_converter import process_element

    sixteenth = {"numerator": 1, "denominator": 16}
    # A triplet of 16ths fills an eighth; the others fill a quarter
    span = (1, 8) if actual == 3 else (1, 4)
    normal = 2 if actual == 3 else 4
    results = run(
        [
            {"action": "goToMeasure", "params": {"measure": 1}},
            tuplet_step(actual, normal, *span),
        ]
        + [add_note(60 + i, sixteenth) for i in range(actual)]
        + [get_measures(1, 1)],
        tie_score(tmp_path, REST_BAR),
    )
    (bar,) = bars_of(results[-1]["result"])
    written = [process_element(e) for e in bar if "tuplet" in e]
    pitches = [n["pitchMidi"] for e in bar if "tuplet" in e for n in e["notes"]]
    assert pitches == [60 + i for i in range(actual)]
    assert all(w.endswith(f"16*{normal}/{actual}") for w in written)


@pytest.mark.xfail(
    strict=True,
    reason="B20: inside a nested tuplet a slot can start between two ticks "
    "(53 1/3); the cursor is kept in whole ticks, so the next note lands on "
    "the slot before it and overwrites it",
)
def test_notes_in_a_tuplet_inside_a_tuplet_get_both_ratios(tmp_path):
    from src.utils.lilypond_converter import process_element

    sixteenth = {"numerator": 1, "denominator": 16}
    results = run(
        [
            {"action": "goToMeasure", "params": {"measure": 1}},
            tuplet_step(3, 2, 1, 4),  # a triplet of eighths on beat 1
            tuplet_step(3, 2, 1, 8),  # a triplet of 16ths in its first slot
            add_note(60, sixteenth),
            add_note(62, sixteenth),
            add_note(64, sixteenth),
            add_note(65, EIGHTH),  # back in the outer triplet
            add_note(67, EIGHTH),
            add_note(69),  # after both tuplets
            get_measures(1, 1),
        ],
        tie_score(tmp_path, REST_BAR),
    )
    (bar,) = bars_of(results[-1]["result"])
    assert [process_element(e) for e in bar] == [
        "c'16*4/9",
        "d'16*4/9",
        "e'16*4/9",
        "f'8*2/3",
        "g'8*2/3",
        "a'4",
        "r2",
    ]


@pytest.mark.parametrize(
    "steps, ratio, first",
    [
        (  # a quintuplet of 16ths in the first slot of a triplet of quarters
            [tuplet_step(3, 2, 1, 2), tuplet_step(5, 4, 1, 4)],
            (15, 8),
            "r16*8/15",
        ),
        (  # a triplet of 16ths in the first slot of a quintuplet of eighths
            [tuplet_step(5, 4, 1, 2), tuplet_step(3, 2, 1, 8)],
            (15, 8),
            "r16*8/15",
        ),
        (  # three triplets inside each other
            [
                tuplet_step(3, 2, 1, 2),
                tuplet_step(3, 2, 1, 4),
                tuplet_step(3, 2, 1, 8),
            ],
            (27, 8),
            "r16*8/27",
        ),
        (  # a duplet: two eighths in the time of a dotted quarter
            [tuplet_step(2, 3, 3, 8)],
            (2, 3),
            "r8*3/2",
        ),
    ],
)
def test_tuplets_report_their_combined_ratio(tmp_path, steps, ratio, first):
    from src.utils.lilypond_converter import process_element

    results = run(
        [{"action": "goToMeasure", "params": {"measure": 1}}]
        + steps
        + [get_measures(1, 1)],
        tie_score(tmp_path, REST_BAR),
    )
    (bar,) = bars_of(results[-1]["result"])
    tuplet = bar[0]["tuplet"]
    assert (tuplet["actual"], tuplet["normal"]) == ratio
    assert process_element(bar[0]) == first


def test_next_element_reports_where_it_moved(tmp_path):
    results = run(
        [
            {"action": "goToMeasure", "params": {"measure": 2}},
            {"action": "nextElement", "params": {}},
        ],
        tie_score(
            tmp_path,
            REST_BAR,
            xml_chord("half", 60) + xml_chord("half", 64),
            REST_BAR,
        ),
    )
    assert results[1]["result"]["currentSelection"]["startTick"] == 1920 + 960


def get_measures(start=1, end=4):
    return {
        "action": "getScore",
        "params": {"startMeasure": start, "endMeasure": end},
    }


def test_musescore_knows_every_action_name_the_plugin_uses(tmp_path):
    """Every cmd() name in the plugin is an action MuseScore knows.

    cmd() with an unknown name does nothing and returns no error; MuseScore only
    logs it, and run() fails on that log line. The names are read from the
    plugin, so a new cmd() call is checked too. A made-up name first shows that
    the check sees refusals. Undo was broken this way: MuseScore 4.7 renamed
    "undo" to "action://notation/undo".
    """
    import re

    from dev.plugin_harness import GUI_ONLY_ACTIONS, PLUGIN

    code = [
        line
        for line in PLUGIN.read_text().splitlines()
        if not line.strip().startswith("//")
    ]
    names = sorted(
        set(re.findall(r'\bcmd\("([^"]+)"\)', "\n".join(code)))
        - GUI_ONLY_ACTIONS
    )
    assert "action://notation/undo" in names and "tie" in names
    score = tie_score(tmp_path, REST_BAR, REST_BAR)

    def probe(name):
        return {"action": "harnessCmd", "params": {"name": name}}

    # The names are asked for out of context (undo with nothing to undo, delete
    # without a selection), so MuseScore may not run them: only unknown names fail
    with pytest.raises(RuntimeError, match="harness-made-up-action"):
        run([probe("harness-made-up-action")], score, unknown_actions_only=True)
    results = run(
        [probe(name) for name in names], score, unknown_actions_only=True
    )
    assert all(r["result"].get("success") for r in results)


def test_undo_uses_an_action_musescore_knows(tmp_path):
    """The undo tool asks for an action MuseScore knows and runs.

    run() fails when MuseScore refuses the action. The undo itself never runs
    here: MuseScore's converter mode has no document window to undo in, so
    checking that the note is gone needs the GUI.
    """
    results = run(
        [add_note(60), {"action": "undo", "params": {}}],
        tie_score(tmp_path, REST_BAR, REST_BAR),
    )
    assert results[1]["result"].get("success")


def test_append_measure_adds_measures_at_the_end(tmp_path):
    results = run(
        [
            {"action": "appendMeasure", "params": {}},
            {"action": "appendMeasure", "params": {"count": 2}},
            get_measures(),
        ],
        tie_score(tmp_path, REST_BAR, REST_BAR),
    )
    assert results[-1]["result"]["analysis"]["numMeasures"] == 5


def test_insert_measure_goes_before_the_selected_measure(tmp_path):
    # Bar 2 is the score's last bar, which the selection used to leave out
    results = run(
        [
            {"action": "goToMeasure", "params": {"measure": 2}},
            {"action": "insertMeasure", "params": {}},
            get_measures(),
        ],
        tie_score(tmp_path, REST_BAR, xml_chord("whole", 60)),
    )
    analysis = results[-1]["result"]["analysis"]
    assert analysis["numMeasures"] == 3
    # The C that was in bar 2 is in bar 3 now; the new bar 2 is empty
    pitches = [
        [
            n["pitchMidi"]
            for e in bar
            if e["name"] == "Chord"
            for n in e["notes"]
        ]
        for bar in bars_of(results[-1]["result"])
    ]
    assert pitches == [[], [], [60]]


def test_delete_selection_turns_the_notes_into_rests(tmp_path):
    results = run(
        [
            {
                "action": "selectMeasures",
                "params": {"startMeasure": 1, "endMeasure": 1},
            },
            {"action": "deleteSelection", "params": {}},
            get_measures(1, 2),
        ],
        tie_score(
            tmp_path, xml_chord("half", 60) + xml_chord("half", 64), REST_BAR
        ),
    )
    first, second = bars_of(results[-1]["result"])
    assert first and all(e["name"] == "Rest" for e in first)


def test_delete_selection_after_go_to_measure(tmp_path):
    results = run(
        [
            {"action": "goToMeasure", "params": {"measure": 2}},
            {"action": "deleteSelection", "params": {}},
            get_measures(1, 2),
        ],
        tie_score(tmp_path, REST_BAR, xml_chord("whole", 60)),
    )
    first, second = bars_of(results[-1]["result"])
    assert second and all(e["name"] == "Rest" for e in second)


def test_delete_measures_removes_the_last_bar(tmp_path):
    results = run(
        [
            {
                "action": "deleteMeasures",
                "params": {"startMeasure": 2, "endMeasure": 2},
            },
            get_measures(1, 2),
        ],
        tie_score(tmp_path, xml_chord("whole", 60), xml_chord("whole", 62)),
    )
    assert results[-1]["result"]["analysis"]["numMeasures"] == 1


def test_a_custom_range_up_to_the_end_of_the_score_can_be_deleted(tmp_path):
    results = run(
        [
            {
                "action": "selectCustomRange",
                "params": {
                    "startTick": 1920,
                    "endTick": 3840,
                    "startStaff": 0,
                    "endStaff": 1,
                },
            },
            {"action": "deleteSelection", "params": {}},
            get_measures(1, 2),
        ],
        tie_score(tmp_path, xml_chord("whole", 60), xml_chord("whole", 62)),
    )
    first, second = bars_of(results[-1]["result"])
    assert second and all(e["name"] == "Rest" for e in second)


def test_next_element_onto_the_last_note_appends_a_measure(tmp_path):
    results = run(
        [
            {"action": "goToMeasure", "params": {"measure": 2}},
            {"action": "nextElement", "params": {}},
            get_measures(),
        ],
        tie_score(
            tmp_path, REST_BAR, xml_chord("half", 60) + xml_chord("half", 64)
        ),
    )
    assert results[1]["result"].get("success")
    assert results[-1]["result"]["analysis"]["numMeasures"] == 3


def test_element_steps_past_the_start_or_end_of_the_score_are_errors(
    tmp_path,
):
    results = run(
        [
            {"action": "goToBeginningOfScore", "params": {}},
            {"action": "prevElement", "params": {}},
            {"action": "goToFinalMeasure", "params": {}},
            {"action": "nextElement", "params": {}},
        ],
        tie_score(tmp_path, REST_BAR, xml_chord("whole", 60)),
    )
    assert "Beginning of score" in results[1]["result"]["error"]
    assert "End of score" in results[3]["result"]["error"]


def test_go_to_final_measure_selects_the_whole_last_bar(tmp_path):
    results = run(
        [
            {"action": "goToFinalMeasure", "params": {}},
            {"action": "deleteSelection", "params": {}},
            get_measures(1, 2),
        ],
        tie_score(
            tmp_path,
            REST_BAR,
            xml_chord("half", 60) + xml_chord("half", 62),
        ),
    )
    selection = results[0]["result"]["currentSelection"]
    assert (selection["startTick"], selection["totalDuration"]) == (1920, 1920)
    first, second = bars_of(results[-1]["result"])
    assert second and all(e["name"] == "Rest" for e in second)


def test_go_to_final_measure_in_a_one_bar_score(tmp_path):
    (result,) = run(
        [{"action": "goToFinalMeasure", "params": {}}],
        tie_score(tmp_path, xml_chord("whole", 60)),
    )
    assert result["result"]["currentSelection"]["startTick"] == 0


def test_style_keys_are_checked_and_read_back():
    results = run(
        [
            {
                "action": "setStyle",
                "params": {"key": "createMultiMeasureRests", "value": True},
            },
            {
                "action": "setStyle",
                "params": {"key": "useGermanNoteNames", "value": True},
            },
            {
                "action": "getStyle",
                "params": {
                    "keys": ["createMultiMeasureRests", "useGermanNoteNames"]
                },
            },
        ],
        JAZZ,
    )
    assert results[0]["result"]["value"] is True
    assert results[1]["result"] == {
        "error": "Unknown style key: useGermanNoteNames"
    }
    assert results[2]["result"]["styles"] == {"createMultiMeasureRests": True}
    assert results[2]["result"]["unknown"] == ["useGermanNoteNames"]


def test_a_failing_step_stops_a_sequence():
    results = run(
        [
            {
                "action": "processSequence",
                "params": {
                    "sequence": [
                        {
                            "action": "setStyle",
                            "params": {"key": "nope", "value": 1},
                        },
                        {"action": "appendMeasure", "params": {}},
                    ]
                },
            },
            {
                "action": "getScore",
                "params": {"startMeasure": 1, "includeElements": False},
            },
        ],
        JAZZ,
    )
    assert results[0]["result"] == {
        "error": "Step 1 of 2 (setStyle) failed: Unknown style key: nope. "
        "No step was applied."
    }
    before = run(
        [
            {
                "action": "getScore",
                "params": {"startMeasure": 1, "includeElements": False},
            }
        ],
        JAZZ,
    )
    assert (
        results[1]["result"]["analysis"]["numMeasures"]
        == before[0]["result"]["analysis"]["numMeasures"]
    )


def measure_elements_score(tmp_path):
    """Write a 3-bar score with a Coda, a D.S. al Coda jump and a line break."""
    rest = "<Rest><durationType>measure</durationType><duration>4/4</duration></Rest>"
    coda = (
        "<Marker><markerType>codab</markerType><style>repeat_left</style><text><sym>coda</sym></text>"
        "<label>codab</label></Marker>"
    )
    jump = (
        "<Jump><style>repeat_right</style><text>D.S. al Coda</text>"
        "<jumpTo>segno</jumpTo><playUntil>coda</playUntil>"
        "<continueAt>codab</continueAt></Jump>"
    )
    line_break = "<LayoutBreak><subtype>line</subtype></LayoutBreak>"
    timesig = "<TimeSig><sigN>4</sigN><sigD>4</sigD></TimeSig>"
    measures = (
        f"<Measure><voice>{timesig}{rest}</voice></Measure>"
        f"<Measure>{jump}<voice>{rest}</voice>{line_break}</Measure>"
        f"<Measure>{coda}<voice>{rest}</voice></Measure>"
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?><museScore version="4.70"><Score>'
        '<Part id="1"><Staff id="1"/><trackName>Piano</trackName></Part>'
        f'<Staff id="1">{measures}</Staff></Score></museScore>'
    )
    path = tmp_path / "markers.mscx"
    path.write_text(xml)
    return path


def test_score_reading_lists_markers_jumps_and_breaks(tmp_path):
    (result,) = run(
        [{"action": "getScore", "params": {"startMeasure": 1}}],
        measure_elements_score(tmp_path),
    )
    measures = result["result"]["analysis"]["measures"]
    assert [m["measureElements"] for m in measures] == [
        [],
        [
            {"name": "Jump", "text": "D.S. al Coda"},
            {"name": "LayoutBreak", "text": "System break"},
        ],
        [{"name": "Marker", "text": "Coda"}],
    ]


def rest_score(tmp_path, bars):
    """Write a score of `bars` whole-bar rests in 4/4, on one staff."""
    rest = "<Rest><durationType>measure</durationType><duration>4/4</duration></Rest>"
    timesig = "<TimeSig><sigN>4</sigN><sigD>4</sigD></TimeSig>"
    measures = f"<Measure><voice>{timesig}{rest}</voice></Measure>" + (
        f"<Measure><voice>{rest}</voice></Measure>" * (bars - 1)
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?><museScore version="4.70"><Score>'
        '<Part id="1"><Staff id="1"/><trackName>Piano</trackName></Part>'
        f'<Staff id="1">{measures}</Staff></Score></museScore>'
    )
    path = tmp_path / "rests.mscx"
    path.write_text(xml)
    return path


def add_marker(measure, marker):
    return {
        "action": "addMarker",
        "params": {"measure": measure, "marker": marker},
    }


def markers_and_jumps(get_score_result):
    return [
        [
            e["text"]
            for e in m["measureElements"]
            if e["name"] in ("Marker", "Jump")
        ]
        for m in get_score_result["result"]["analysis"]["measures"]
    ]


def test_markers_and_jumps_are_added_and_removed(tmp_path):
    get_score = {"action": "getScore", "params": {"startMeasure": 1}}
    results = run(
        [
            add_marker(2, "ds_al_coda"),
            add_marker(1, "segno"),
            add_marker(2, "to_coda"),
            add_marker(3, "coda"),
            add_marker(3, "coda"),
            add_marker(4, "dc_al_fine"),
            add_marker(4, "fine"),
            add_marker(5, "dc"),
            add_marker(6, "dc_al_coda"),
            add_marker(7, "ds"),
            add_marker(8, "ds_al_fine"),
            get_score,
            {
                "action": "removeAnnotations",
                "params": {
                    "startMeasure": 1,
                    "endMeasure": 4,
                    "kinds": ["markers"],
                },
            },
            {
                "action": "removeAnnotations",
                "params": {
                    "startMeasure": 1,
                    "endMeasure": 8,
                    "kinds": ["jumps"],
                },
            },
            get_score,
        ],
        rest_score(tmp_path, 8),
    )
    replies = [r.get("result", r) for r in results]
    # MuseScore's name for the jump's type, which it derives from jumpTo, playUntil and continueAt
    assert [r.get("added") for r in replies[:11]] == [
        "D.S. al Coda",
        "Segno",
        "To coda",
        "Coda",
        None,
        "Da Capo al Fine",
        "Fine",
        "Da Capo",
        "Da Capo al Coda",
        "D.S.",
        "D.S. al Fine",
    ]
    assert replies[0]["missing"] == ["Segno", "To Coda", "Coda"]
    assert "Measure 3 already has a Coda" in str(replies[4])
    assert replies[5]["missing"] == ["Fine"]
    assert replies[8]["missing"] == []
    assert markers_and_jumps(results[11]) == [
        ["Segno"],
        ["D.S. al Coda", "To coda"],
        ["Coda"],
        ["D.C. al Fine", "Fine"],
        ["D.C."],
        ["D.C. al Coda"],
        ["D.S."],
        ["D.S. al Fine"],
    ]
    assert replies[12]["removed"]["markers"] == 4
    assert replies[13]["removed"]["jumps"] == 6
    assert markers_and_jumps(results[14]) == [[]] * 8


def test_to_coda_is_added_as_a_symbol_and_counts_for_jumps(tmp_path):
    results = run(
        [
            add_marker(1, "segno"),
            add_marker(2, "to_coda_symbol"),
            add_marker(3, "coda"),
            add_marker(4, "ds_al_coda"),
            {"action": "getScore", "params": {"startMeasure": 1}},
        ],
        rest_score(tmp_path, 4),
    )
    replies = [r.get("result", r) for r in results]
    assert replies[1]["added"] == "To coda (symbol)"
    assert replies[3]["missing"] == []
    assert markers_and_jumps(results[4])[1] == ["To coda (symbol)"]


def beats_score(tmp_path):
    """Write 3 bars of quarter rests in 4/4; bar 2 starts with a half rest."""
    quarter = "<Rest><durationType>quarter</durationType></Rest>"
    half = "<Rest><durationType>half</durationType></Rest>"
    timesig = "<TimeSig><sigN>4</sigN><sigD>4</sigD></TimeSig>"
    measures = (
        f"<Measure><voice>{timesig}{quarter * 4}</voice></Measure>"
        f"<Measure><voice>{half}{quarter * 2}</voice></Measure>"
        f"<Measure><voice>{quarter * 4}</voice></Measure>"
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?><museScore version="4.70"><Score>'
        '<Part id="1"><Staff id="1"/><trackName>Piano</trackName></Part>'
        f'<Staff id="1">{measures}</Staff></Score></museScore>'
    )
    path = tmp_path / "beats.mscx"
    path.write_text(xml)
    return path


def chord_symbols(get_score_result):
    return [
        (m["measure"], mk["startTick"] - m["startTick"], mk["text"])
        for m in get_score_result["result"]["analysis"]["measures"]
        for mk in m["markings"]
        if mk["name"] == "Harmony"
    ]


def test_chord_symbols_are_set_moved_and_removed(tmp_path):
    def set_chord(measure, beat, chord):
        return {
            "action": "setChordSymbol",
            "params": {"measure": measure, "beat": beat, "chord": chord},
        }

    get_score = {"action": "getScore", "params": {"startMeasure": 1}}
    results = run(
        [
            set_chord(1, 1, "C"),
            set_chord(1, 3, "G7"),
            set_chord(1, 3, "G7sus4"),
            set_chord(2, 2, "F"),
            set_chord(2, 3, "F"),
            {
                "action": "moveChordSymbol",
                "params": {
                    "measure": 1,
                    "beat": 3,
                    "toMeasure": 3,
                    "toBeat": 1,
                },
            },
            get_score,
            {
                "action": "removeAnnotations",
                "params": {
                    "startMeasure": 1,
                    "endMeasure": 3,
                    "kinds": ["chord_symbols"],
                    "contains": "C",
                    "exact": True,
                },
            },
            get_score,
        ],
        beats_score(tmp_path),
    )
    replies = [r.get("result", r) for r in results]
    assert replies[1]["chord"] == "G7" and "replaced" not in replies[1]
    assert replies[2]["replaced"] == "G7"
    assert "No note or rest starts on beat 2 of measure 2" in str(replies[3])
    assert "beats 1, 3, 4" in str(replies[3])
    assert replies[5]["chord"] == "G7sus4"
    assert chord_symbols(results[6]) == [
        (1, 0, "C"),
        (2, 960, "F"),
        (3, 0, "G7sus4"),
    ]
    assert replies[7]["removed"]["chord_symbols"] == 1
    assert chord_symbols(results[8]) == [(2, 960, "F"), (3, 0, "G7sus4")]


IMPORTED_CHORD = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.1">
  <part-list><score-part id="P1"><part-name>Piano</part-name></score-part></part-list>
  <part id="P1">
    <measure number="1">
      <attributes><divisions>1</divisions><time><beats>4</beats><beat-type>4</beat-type></time>
        <clef><sign>G</sign><line>2</line></clef></attributes>
      <harmony><root><root-step>C</root-step></root><kind>major</kind></harmony>
      <note><rest/><duration>4</duration><type>whole</type></note>
    </measure>
    <measure number="2">
      <note><rest/><duration>2</duration><type>half</type></note>
      <harmony><root><root-step>F</root-step></root><kind>major</kind><offset>-1</offset></harmony>
      <note><rest/><duration>2</duration><type>half</type></note>
    </measure>
  </part>
</score-partwise>
"""


def test_an_imported_chord_symbol_is_not_moved_but_can_be_set(tmp_path):
    path = tmp_path / "imported.musicxml"
    path.write_text(IMPORTED_CHORD)
    results = run(
        [
            {
                "action": "moveChordSymbol",
                "params": {
                    "measure": 1,
                    "beat": 1,
                    "toMeasure": 2,
                    "toBeat": 1,
                },
            },
            {
                "action": "setChordSymbol",
                "params": {"measure": 1, "beat": 1, "chord": "Cmaj7"},
            },
            # On beat 2 of bar 2 no note or rest starts: MuseScore holds the chord symbol on a segment of its own
            {
                "action": "setChordSymbol",
                "params": {"measure": 2, "beat": 2, "chord": "F6"},
            },
            {"action": "getScore", "params": {"startMeasure": 1}},
        ],
        path,
    )
    assert "Ask the user" in str(results[0])
    assert results[1]["result"]["replaced"] == "(name not readable)"
    assert results[2]["result"]["replaced"] == "(name not readable)"
    assert chord_symbols(results[3]) == [(1, 0, "Cmaj7"), (2, 480, "F6")]


def test_an_imported_chord_symbol_is_removed_by_its_beat(tmp_path):
    path = tmp_path / "imported.musicxml"
    path.write_text(IMPORTED_CHORD)
    results = run(
        [
            # Bar 2's chord symbol is on beat 2, inside a half rest, on a segment of its own
            {
                "action": "removeAnnotations",
                "params": {
                    "startMeasure": 1,
                    "endMeasure": 2,
                    "kinds": ["chord_symbols"],
                    "beat": 2,
                },
            },
            {"action": "getScore", "params": {"startMeasure": 1}},
        ],
        path,
    )
    assert results[0]["result"]["removed"]["chord_symbols"] == 1
    assert chord_symbols(results[1]) == [(1, 0, "")]


def systems_of(reply):
    return [(s["firstMeasure"], s["lastMeasure"]) for s in reply["systems"]]


def test_measures_per_system_with_locks_then_breaks(tmp_path):
    def per_system(n, method="locks", start=1, end=12):
        return {
            "action": "setMeasuresPerSystem",
            "params": {
                "startMeasure": start,
                "endMeasure": end,
                "perSystem": n,
                "method": method,
            },
        }

    results = run(
        [
            per_system(4),
            per_system(3, "breaks"),
            {"action": "getScore", "params": {"startMeasure": 1}},
            per_system(0, "breaks"),
        ],
        rest_score(tmp_path, 12),
    )
    replies = [r.get("result", r) for r in results]
    assert systems_of(replies[0]) == [(1, 4), (5, 8), (9, 12)]
    assert systems_of(replies[1]) == [(1, 3), (4, 6), (7, 9), (10, 12)]
    breaks = [
        m["measure"]
        for m in replies[2]["analysis"]["measures"]
        if {"name": "LayoutBreak", "text": "System break"}
        in m["measureElements"]
    ]
    # No break after the score's last bar
    assert breaks == [3, 6, 9]
    assert replies[3]["removed_breaks"] == 3
    # Back to MuseScore's own layout: twelve empty bars fit on fewer systems
    assert len(replies[3]["systems"]) < 4


def test_breaks_are_added_once_and_removed(tmp_path):
    def add_break(measure, kind):
        return {
            "action": "addBreak",
            "params": {"measure": measure, "kind": kind},
        }

    get_score = {"action": "getScore", "params": {"startMeasure": 1}}
    results = run(
        [
            add_break(2, "line"),
            add_break(4, "page"),
            add_break(6, "section"),
            add_break(2, "line"),
            get_score,
            {
                "action": "removeAnnotations",
                "params": {
                    "startMeasure": 1,
                    "endMeasure": 4,
                    "kinds": ["breaks"],
                },
            },
            get_score,
        ],
        rest_score(tmp_path, 8),
    )
    replies = [r.get("result", r) for r in results]
    assert [r.get("added") for r in replies[:3]] == [
        "System break",
        "Page break",
        "Section break",
    ]
    assert "Measure 2 already has a System break" in str(replies[3])

    def breaks(get_score_result):
        return [
            (m["measure"], e["text"])
            for m in get_score_result["result"]["analysis"]["measures"]
            for e in m["measureElements"]
            if e["name"] == "LayoutBreak"
        ]

    assert breaks(results[4]) == [
        (2, "System break"),
        (4, "Page break"),
        (6, "Section break"),
    ]
    assert replies[5]["removed"]["breaks"] == 2
    assert breaks(results[6]) == [(6, "Section break")]


def test_elements_are_found_and_their_properties_set(tmp_path):
    def set_props(**params):
        return {
            "action": "setProperties",
            "params": {
                "startMeasure": 1,
                "endMeasure": 1,
                "kinds": ["chord_symbols"],
                **params,
            },
        }

    results = run(
        [
            {
                "action": "setChordSymbol",
                "params": {"measure": 1, "chord": "C"},
            },
            {
                "action": "setChordSymbol",
                "params": {"measure": 1, "beat": 3, "chord": "G7"},
            },
            {
                "action": "addMarker",
                "params": {"measure": 2, "marker": "to_coda"},
            },
            {"action": "addText", "params": {"measure": 3, "text": "cue"}},
            {
                "action": "findElements",
                "params": {"startMeasure": 1, "endMeasure": 3},
            },
            set_props(
                placement="below", align="left", fontSize=12, moveBy=[0.5, 1]
            ),
            set_props(
                contains="G7",
                exact=True,
                reset=["placement", "align", "fontSize", "offset"],
            ),
            set_props(contains="nothing like this", fontSize=9),
        ],
        beats_score(tmp_path),
    )
    found = results[4]["result"]["elements"]
    assert [
        (e["measure"], e.get("beat"), e["kind"], e["text"]) for e in found
    ] == [
        (1, 1, "chord_symbols", "C"),
        (1, 3, "chord_symbols", "G7"),
        (2, None, "markers", "To coda"),
        (3, 1, "texts", "cue"),
    ]
    # MuseScore 4.7's styles: chord symbols centred, To Coda right-aligned, staff text left-aligned
    assert [e["align"] for e in found] == ["center", "center", "right", "left"]
    assert found[0]["offset"] == [0, -2.5] and found[0]["fontSize"] == 10

    changed = results[5]["result"]["elements"]
    # Below the staff, MuseScore takes the style's offset for below, then moveBy is added to it
    assert [
        (e["placement"], e["align"], e["fontSize"], e["offset"])
        for e in changed
    ] == [
        ("below", "left", 12, [0.5, 4.5]),
        ("below", "left", 12, [0.5, 4.5]),
    ]
    (reset,) = results[6]["result"]["elements"]
    assert (
        reset["text"],
        reset["placement"],
        reset["align"],
        reset["fontSize"],
        reset["offset"],
    ) == (
        "G7",
        "above",
        "center",
        10,
        [0, -2.5],
    )
    assert "No elements match" in str(results[7])


def test_measure_stretch_widens_the_measure(tmp_path):
    def widths(render_result):
        boxes = render_result["result"]["measures"]
        return [b["width"] for b in boxes]

    results = run(
        [
            {
                "action": "renderScore",
                "params": {"path": str(tmp_path / "before")},
            },
            {
                "action": "setMeasureStretch",
                "params": {"startMeasure": 2, "endMeasure": 2, "stretch": 1.5},
            },
            {
                "action": "renderScore",
                "params": {"path": str(tmp_path / "after")},
            },
        ],
        beats_score(tmp_path),
    )
    assert results[1]["result"]["measures"] == [{"measure": 2, "stretch": 1.5}]
    before, after = widths(results[0]), widths(results[2])
    assert after[1] / after[0] > 1.2 * before[1] / before[0]


def test_rendered_score_and_measure_boxes_can_be_cropped(tmp_path):
    from src.render import boxes_from, crops, render_measures, render_whole_page

    base = tmp_path / "render"
    results = run(
        [
            {"action": "renderScore", "params": {"path": base.as_posix()}},
            {
                "action": "getScore",
                "params": {"startMeasure": 1, "includeElements": False},
            },
        ],
        JAZZ,
    )
    rendered = results[0]["result"]
    pdf = base.with_name("render.pdf")
    assert rendered["pages"] == 1 and pdf.exists()
    boxes = [b for b in boxes_from(rendered["measures"]) if b is not None]
    assert len(boxes) == results[1]["result"]["analysis"]["numMeasures"] == 8
    assert rendered["numbers"] == list(range(1, 9))
    # A4 is 120 × 170 staff spaces at the default spatium (1.75 mm).
    assert round(rendered["pageWidth"]) == 120
    assert round(rendered["pageHeight"]) == 170
    for box in boxes:
        assert box.page == 0
        assert 0 < box.x < box.x + box.width < rendered["pageWidth"]
        assert 0 < box.y < box.bottom < rendered["pageHeight"]
    # Bars 1-6 share the first system, bars 7-8 the second.
    assert len({b.y for b in boxes[:6]}) == 1 and boxes[6].y > boxes[0].y
    assert render_whole_page(pdf, 0).size == (1109, 1568)
    image = render_measures(pdf, rendered["pageWidth"], boxes, 2, 2)
    (crop,) = crops(boxes, 2, 2)
    scale = image.width / round(crop.region.width * 25)

    def ink_in_the_middle_of(box):
        x = int((box.x + box.width / 2 - crop.region.x) * 25 * scale)
        column = image.convert("L").crop((x, 0, x + 1, image.height))
        return min(column.tobytes()) < 128

    # Bar 2 stands where it does on its system; bar 1 before it is blank.
    assert ink_in_the_middle_of(boxes[1])
    assert not ink_in_the_middle_of(boxes[0])


def test_measures_inside_a_multi_measure_rest_have_no_box(tmp_path):
    from tests.test_rolls import chord, write_score

    rest = "<Rest><durationType>measure</durationType><duration>4/4</duration></Rest>"
    source = write_score(
        tmp_path, [chord("whole", 49)] + [rest] * 4 + [chord("whole", 38)]
    )
    results = run(
        [
            {
                "action": "setStyle",
                "params": {"key": "createMultiMeasureRests", "value": True},
            },
            {
                "action": "renderScore",
                "params": {"path": (tmp_path / "mm").as_posix()},
            },
        ],
        source,
    )
    measures = results[1]["result"]["measures"]
    assert len(measures) == 6
    assert measures[0] is not None and measures[5] is not None
    assert measures[1:5] == [None] * 4


def test_a_measure_content_box_takes_in_its_marker(tmp_path):
    (result,) = run(
        [
            {
                "action": "renderScore",
                "params": {"path": (tmp_path / "r").as_posix()},
            }
        ],
        measure_elements_score(tmp_path),
    )
    measures = result["result"]["measures"]
    for m in measures:
        c, n = m["content"], m["notes"]
        for outer, inner in ((c, n), (n, m)):
            assert outer["x"] <= inner["x"] and outer["y"] <= inner["y"]
            assert outer["x"] + outer["width"] >= inner["x"] + inner["width"]
            assert outer["y"] + outer["height"] >= inner["y"] + inner["height"]
    # Bar 3's Coda sign stands above the staff, so its content reaches higher;
    # the sign is not a note, so its notes box does not.
    assert measures[2]["content"]["y"] < measures[2]["y"] - 1
    assert measures[2]["notes"]["y"] > measures[2]["y"] - 1


def test_bar_numbers_tell_a_pickup_from_the_bars_after_it():
    results = run(
        [
            {
                "action": "setMeasureNumbering",
                "params": {"measure": 1, "excludeFromCount": True},
            },
            {"action": "barNumbers", "params": {}},
        ],
        JAZZ,
    )
    reply = results[1]["result"]
    assert reply["numbers"] == [1, 1, 2, 3, 4, 5, 6, 7]
    assert reply["excluded"] == [True] + [False] * 7
    # Each measure's start and beat length, for naming a tick's bar and beat
    assert reply["startTicks"][:3] == [0, 1440, 2880]
    assert reply["beatTicks"][:3] == [480, 480, 480]
