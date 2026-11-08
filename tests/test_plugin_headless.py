"""The real QML plugin, run headless in MuseScore (dev/plugin_harness.py). Skipped without MuseScore."""

import shutil
import zipfile
from pathlib import Path

import pytest

from dev.plugin_harness import find_musescore, run

JAZZ = Path(__file__).resolve().parent.parent / "examples" / "jazz piano" / "Jazz Piano.mscz"

pytestmark = pytest.mark.skipif(find_musescore() is None, reason="MuseScore not installed")


def results_by_action(results):
    return {entry["action"]: entry["result"] for entry in results}


def text_lines(path):
    with zipfile.ZipFile(path) as z:
        name = next(n for n in z.namelist() if n.endswith(".mscx") and "/" not in n)
        return z.read(name).decode("utf-8").count('<Spanner type="TextLine">')


def test_score_reading_reports_parts_and_ranges():
    results = results_by_action(run([
        {"action": "getScore", "params": {"startMeasure": 2, "endMeasure": 3, "staves": [1]}},
    ], JAZZ))
    analysis = results["getScore"]["analysis"]
    assert [m["measure"] for m in analysis["measures"]] == [2, 3]
    assert analysis["measures"][0]["durationTicks"] == 1440  # 3/4
    assert analysis["staves"] == [
        {**analysis["staves"][0], "index": 1, "partName": "Piano", "isDrums": False}
    ]
    assert analysis["measures"][0]["elements"]["staff1"]


def test_highlights_are_added_to_the_score(tmp_path):
    out = tmp_path / "out.mscz"
    results = results_by_action(run([
        {"action": "highlightNotes", "params": {"startMeasure": 1, "endMeasure": 1, "startStaff": 0, "endStaff": 1}},
        {"action": "highlightSymbols", "params": {"startMeasure": 1, "endMeasure": 1}},
        {"action": "addHighlight", "params": {"startMeasure": 2, "endMeasure": 2, "startStaff": 1, "endStaff": 2}},
    ], JAZZ, out=out))
    assert results["highlightNotes"]["boxes"] >= 1
    assert results["highlightSymbols"]["found"]["time_signatures"] == 2
    assert results["addHighlight"]["placedSegments"] == 1
    boxes = results["highlightNotes"]["boxes"] + results["highlightSymbols"]["boxes"] + 1
    assert text_lines(out) == 2 * boxes  # every line is stored with a start and an end tag


def test_clear_highlights_removes_them(tmp_path):
    out = tmp_path / "out.mscz"
    results = run([
        {"action": "highlightNotes", "params": {"startMeasure": 1, "endMeasure": 2, "startStaff": 0, "endStaff": 1}},
        {"action": "clearHighlights", "params": {"startMeasure": 1, "endMeasure": 2}},
    ], JAZZ, out=out)
    assert results[1]["result"]["removed"] == results[0]["result"]["boxes"]
    assert text_lines(out) == 0


def test_go_to_measure_moves_the_cursor_there():
    results = results_by_action(run([
        {"action": "goToMeasure", "params": {"measure": 3}},
        {"action": "setTimeSignature", "params": {"numerator": 2, "denominator": 4}},
        {"action": "getScore", "params": {"startMeasure": 1, "endMeasure": 3, "includeElements": False}},
    ], JAZZ))
    selection = results["goToMeasure"]["currentSelection"]
    assert selection["startTick"] == 2 * 1440  # bars 1-2 are in 3/4
    assert (selection["startStaff"], selection["endStaff"]) == (0, 2)
    measures = results["getScore"]["analysis"]["measures"]
    assert [m["durationTicks"] for m in measures] == [1440, 1440, 960]


def test_errors_come_back_as_results():
    (result,) = run([{"action": "colorRange", "params": {"startMeasure": 99}}], JAZZ)
    assert "Invalid measure range" in result["result"]["error"]


def test_bars_are_numbered_as_played():
    results = results_by_action(run([
        {"action": "setRepeatBarlines", "params": {"startMeasure": 2, "endMeasure": 3, "playCount": 3}},
        {"action": "numberAsPlayed", "params": {}},
        {"action": "getScore", "params": {"startMeasure": 1, "endMeasure": 6, "includeElements": False}},
    ], JAZZ))
    assert [(o["measure"], o["addToNumber"]) for o in results["numberAsPlayed"]["offsets"]] == [(4, 4)]
    measures = results["getScore"]["analysis"]["measures"]
    assert [m["number"] for m in measures] == [1, 2, 3, 8, 9, 10]
    assert measures[1]["repeatStart"] is True and measures[2]["repeatEnd"] == 3


def test_add_text_is_styled(tmp_path):
    out = tmp_path / "out.mscz"
    (entry,) = run([{"action": "addText", "params": {
        "measure": 2, "text": "Cue", "fontSize": 8, "italic": True, "color": "#9E9E9E", "placement": "below"}}],
        JAZZ, out=out)
    assert entry["result"]["success"]
    with zipfile.ZipFile(out) as z:
        name = next(n for n in z.namelist() if n.endswith(".mscx") and "/" not in n)
        xml = z.read(name).decode("utf-8")
    staff_text = xml[xml.index("<StaffText>"):xml.index("</StaffText>")]
    assert "<size>8</size>" in staff_text and "<italic>1</italic>" in staff_text
    assert '<color r="158" g="158" b="158"' in staff_text
    assert "<placement>below</placement>" in staff_text and "Cue" in staff_text


def test_added_texts_and_marks_can_be_removed():
    results = run([
        {"action": "setTempo", "params": {"bpm": 146, "measure": 1}},
        {"action": "addRehearsalMark", "params": {"measure": 2, "text": "Verse"}},
        {"action": "addText", "params": {"measure": 1, "text": "* crash on 1st time only", "fontSize": 8, "italic": True}},
        {"action": "addText", "params": {"measure": 3, "text": "**"}},
        {"action": "addLabel", "params": {"measure": 5, "text": "Groove x7"}},
        {"action": "addVolta", "params": {"startMeasure": 6, "endMeasure": 6}},
        {"action": "removeAnnotations", "params": {"startMeasure": 1, "endMeasure": 8, "kinds": ["texts"], "contains": "**"}},
        {"action": "removeAnnotations", "params": {
            "startMeasure": 1, "endMeasure": 8, "kinds": ["texts", "labels", "rehearsal_marks", "tempo", "voltas"]}},
        {"action": "getScore", "params": {"startMeasure": 1, "endMeasure": 8, "staves": [0]}},
    ], JAZZ)
    assert results[6]["result"]["removed"]["texts"] == 1
    assert results[7]["result"]["removed"] == {"texts": 1, "labels": 1, "rehearsal_marks": 1, "tempo": 1, "voltas": 1}
    assert not any(m["markings"] for m in results[8]["result"]["analysis"]["measures"])


def test_articulations_and_ghost_notes(tmp_path):
    out = tmp_path / "out.mscz"
    results = results_by_action(run([
        {"action": "addArticulation", "params": {"startMeasure": 1, "endMeasure": 1, "symbol": "half_open"}},
        {"action": "getScore", "params": {"startMeasure": 1, "endMeasure": 1, "staves": [0]}},
        {"action": "removeArticulations", "params": {"startMeasure": 1, "endMeasure": 1}},
        {"action": "ghostNotes", "params": {"startMeasure": 1, "endMeasure": 8, "mode": "list"}},
    ], JAZZ, out=out))
    assert results["addArticulation"]["added"] > 0
    chords = [e for e in results["getScore"]["analysis"]["measures"][0]["elements"]["staff0"] if e["name"] == "Chord"]
    assert all(e.get("articulations") == ["half_open"] for e in chords)
    assert results["removeArticulations"]["removed"] == results["addArticulation"]["added"]
    assert results["ghostNotes"] == {"success": True, "ghostNotes": 0, "bars": []}


def test_remove_parts_keeps_system_texts_of_the_removed_top_staff(tmp_path):
    """make_part_score(in_place=True) relies on MuseScore moving tempo/rehearsal marks/repeats to the kept staff."""
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
    results = results_by_action(run([{"action": "removeParts", "params": {"keepStaves": [3]}}], source, out=out))
    assert results["removeParts"]["numStaves"] == 1
    (staff,) = ScoreFile(out).staves()
    texts = lambda tag: ["".join(e.find("text").itertext()) for e in staff.iter(tag)]
    assert texts("RehearsalMark") == ["A", "B"] and "q = 90" in texts("Tempo")
    assert staff[0].tag == "VBox" and staff.findall("Measure")[1].find("startRepeat") is not None


def test_export_makes_a_musicxml_copy_without_saving(tmp_path):
    """make_part_score(in_place=True) backs up the full score this way (writeScore can't write .mscz in 4.7)."""
    export = tmp_path / "full.mxl"
    results = results_by_action(run([
        {"action": "exportScore", "params": {"path": str(export)}},
        {"action": "exportScore", "params": {"path": str(tmp_path / "full.mscz")}},
    ], JAZZ))
    assert results["exportScore"]["error"].startswith("MuseScore files cannot be exported")  # the last result wins
    with zipfile.ZipFile(export) as z:
        assert any(name.endswith(".xml") and "META-INF" not in name for name in z.namelist())


def test_coloring_includes_flams(tmp_path):
    """A flam is a grace note (acciaccatura) attached to the main chord: it takes the chord's colour."""
    from src.mscz import ScoreFile
    from tests.test_rolls import chord, write_score

    flam = "<Chord><acciaccatura/><durationType>eighth</durationType><Note><pitch>38</pitch><tpc>16</tpc></Note></Chord>"
    source = write_score(tmp_path, [flam + chord("quarter", 38) + chord("quarter", 36) * 3])
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    out = out_dir / "out.mscz"
    results = results_by_action(run([{"action": "colorRange", "params": {
        "startMeasure": 1, "endMeasure": 1, "endBeat": 1, "color": "#2ca02c"}}], source, out=out))
    assert results["colorRange"]["colored"] == 2  # the snare and its flam, not the kicks after beat 1
    chords = ScoreFile(out).staves()[0].find("Measure/voice").findall("Chord")
    grace, main, kick = chords[:3]
    assert grace.find("acciaccatura") is not None
    for colored in (grace, main):
        assert colored.find("Note/color").attrib == {"r": "44", "g": "160", "b": "44", "a": "255"}
    assert kick.find("Note/color") is None


def test_beam_over_rests_inside_dotted_quarter_groups(tmp_path):
    """12/8: a rest between two eighths of a dotted-quarter group is beamed over; a rest that starts or ends a
    group is not."""
    from src.mscz import ScoreFile
    from tests.test_rolls import chord, write_score

    rest = "<Rest><durationType>eighth</durationType></Rest>"
    hat, kick = chord("eighth", 42), chord("eighth", 36, 42)
    source = write_score(tmp_path, [kick + rest + hat + rest + hat + hat + kick + hat + hat + kick + hat + rest])
    source.write_text(source.read_text().replace("<sigN>4</sigN><sigD>4</sigD>", "<sigN>12</sigN><sigD>8</sigD>"))
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    out = out_dir / "out.mscz"
    results = results_by_action(run([{"action": "beamOverRests", "params": {"startMeasure": 1}}], source, out=out))
    assert results["beamOverRests"]["changed"] == 1
    rests = ScoreFile(out).staves()[0].find("Measure/voice").findall("Rest")
    assert [r.findtext("BeamMode") for r in rests] == ["mid", None, None]


def test_section_counts_sit_next_to_the_section_label(tmp_path):
    """A bold red count right of the rehearsal mark, placed by offset (autoplace off); running it again replaces
    it, and other staff texts (e.g. a "*" crash mark) stay."""
    from src.mscz import ScoreFile
    from tests.test_rolls import chord, write_score

    mark = "<RehearsalMark><text>Verse 1</text></RehearsalMark><StaffText><text>*</text></StaffText>"
    source = write_score(tmp_path, [mark + chord("quarter", 36, 42) * 4, chord("quarter", 36, 42) * 4])
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    out = out_dir / "out.mscz"
    beside = {"mode": "beside"}
    results = run([{"action": "addSectionCounts", "params": {"counts": [{"measure": 1, "text": "2x4+2"}], **beside}},
                   {"action": "addSectionCounts", "params": {"counts": [{"measure": 1, "text": "(3x4)"}], **beside}}],
                  source, out=out)
    assert [r["result"]["removed"] for r in results] == [0, 1]
    texts = ScoreFile(out).staves()[0].find("Measure/voice").findall("StaffText")
    plain = ["".join(t.find("text").itertext()) for t in texts]
    assert sorted(plain) == ["*", "3x4"]
    count = texts[plain.index("3x4")]
    assert count.findtext("autoplace") == "0" and count.find("offset") is not None
    assert count.findtext("bold") == "1" and count.find("color").attrib == {"r": "214", "g": "39", "b": "40", "a": "255"}


def test_section_counts_in_the_label_replace_counts_beside_it(tmp_path):
    from src.mscz import ScoreFile
    from tests.test_rolls import chord, write_score

    mark = "<RehearsalMark><text>Chorus 4</text></RehearsalMark>"
    stale = "<StaffText><bold>1</bold><text>4+2</text></StaffText>"  # a count left on another bar earlier
    source = write_score(tmp_path, [mark + chord("quarter", 36, 42) * 4, stale + chord("quarter", 36, 42) * 4])
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    out = out_dir / "out.mscz"
    run([{"action": "addSectionCounts", "params": {"counts": [{"measure": 1, "text": "4"}], "mode": "beside"}},
         {"action": "addSectionCounts", "params": {"counts": [{"measure": 1, "text": "2x4"}]}},
         {"action": "addSectionCounts", "params": {"counts": [{"measure": 1, "text": "(4+2)"}], "clearAll": True}}],
        source, out=out)
    staff = ScoreFile(out).staves()[0]
    assert "".join(staff.find("Measure/voice/RehearsalMark/text").itertext()) == "Chorus 4 (4+2)"
    assert not list(staff.iter("StaffText"))


def test_delete_measures_inside_a_multi_measure_rest(tmp_path):
    """With multi-measure rests on, deleting empty bars used to report success and delete nothing (seen live)."""
    from tests.test_rolls import chord, write_score

    rest = "<Rest><durationType>measure</durationType><duration>4/4</duration></Rest>"
    source = write_score(tmp_path, [chord("whole", 49)] + [rest] * 4 + [chord("whole", 38)])
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    results = results_by_action(run([
        {"action": "setStyle", "params": {"key": "createMultiMeasureRests", "value": True}},
        {"action": "deleteMeasures", "params": {"startMeasure": 3, "endMeasure": 4}},
        {"action": "getScore", "params": {"startMeasure": 1, "endMeasure": 1, "includeElements": False}},
    ], source, out=out_dir / "out.mscz"))
    assert results["deleteMeasures"]["numMeasures"] == 4
    assert results["getScore"]["analysis"]["numMeasures"] == 4



TPC_BY_PITCH_CLASS = [14, 21, 16, 23, 18, 13, 20, 15, 22, 17, 24, 19]


def xml_note(pitch, ahead=None, back=None):
    """A note, optionally tied to the note `ahead` or from the note `back` (fractions of a whole, e.g. "1/4")."""
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
    return {n["pitchMidi"]: (n.get("tieForward", False), n.get("tieBack", False)) for n in element["notes"]}


def test_get_score_reports_ties_per_note(tmp_path):
    """Ties belong to notes. getScore used to read them from the chord, so isTie was always false."""
    # Bar 1: C-E-G with only C and E tied into C-E-A, then a D tied across the barline into bar 2
    source = tie_score(
        tmp_path,
        xml_chord("quarter", xml_note(60, ahead="1/4"), xml_note(64, ahead="1/4"), 67)
        + xml_chord("quarter", xml_note(60, back="1/4"), xml_note(64, back="1/4"), 69)
        + xml_chord("half", xml_note(62, ahead="1/2")),
        xml_chord("whole", xml_note(62, back="1/2")),
    )
    (entry,) = run([{"action": "getScore", "params": {"startMeasure": 1, "endMeasure": 2}}], source)
    bar_1, bar_2 = bars_of(entry["result"])

    assert ties(bar_1[0]) == {60: (True, False), 64: (True, False), 67: (False, False)}
    assert ties(bar_1[1]) == {60: (False, True), 64: (False, True), 69: (False, False)}
    assert ties(bar_1[2]) == {62: (True, False)}
    assert ties(bar_2[0]) == {62: (False, True)}
    assert [e["isTie"] for e in bar_1 + bar_2] == [True, False, True, False]


def test_add_tie_partial_chord_then_across_the_barline(tmp_path):
    source = tie_score(
        tmp_path,
        xml_chord("quarter", 60, 64, 67) + xml_chord("quarter", 60, 64, 69) + xml_chord("half", 62),
        xml_chord("whole", 62),
    )
    results = run([
        {"action": "addTie", "params": {"pitches": [60, 64]}},  # the cursor starts on the first chord
        {"action": "nextElement", "params": {}},  # addTie left the cursor on C-E-A; move on to the D
        {"action": "addTie", "params": {}},
        {"action": "getScore", "params": {"startMeasure": 1, "endMeasure": 2}},
    ], source)
    partial, _, across, score = (r["result"] for r in results)
    assert (partial["tiedPitches"], partial["skippedPitches"]) == ([60, 64], [])
    assert across["tiedPitches"] == [62]
    bar_1, bar_2 = bars_of(score)
    assert ties(bar_1[0]) == {60: (True, False), 64: (True, False), 67: (False, False)}
    assert ties(bar_1[1]) == {60: (False, True), 64: (False, True), 69: (False, False)}
    assert ties(bar_1[2]) == {62: (True, False)} and ties(bar_2[0]) == {62: (False, True)}
    assert [e["durationTicks"] for e in bar_1 + bar_2] == [480, 480, 960, 1920]  # no notes inserted


def test_add_tie_default_pitches_skip_the_ones_not_in_the_next_chord(tmp_path):
    source = tie_score(tmp_path, xml_chord("quarter", 60, 64, 67) + xml_chord("quarter", 60, 64, 69)
                       + xml_chord("half", 62))
    added, score = (r["result"] for r in run([
        {"action": "addTie", "params": {}},
        {"action": "getScore", "params": {"startMeasure": 1, "endMeasure": 1}},
    ], source))
    assert (added["tiedPitches"], added["skippedPitches"]) == ([60, 64], [67])
    (bar,) = bars_of(score)
    assert ties(bar[0]) == {60: (True, False), 64: (True, False), 67: (False, False)}


def test_add_tie_chain(tmp_path):
    source = tie_score(tmp_path, xml_chord("quarter", 60) * 4)
    results = run([{"action": "addTie", "params": {}}] * 3
                  + [{"action": "getScore", "params": {"startMeasure": 1, "endMeasure": 1}}], source)
    (bar,) = bars_of(results[-1]["result"])
    assert [ties(e)[60] for e in bar] == [(True, False), (True, True), (True, True), (False, True)]
    # Each addTie reports the chord it moved the cursor to: the one it tied to
    assert [r["result"]["currentSelection"]["startTick"] for r in results[:3]] == [480, 960, 1440]
    (reported,) = results[0]["result"]["currentSelection"]["elements"]["staff0"]
    assert ties(reported) == {60: (False, True)}  # the reported chord already shows its tie back


def test_add_tie_errors_leave_the_music_unchanged(tmp_path):
    """MuseScore's tie command would insert a new tied note here and overwrite the next one."""
    rest = "<Rest><durationType>quarter</durationType></Rest>"
    source = tie_score(tmp_path, xml_chord("quarter", 60) + xml_chord("quarter", 62) + xml_chord("quarter", 64) + rest)
    results = run([
        {"action": "addTie", "params": {}},  # C, then D: no matching pitch
        {"action": "addTie", "params": {"pitches": [62]}},  # D is not in the chord at the cursor
        {"action": "nextElement", "params": {"numElements": 2}},
        {"action": "addTie", "params": {}},  # E, then a rest
        {"action": "getScore", "params": {"startMeasure": 1, "endMeasure": 1}},
    ], source)
    no_match, not_in_chord, _, before_rest, score = (r["result"] for r in results)
    assert no_match["error"].startswith("No pitch to tie: the chord at the cursor has [60], the next chord has [62]")
    assert "requested [62]" in not_in_chord["error"]
    assert "rest" in before_rest["error"]
    (bar,) = bars_of(score)
    assert [(e["name"], e["durationTicks"]) for e in bar] == [("Chord", 480)] * 3 + [("Rest", 480)]
    assert not any(e["isTie"] for e in bar)
