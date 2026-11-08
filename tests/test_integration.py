"""Integration tests: real MCP tools and WebSocket client against the in-memory mock plugin."""

import asyncio

from fastmcp import Client

import server
from mock_musescore import MockMuseScore, MockScore, demo_score, running_mock

QUARTER = {"numerator": 1, "denominator": 4}


def patterned_score(*patterns):
    """Mock score with one staff per pattern; each letter is a bar of four quarter notes of one pitch."""
    mock = MockMuseScore(MockScore(staves=len(patterns), measures=len(patterns[0])))
    for staff, pattern in enumerate(patterns):
        mock.score.cursor_staff, mock.score.cursor_tick = staff, 0
        for letter in pattern:
            for _ in range(4):
                mock.process_command({"action": "addNote", "params": {
                    "pitch": 60 + "ABCDEFGH".index(letter), "duration": QUARTER,
                    "advanceCursorAfterAction": True}})
    mock.score.cursor_staff, mock.score.cursor_tick = 0, 0
    return mock.score


def run_with_mock(scenario, score=None):
    """Run `scenario(mcp_client, mock)` with server.client pointed at a mock plugin."""

    async def runner():
        original_uri = server.client.uri
        async with running_mock(score) as mock:
            server.client.uri = mock.uri
            server.client.websocket = None
            try:
                async with Client(server.mcp) as mcp_client:
                    await scenario(mcp_client, mock)
            finally:
                await server.client.close()
                server.client.uri = original_uri

    asyncio.run(runner())


def test_ping_reaches_plugin():
    async def scenario(c, mock):
        await c.call_tool("ping_musescore", {})
        assert mock.commands == [{"action": "ping", "params": {}}]

    run_with_mock(scenario)


def test_melody_is_written_sequentially():
    async def scenario(c, mock):
        for pitch in (60, 62, 64):
            await c.call_tool("add_note", {"pitch": pitch, "duration": QUARTER})
        chords = mock.score.elements[0]
        assert [e["notes"][0]["pitchMidi"] for e in chords] == [60, 62, 64]
        assert [e["startTick"] for e in chords] == [0, 480, 960]

    run_with_mock(scenario)


def test_add_to_chord_stacks_pitches():
    async def scenario(c, mock):
        await c.call_tool(
            "add_note", {"pitch": 60, "duration": QUARTER, "advance_cursor_after_action": False}
        )
        await c.call_tool("add_note", {"pitch": 64, "duration": QUARTER, "add_to_chord": True})
        (chord,) = mock.score.elements[0]
        assert [n["pitchMidi"] for n in chord["notes"]] == [60, 64]

    run_with_mock(scenario)


def test_process_sequence_runs_actions_in_order():
    sequence = [
        {"action": "goToMeasure", "params": {"measure": 2}},
        {"action": "addRest", "params": {"duration": QUARTER, "advanceCursorAfterAction": True}},
        {
            "action": "addNote",
            "params": {"pitch": 67, "duration": QUARTER, "advanceCursorAfterAction": True},
        },
    ]

    async def scenario(c, mock):
        await c.call_tool("processSequence", {"sequence": sequence})
        names = [(e["name"], e["startTick"]) for e in mock.score.elements[0]]
        assert names == [("Rest", 1920), ("Chord", 2400)]

    run_with_mock(scenario)


def test_undo_reverts_last_edit():
    async def scenario(c, mock):
        await c.call_tool("add_note", {"pitch": 60, "duration": QUARTER})
        await c.call_tool("undo", {})
        assert mock.score.elements[0] == []

    run_with_mock(scenario)


def test_append_measure_and_get_score():
    async def scenario(c, mock):
        await c.call_tool("append_measure", {"count": 2})
        assert mock.score.num_measures == 6
        await c.call_tool("get_score", {})
        assert mock.commands[-1]["action"] == "getScore"

    run_with_mock(scenario, MockScore(measures=4))


def test_plugin_errors_surface_in_result():
    async def scenario(c, mock):
        result = await c.call_tool("go_to_measure", {"measure": 99})
        assert "Invalid measure number" in str(result)

    run_with_mock(scenario)


def test_show_score_returns_structured_score_for_the_viewer():
    async def scenario(c, mock):
        result = await c.call_tool("show_score", {"first_measure": 2, "last_measure": 3})
        score = result.structured_content
        assert [m["measure"] for m in score["measures"]] == [2, 3]
        assert score["measureTicks"] == 1920
        assert score["title"] == "Twinkle Twinkle (demo)"
        assert "2 of 4" in result.content[0].text

    run_with_mock(scenario, demo_score())


def test_show_score_declares_its_ui_resource_and_serves_it():
    async def scenario(c, mock):
        tools = {t.name: t for t in await c.list_tools()}
        assert tools["show_score"].meta["ui"]["resourceUri"] == "ui://musescore/score-viewer.html"
        (page,) = await c.read_resource("ui://musescore/score-viewer.html")
        assert page.mime_type == "text/html;profile=mcp-app"
        assert "Vex.Flow" in page.text

    run_with_mock(scenario)


def test_get_score_returns_lilypond_in_windows():
    async def scenario(c, mock):
        first = (await c.call_tool("get_score", {})).content[0].text
        assert "Mesures affichées: 1-16" in first and "Total Mesures: 20" in first
        assert "% m.1" in first and "% m.16" in first and "% m.17" not in first
        assert "get_score(start_measure=17)" in first
        rest = (await c.call_tool("get_score", {"start_measure": 17})).content[0].text
        assert "Mesures affichées: 17-20" in rest and "More measures" not in rest
        assert mock.commands[-1]["params"] == {"startMeasure": 17, "endMeasure": 32}

    run_with_mock(scenario, patterned_score("ABCD" * 5))


def test_get_score_json_for_selected_staves():
    async def scenario(c, mock):
        analysis = (await c.call_tool(
            "get_score", {"start_measure": 2, "end_measure": 3, "staves": [1], "format": "json"}
        )).data
        assert [m["measure"] for m in analysis["measures"]] == [2, 3]
        assert [st["index"] for st in analysis["staves"]] == [1]
        assert set(analysis["measures"][0]["elements"]) == {"staff1"}

    run_with_mock(scenario, demo_score())


def test_navigation_returns_lilypond_for_the_selection():
    async def scenario(c, mock):
        text = (await c.call_tool("go_to_measure", {"measure": 1})).content[0].text
        assert "[Partition]" in text
        assert "c'4" in text and "c2 g2" in text

    run_with_mock(scenario, demo_score())


def test_get_score_shows_ties():
    score = patterned_score("AA")
    last_of_bar_1, first_of_bar_2 = score.elements[0][3], score.elements[0][4]
    last_of_bar_1["isTie"] = True
    last_of_bar_1["notes"][0]["tieForward"] = True
    first_of_bar_2["notes"][0]["tieBack"] = True

    async def scenario(c, mock):
        text = (await c.call_tool("get_score", {})).content[0].text
        assert "c'4 c'4 c'4 c'4~ | % m.1" in text
        analysis = (await c.call_tool("get_score", {"format": "json"})).data
        bar_1, bar_2 = (m["elements"]["staff0"] for m in analysis["measures"])
        assert bar_1[3]["isTie"] and bar_1[3]["notes"][0]["tieForward"]
        assert bar_2[0]["notes"][0]["tieBack"] and not bar_2[0]["isTie"]

    run_with_mock(scenario, score)


def test_set_tempo_at_a_measure():
    async def scenario(c, mock):
        await c.call_tool("set_tempo", {"bpm": 90, "measure": 2})
        assert (mock.score.tempo, mock.score.tempo_measure) == (90, 2)

    run_with_mock(scenario)


def test_color_range_and_clear_color():
    async def scenario(c, mock):
        result = (await c.call_tool(
            "color_range", {"start_measure": 1, "first_staff": 1, "last_staff": 1, "color": "#00ff00"}
        )).data
        assert result["colored"] == 2
        assert set(mock.score.colors.values()) == {"#00ff00"}
        assert {staff for staff, _, _ in mock.score.colors} == {1}
        await c.call_tool("clear_color", {"start_measure": 1})
        assert set(mock.score.colors.values()) == {"#000000"}

    run_with_mock(scenario, demo_score())


def test_set_repeat_barlines_and_volta():
    async def scenario(c, mock):
        await c.call_tool("set_repeat_barlines", {"start_measure": 1, "end_measure": 2, "play_count": 3})
        assert mock.score.repeats == {1: {"start": True}, 2: {"end": True, "count": 3}}
        await c.call_tool("add_volta", {"start_measure": 2, "endings": [1]})
        assert mock.score.voltas == [{"startMeasure": 2, "endMeasure": 2, "endings": [1], "text": "1."}]

    run_with_mock(scenario)


def test_set_repeat_barlines_falls_back_to_selection():
    score = MockScore()
    score.repeat_barlines_supported = False

    async def scenario(c, mock):
        result = (await c.call_tool("set_repeat_barlines", {"start_measure": 2, "end_measure": 3})).data
        assert result["fallback"] == "manual"
        assert mock.score.repeats == {}
        assert mock.score.selected["startMeasure"] == 2 and mock.score.selected["endMeasure"] == 3

    run_with_mock(scenario, score)


def test_prepare_measure_repeat_selects_bars():
    async def scenario(c, mock):
        result = (await c.call_tool(
            "prepare_measure_repeat", {"start_measure": 3, "bars": 2, "first_staff": 1, "last_staff": 1}
        )).data
        assert mock.score.selected == {"startMeasure": 3, "endMeasure": 4, "startStaff": 1, "endStaff": 2}
        assert "2-measure repeat" in result["next_step"]

    run_with_mock(scenario, demo_score())


def test_invalid_range_is_a_tool_error():
    async def scenario(c, mock):
        result = await c.call_tool("color_range", {"start_measure": 9}, raise_on_error=False)
        assert result.is_error
        assert "Invalid measure range" in result.content[0].text

    run_with_mock(scenario)


def test_delete_measures_shifts_later_bars():
    async def scenario(c, mock):
        await c.call_tool("delete_measures", {"start_measure": 2, "end_measure": 3})
        assert mock.score.num_measures == 3
        pitches = [e["notes"][0]["pitchMidi"] for e in mock.score.elements[0]]
        assert pitches == [60] * 4 + [64] * 4 + [65] * 4

    run_with_mock(scenario, patterned_score("ABCEF"))


def test_find_repeated_measures_reads_in_chunks_and_highlights():
    # 20 bars, so the analysis needs two getScore chunks; bars 3-10 repeat as 11-18
    pattern = "GH" + "ABCDEFAB" + "ABCDEFAB" + "CD"

    async def scenario(c, mock):
        result = (await c.call_tool("find_repeated_measures", {"highlight": True})).data
        ranges = [cmd["params"] for cmd in mock.commands if cmd["action"] == "getScore"]
        assert [(r["startMeasure"], r["endMeasure"]) for r in ranges] == [(1, 16), (17, 20)]

        (passage,) = result["passages"]
        assert (passage["start"], passage["end"], passage["duplicate_measures"]) == (3, 10, [11, 18])
        assert passage["apply"] == ["delete_measures(11, 18)", "set_repeat_barlines(3, 10, play_count=2)"]

        colored_ticks = {tick for _, tick, _ in mock.score.colors}
        assert min(colored_ticks) == 10 * 1920 and max(colored_ticks) < 18 * 1920
        assert result["highlight_legend"][-1]["meaning"].startswith("duplicate of measures 3-10")

    run_with_mock(scenario, patterned_score(pattern, pattern))


def test_applying_a_passage_shortens_the_score():
    async def scenario(c, mock):
        (passage,) = (await c.call_tool("find_repeated_measures", {})).data["passages"]
        dup_first, dup_last = passage["duplicate_measures"]
        await c.call_tool("delete_measures", {"start_measure": dup_first, "end_measure": dup_last})
        await c.call_tool("set_repeat_barlines", {"start_measure": passage["start"], "end_measure": passage["end"]})
        assert mock.score.num_measures == 5
        assert mock.score.repeats[2]["start"] and mock.score.repeats[4]["end"]
        again = (await c.call_tool("find_repeated_measures", {})).data
        assert again["passages"] == []

    run_with_mock(scenario, patterned_score("EABCABCF"))



# --- score-file edits, groove sections, part scores ----------------------------------

import json
import shutil
from pathlib import Path

from src.mscz import ScoreFile

JAZZ = Path(__file__).resolve().parent.parent / "examples" / "jazz piano" / "Jazz Piano.mscz"


def jazz_copy(tmp_path, monkeypatch):
    """A copy of the example score plus an isolated backup directory."""
    monkeypatch.setenv("MCP_MUSESCORE_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setenv("MUSESCORE_DATA_DIR", str(tmp_path / "no-musescore-data"))
    path = tmp_path / "Jazz Piano.mscz"
    shutil.copy(JAZZ, path)
    return path


def open_in_mock(path, staves=2, measures=8, score=None):
    """A mock score shaped like the file (the example has 2 staves and 8 measures) and saved in it."""
    score = score or MockScore(staves=staves, measures=measures)
    score.file_path = str(path)
    return score


def bass_staff_repeat(path, measure):
    return ScoreFile(path).staves()[1].findall("Measure")[measure - 1].findtext("voice/MeasureRepeat/subtype")


def test_apply_measure_repeats_edits_file_and_reloads(tmp_path, monkeypatch):
    path = jazz_copy(tmp_path, monkeypatch)
    original = path.read_bytes()

    async def scenario(c, mock):
        result = (await c.call_tool("apply_measure_repeats", {
            "staff": 1, "groups": [{"start": 2, "end": 3}], "score_path": str(path)})).data
        assert [g["start"] for g in result["applied"]] == [2, 3]
        assert result["reopened"] is True
        actions = [cmd["action"] for cmd in mock.commands]
        assert actions.index("ensureScoreId") < actions.index("saveScore") < actions.index("reopenScore")
        assert mock.opened == [str(path)]
        assert bass_staff_repeat(Path(result["backup"]), 2) is None
        assert bass_staff_repeat(path, 2) == "1" and bass_staff_repeat(path, 3) == "1"

        restored = (await c.call_tool("restore_backup", {"score_path": str(path)})).data
        assert Path(restored["previous_version_backup"]).exists()
        assert mock.opened == [str(path), str(path)]
        assert bass_staff_repeat(path, 2) is None  # back to the version before the edit

    run_with_mock(scenario, open_in_mock(path))


def test_apply_measure_repeats_without_changes_does_not_reload(tmp_path, monkeypatch):
    path = jazz_copy(tmp_path, monkeypatch)

    async def scenario(c, mock):
        result = (await c.call_tool("apply_measure_repeats", {
            "staff": 1, "groups": [{"start": 1}], "score_path": str(path)})).data
        assert result["skipped"] and not result["applied"]
        assert "backup" not in result and mock.opened == []
        assert not (tmp_path / "backups").exists()

    run_with_mock(scenario, open_in_mock(path))


def test_apply_measure_repeats_finds_the_open_file(tmp_path, monkeypatch):
    path = jazz_copy(tmp_path, monkeypatch)
    data_dir = tmp_path / "musescore"
    (data_dir / "session").mkdir(parents=True)
    (data_dir / "session" / "session.json").write_text(json.dumps([str(path)]))
    (data_dir / "recent_files.json").write_text(json.dumps([str(path), "/nowhere/Other.mscz"]))
    monkeypatch.setenv("MUSESCORE_DATA_DIR", str(data_dir))
    score = open_in_mock(path)

    async def scenario(c, mock):
        result = (await c.call_tool("apply_measure_repeats", {
            "staff": 1, "groups": [{"start": 3, "end": 6, "bars": 2}]})).data
        assert result["file"] == str(path)
        assert [(g["start"], g["bars"]) for g in result["applied"]] == [(3, 2), (5, 2)]
        assert bass_staff_repeat(path, 3) == "2"

    run_with_mock(scenario, score)


def test_apply_measure_repeats_rejects_uneven_runs(tmp_path, monkeypatch):
    path = jazz_copy(tmp_path, monkeypatch)

    async def scenario(c, mock):
        result = await c.call_tool("apply_measure_repeats", {
            "staff": 1, "groups": [{"start": 3, "end": 5, "bars": 2}], "score_path": str(path)},
            raise_on_error=False)
        assert result.is_error and "cannot be split" in result.content[0].text

    run_with_mock(scenario, open_in_mock(path))


def drum_score(pattern, other=None):
    score = patterned_score(pattern, other) if other else patterned_score(pattern)
    score.drum_staves = {0}
    score.part_names[0] = "Drum Kit"
    return score


def test_find_groove_sections_defaults_to_drums():
    async def scenario(c, mock):
        result = (await c.call_tool("find_groove_sections", {})).data
        (staff,) = result["staves"]
        assert staff["name"] == "Drum Kit"
        assert staff["road_map"][0] == "Bars 1-5: groove bar 1, 3 exact copies, fill 5, collapse 1-4 to 1 x4"
        assert staff["apply_exact_copies"] == {"staff": 0, "groups": [{"start": 2, "end": 4, "bars": 1}]}
        assert staff["sections"][0]["runs"][0]["play_count"] == 4

    run_with_mock(scenario, drum_score("AAAAB", "CDEFG"))


def test_find_groove_sections_needs_a_drum_staff():
    async def scenario(c, mock):
        result = await c.call_tool("find_groove_sections", {}, raise_on_error=False)
        assert result.is_error and "No drum staff" in result.content[0].text

    run_with_mock(scenario, patterned_score("AAAA"))


def test_collapse_to_repeat_keeps_one_bar_with_a_count():
    async def scenario(c, mock):
        result = (await c.call_tool("collapse_to_repeat", {"start": 2, "end": 5})).data
        assert result["success"]
        assert mock.score.repeats[2] == {"start": True, "end": True, "count": 4}
        assert mock.score.num_measures == 3
        assert mock.score.style["repeatPlayCountShow"] is True

    run_with_mock(scenario, drum_score("BAAAAC"))


def test_collapse_to_repeat_refuses_when_other_staves_differ():
    async def scenario(c, mock):
        result = await c.call_tool("collapse_to_repeat", {"start": 1, "end": 4}, raise_on_error=False)
        assert result.is_error and "Part 2 (staff 1): bars [2, 3, 4]" in result.content[0].text
        assert mock.score.num_measures == 4
        forced = (await c.call_tool("collapse_to_repeat", {"start": 1, "end": 4, "force": True})).data
        assert forced["differences_dropped"][0]["bars"] == [2, 3, 4]
        assert mock.score.num_measures == 1

    run_with_mock(scenario, drum_score("AAAA", "CDEF"))


QUARTET = Path(__file__).resolve().parent.parent / "examples" / "string quartet" / "String Quartet.mscz"


def quartet_copy(tmp_path, monkeypatch):
    """A copy of the 4-part example (4 staves, 4 measures) in an isolated MuseScore data dir."""
    monkeypatch.setenv("MCP_MUSESCORE_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setenv("MUSESCORE_DATA_DIR", str(tmp_path / "no-musescore-data"))
    path = tmp_path / "Quartet.mscz"
    shutil.copy(QUARTET, path)
    return path


def test_make_part_score_opens_a_copy_with_one_part(tmp_path, monkeypatch):
    source = quartet_copy(tmp_path, monkeypatch)
    score = open_in_mock(source, score=patterned_score("AAAA", "BBBB", "CCCC", "DDDD"))
    score.short_names[3] = "Vc."  # trailing dot: the copy must not be named "... - Vc..mscz"

    async def scenario(c, mock):
        result = (await c.call_tool("make_part_score", {"staves": [3], "score_path": str(source)})).data
        target = tmp_path / "Quartet - Vc.mscz"
        assert result["file"] == str(target) and result["staves_now"] == 1
        assert result["kept_parts"] == ["Violoncello"]
        assert mock.opened == [str(target)]
        assert "removeParts" not in [cmd["action"] for cmd in mock.commands]
        copy = ScoreFile(target)
        assert len(copy.staves()) == 1 and [p.findtext("trackName") for p in copy.score.findall("Part")] == ["Violoncello"]
        # the copy has its own score ID, so it can never be mistaken for the original
        from src.mscz.locate import read_score_id
        assert read_score_id(target) and read_score_id(target) != read_score_id(source)
        assert len(ScoreFile(source).staves()) == 4  # the original is unchanged

    run_with_mock(scenario, score)


def test_make_part_score_reopens_the_original_if_the_copy_cannot_be_opened(tmp_path, monkeypatch):
    source = quartet_copy(tmp_path, monkeypatch)
    score = open_in_mock(source, score=patterned_score("AAAA", "BBBB", "CCCC", "DDDD"))

    async def scenario(c, mock):
        mock.opens_in_new_window = True
        result = await c.call_tool("make_part_score", {"staves": [3], "score_path": str(source)},
                                   raise_on_error=False)
        assert result.is_error and "the original was reopened unchanged" in result.content[0].text
        assert mock.opened[-1] == str(source)
        assert mock.score.num_staves == 4

    run_with_mock(scenario, score)


def test_make_part_score_in_place_removes_parts_from_the_open_score(tmp_path, monkeypatch):
    source = quartet_copy(tmp_path, monkeypatch)
    score = open_in_mock(source, score=patterned_score("AAAA", "BBBB", "CCCC", "DDDD"))

    async def scenario(c, mock):
        result = (await c.call_tool("make_part_score", {"staves": [3], "in_place": True})).data
        assert result["staves_now"] == 1 and mock.score.num_staves == 1
        actions = [cmd["action"] for cmd in mock.commands]
        # nothing is saved and no other file is opened: the full score (maybe damaged) is never written again
        assert "saveScore" not in actions and "reopenScore" not in actions and mock.opened == []
        assert actions.index("exportScore") < actions.index("removeParts")
        (export,) = result["full_score_backups"]  # the file was never saved with this score's ID, so no copy
        assert export.endswith(".full-score.mxl") and Path(export).read_text() == "exported 4 staves"
        assert result["incomplete_bars"] == [] and result["warnings"] == []

    run_with_mock(scenario, score)


def test_file_edits_refuse_a_file_that_is_not_the_open_score(tmp_path, monkeypatch):
    open_file = jazz_copy(tmp_path, monkeypatch)
    other = tmp_path / "Other.mscz"
    shutil.copy(JAZZ, other)

    async def scenario(c, mock):
        # an explicit path to another file is refused
        result = await c.call_tool("set_end_notes", {"lines": ["x"], "score_path": str(other)},
                                   raise_on_error=False)
        assert result.is_error and "is not the file of the score open in MuseScore" in result.content[0].text
        # a file with the open score's ID but a different shape (e.g. not saved) is refused too
        mock.score.num_measures = 5
        result = await c.call_tool("set_end_notes", {"lines": ["x"]}, raise_on_error=False)
        assert result.is_error and "but the open score has 2 and 5" in result.content[0].text
        assert not (tmp_path / "backups").exists()

    data_dir = tmp_path / "musescore"
    (data_dir / "session").mkdir(parents=True)
    (data_dir / "session" / "session.json").write_text(json.dumps([str(other)]))
    (data_dir / "recent_files.json").write_text(json.dumps([str(open_file), str(other)]))
    monkeypatch.setenv("MUSESCORE_DATA_DIR", str(data_dir))
    run_with_mock(scenario, open_in_mock(open_file))


def test_add_rehearsal_mark():
    async def scenario(c, mock):
        await c.call_tool("add_rehearsal_mark", {"measure": 3, "text": "Verse"})
        assert mock.score.rehearsal_marks == [{"measure": 3, "text": "Verse"}]

    run_with_mock(scenario)


def test_highlight_label_and_clear():
    async def scenario(c, mock):
        await c.call_tool("highlight_bars", {"start_measure": 2, "end_measure": 3, "first_staff": 0, "last_staff": 1,
                                             "color": "#ff0000", "opacity": 0.5})
        assert mock.score.highlights == [
            {"staff": s, "startMeasure": 2, "endMeasure": 3, "color": "#80ff0000"} for s in (0, 1)
        ]
        await c.call_tool("add_label", {"measure": 2, "text": "Groove x7", "staff": 1})
        assert mock.score.labels[0]["text"] == "Groove x7" and mock.score.labels[0]["background"] == "#fff2a8"

        removed = (await c.call_tool("clear_highlights", {"first_staff": 1, "last_staff": 1})).data
        assert removed["removed"] == 2
        assert [h["staff"] for h in mock.score.highlights] == [0] and mock.score.labels == []

    run_with_mock(scenario, demo_score())


def test_highlight_rejects_bad_colors():
    async def scenario(c, mock):
        result = await c.call_tool("highlight_bars", {"start_measure": 1, "color": "yellow"}, raise_on_error=False)
        assert result.is_error and "#rrggbb" in result.content[0].text
        result = await c.call_tool("add_label", {"measure": 1, "text": "A", "background": "#12"},
                                   raise_on_error=False)
        assert result.is_error

    run_with_mock(scenario)


def test_color_range_can_color_part_of_a_bar():
    async def scenario(c, mock):
        # staff 0, bar 1 of the demo: four quarter notes at ticks 0, 480, 960, 1440
        result = (await c.call_tool("color_range", {
            "start_measure": 1, "first_staff": 0, "last_staff": 0, "start_beat": 3, "end_beat": 4,
            "color": "#2ca02c"})).data
        assert result["colored"] == 2
        assert sorted(tick for _, tick, _ in mock.score.colors) == [960, 1440]

        mock.score.colors.clear()
        await c.call_tool("color_range", {"start_measure": 1, "end_measure": 2, "first_staff": 0,
                                          "last_staff": 0, "start_beat": 3.5, "end_beat": 1})
        # from the "and" of 3 in bar 1 (no note starts there) to the end of beat 1 in bar 2
        assert sorted(tick for _, tick, _ in mock.score.colors) == [1440, 1920]

    run_with_mock(scenario, demo_score())


def test_beats_outside_the_bar_are_errors():
    async def scenario(c, mock):
        result = await c.call_tool("color_range", {"start_measure": 1, "start_beat": 5}, raise_on_error=False)
        assert result.is_error and "outside measure 1" in result.content[0].text
        result = await c.call_tool("color_range", {"start_measure": 1, "start_beat": 3, "end_beat": 2},
                                   raise_on_error=False)
        assert result.is_error and "empty" in result.content[0].text

    run_with_mock(scenario, demo_score())


def crash_and_kick_score():
    """Drum staff: bar 1 has kick+crash on beat 1, then kick+snare, plus an f and an mf dynamic."""
    mock = MockMuseScore(MockScore(staves=1, measures=2))
    for pitches in ((36, 57), (36, 38), (36,), (38,)):
        mock.process_command({"action": "addNote", "params": {
            "pitch": pitches[0], "duration": QUARTER, "advanceCursorAfterAction": len(pitches) == 1}})
        for extra in pitches[1:]:
            mock.process_command({"action": "addNote", "params": {
                "pitch": extra, "duration": QUARTER, "advanceCursorAfterAction": True, "addToChord": True}})
            mock.score.cursor_tick = mock.score.elements[0][-1]["startTick"] + 480
    score = mock.score
    score.drum_staves = {0}
    score.markings = [{"staff": 0, "startTick": 0, "name": "Dynamic", "text": "f"},
                      {"staff": 0, "startTick": 1920, "name": "Dynamic", "text": "mf"}]
    score.cursor_tick = 0
    return score


def test_highlight_notes_marks_only_the_crash():
    async def scenario(c, mock):
        result = (await c.call_tool("highlight_notes", {"start_measure": 1, "drums": ["crashes"]})).data
        assert result["highlighted"] == 1
        assert list(mock.score.note_highlights) == [(0, 0, 57)]
        assert mock.commands[-1]["params"]["pitches"] == [49, 57]
        assert mock.commands[-1]["params"]["color"] == "#73ffd600"

        bad = await c.call_tool("highlight_notes", {"start_measure": 1, "drums": ["gong"]}, raise_on_error=False)
        assert bad.is_error and "Unknown drum" in bad.content[0].text

    run_with_mock(scenario, crash_and_kick_score())


def test_dynamics_are_listed_highlighted_and_cleared():
    async def scenario(c, mock):
        text = (await c.call_tool("get_score", {})).content[0].text
        assert "[Markings]\nm.1 beat 1, staff 0: Dynamic f\nm.2 beat 1, staff 0: Dynamic mf" in text

        result = (await c.call_tool("highlight_markings", {})).data
        assert result["found"] == 2
        assert all(mk["highlight"] == "#8cffd600" for mk in mock.score.markings)
        assert "Dynamic f (highlighted)" in (await c.call_tool("get_score", {})).content[0].text

        await c.call_tool("highlight_notes", {"start_measure": 1})
        cleared = (await c.call_tool("clear_highlights", {"kinds": ["markings", "notes"]})).data
        assert cleared["removed"] == 2 + 6  # two dynamics, six noteheads in bar 1
        assert not any(mk["highlight"] for mk in mock.score.markings) and not mock.score.note_highlights

    run_with_mock(scenario, crash_and_kick_score())


def test_highlight_symbols_modes():
    async def scenario(c, mock):
        await c.call_tool("highlight_symbols", {"start_measure": 1, "end_measure": 2})
        await c.call_tool("highlight_symbols", {"kinds": ["repeat_barlines"], "mode": "color", "color": "#5dade2"})
        first, second = mock.score.symbol_requests
        assert first["mode"] == "highlight" and first["color"] == "#99a7d8f0"
        assert first["kinds"] == ["time_signatures", "repeat_barlines", "measure_repeats"]
        assert second == {**second, "mode": "color", "color": "#5dade2", "kinds": ["repeat_barlines"], "endMeasure": 4}
        bad = await c.call_tool("highlight_symbols", {"mode": "color", "color": "blue"}, raise_on_error=False)
        assert bad.is_error

    run_with_mock(scenario)


def test_bars_are_numbered_as_played():
    async def scenario(c, mock):
        # bars: 1 intro, 2 groove x3, 3 fill, 4-5 passage x2, 6 end
        await c.call_tool("set_repeat_barlines", {"start_measure": 2, "end_measure": 2, "play_count": 3})
        await c.call_tool("set_repeat_barlines", {"start_measure": 4, "end_measure": 5})
        result = (await c.call_tool("number_bars_as_played", {})).data
        assert [(o["measure"], o["addToNumber"]) for o in result["offsets"]] == [(3, 2), (6, 2)]
        assert mock.score.displayed_numbers() == [1, 2, 5, 6, 7, 10]
        assert result["lastMeasureNumber"] == 10

        again = (await c.call_tool("number_bars_as_played", {"exclude_from_count": [1]})).data
        assert again["lastMeasureNumber"] == 9 and mock.score.displayed_numbers()[2] == 4

        text = (await c.call_tool("get_score", {"start_measure": 1, "end_measure": 6})).content[0].text
        assert "% m.2 (bar 1) |: :|x3" in text and "% m.3 (bar 4)" in text

        await c.call_tool("set_measure_number", {"measure": 3, "add_to_number": 0})
        assert mock.score.displayed_numbers()[2] == 2
        bad = await c.call_tool("set_measure_number", {"measure": 3}, raise_on_error=False)
        assert bad.is_error

    run_with_mock(scenario, patterned_score("ABCDEF"))


def test_add_text_with_cue_style():
    async def scenario(c, mock):
        await c.call_tool("add_text", {"measure": 2, "text": "Verse cue", "beat": 3})
        (text,) = mock.score.texts
        assert text["tick"] == 1920 + 960
        assert (text["fontSize"], text["italic"], text["color"], text["placement"]) == (8, True, "#9e9e9e", "above")
        bad = await c.call_tool("add_text", {"measure": 2, "text": "x", "color": "grey"}, raise_on_error=False)
        assert bad.is_error

    run_with_mock(scenario)


def test_header_and_end_notes_edit_the_file_and_reload(tmp_path, monkeypatch):
    path = jazz_copy(tmp_path, monkeypatch)

    async def scenario(c, mock):
        result = (await c.call_tool("set_score_header", {
            "title": "Hold The Line", "subtitle": "Drum chart", "part_name": "Drums", "score_path": str(path)})).data
        assert result["header"]["subtitle"] == "Drum chart" and result["reopened"] is True
        assert Path(result["backup"]).exists()

        same = (await c.call_tool("set_score_header", {"title": "Hold The Line", "score_path": str(path)})).data
        assert "backup" not in same  # nothing changed, no reload

        notes = (await c.call_tool("set_end_notes", {
            "lines": ["Intro: x4, then x2", "Verses 1-3: x9 each"], "score_path": str(path)})).data
        assert notes["lines"] == 2 and notes["reopened"] is True
        assert mock.opened == [str(path), str(path)]

        bad = await c.call_tool("set_score_header", {"score_path": str(path)}, raise_on_error=False)
        assert bad.is_error

    run_with_mock(scenario, open_in_mock(path))


def test_remove_annotations_and_reset_numbering():
    async def scenario(c, mock):
        await c.call_tool("add_text", {"measure": 1, "text": "* crash on 1st time only   ** crash every other bar"})
        await c.call_tool("add_text", {"measure": 2, "text": "**", "size": 10, "italic": False})
        await c.call_tool("add_text", {"measure": 3, "text": "*", "size": 10, "italic": False})
        await c.call_tool("add_label", {"measure": 2, "text": "Groove x7"})
        await c.call_tool("add_rehearsal_mark", {"measure": 1, "text": "Intro"})
        await c.call_tool("add_volta", {"start_measure": 4})

        only_double = (await c.call_tool("remove_annotations", {"start_measure": 2, "contains": "**"})).data
        assert only_double["removed"]["texts"] == 1
        assert [t["text"] for t in mock.score.texts] == ["* crash on 1st time only   ** crash every other bar", "*"]
        single = (await c.call_tool("remove_annotations", {"contains": "*", "exact": True})).data
        assert single["removed"]["texts"] == 1 and len(mock.score.texts) == 1
        await c.call_tool("add_text", {"measure": 3, "text": "*"})

        everything = (await c.call_tool("remove_annotations", {
            "kinds": ["texts", "labels", "rehearsal_marks", "voltas"]})).data
        assert everything["removed"] == {"texts": 2, "labels": 1, "rehearsal_marks": 1, "tempo": 0, "voltas": 1}
        assert not (mock.score.texts or mock.score.labels or mock.score.rehearsal_marks or mock.score.voltas)

        await c.call_tool("set_repeat_barlines", {"start_measure": 2, "end_measure": 2, "play_count": 3})
        await c.call_tool("number_bars_as_played", {"exclude_from_count": [1]})
        reset = (await c.call_tool("number_bars_as_played", {"reset": True})).data
        assert reset["reset"] and mock.score.displayed_numbers() == [1, 2, 3, 4]

    run_with_mock(scenario)


def test_file_edits_after_make_part_score_go_to_the_copy(tmp_path, monkeypatch):
    """The original incident: after make_part_score, MuseScore's session list still named the original."""
    source = jazz_copy(tmp_path, monkeypatch)
    data_dir = tmp_path / "musescore"
    (data_dir / "session").mkdir(parents=True)
    (data_dir / "session" / "session.json").write_text(json.dumps([str(source)]))
    (data_dir / "recent_files.json").write_text(json.dumps([str(source)]))
    monkeypatch.setenv("MUSESCORE_DATA_DIR", str(data_dir))
    score = open_in_mock(source, score=drum_score("AAAAAAAA", "CDEFGHAB"))
    score.short_names[0] = "drm."

    async def scenario(c, mock):
        copy = Path((await c.call_tool("make_part_score", {"staves": [0, 1]})).data["file"])
        await c.call_tool("set_end_notes", {"lines": ["Verses x9"]})
        await c.call_tool("set_score_header", {"subtitle": "Drum chart"})

        def has_notes(path):
            return any(child.tag == "TBox" for child in ScoreFile(path).staves()[0])

        assert has_notes(copy) and not has_notes(source)
        from src.mscz.frames import header_texts
        assert header_texts(ScoreFile(copy)).get("subtitle") == "Drum chart"
        assert "subtitle" not in header_texts(ScoreFile(source))

    run_with_mock(scenario, score)


def test_collapse_to_repeat_collapses_a_two_bar_phrase():
    async def scenario(c, mock):
        result = (await c.call_tool("collapse_to_repeat", {"start": 2, "end": 7, "phrase_bars": 2})).data
        assert "Bars 2-3 now play 3 times" in result["message"]
        assert mock.score.repeats[2]["start"] and mock.score.repeats[3] == {"end": True, "count": 3}
        assert mock.score.num_measures == 4

    run_with_mock(scenario, drum_score("CABABABD"))


def test_collapse_to_repeat_refuses_phrases_that_differ():
    async def scenario(c, mock):
        result = await c.call_tool("collapse_to_repeat", {"start": 1, "end": 4, "phrase_bars": 2},
                                   raise_on_error=False)
        assert result.is_error and "bars [4]" in result.content[0].text
        bad = await c.call_tool("collapse_to_repeat", {"start": 1, "end": 5, "phrase_bars": 2},
                                raise_on_error=False)
        assert bad.is_error and "whole number" in bad.content[0].text
        assert mock.score.num_measures == 6

    run_with_mock(scenario, drum_score("ABACDE"))



def test_articulations_and_ghost_notes():
    score = drum_score("AAAA")
    score.elements[0][1]["notes"].append({"pitchMidi": 42, "tpc": 0, "pitchName": "F#", "ghost": True})
    score.elements[0][5]["notes"] = [{"pitchMidi": 42, "tpc": 0, "pitchName": "F#", "ghost": True}]

    async def scenario(c, mock):
        listed = (await c.call_tool("ghost_notes", {})).data
        assert listed["ghostNotes"] == 2 and listed["bars"] == [{"measure": 1, "ghostNotes": 1}, {"measure": 2, "ghostNotes": 1}]
        removed = (await c.call_tool("ghost_notes", {"mode": "remove"})).data
        assert removed["removed"] == 2 and mock.score.elements[0][5]["name"] == "Rest"

        await c.call_tool("add_articulation", {"start_measure": 1, "end_measure": 1, "symbol": "half_open",
                                               "start_beat": 2, "end_beat": 3})
        assert [e.get("articulations") for e in mock.score.elements[0][:4]] == [None, ["half_open"], ["half_open"], None]
        assert mock.commands[-1]["params"]["symbol"] == "half_open"
        gone = (await c.call_tool("remove_articulations", {})).data
        assert gone["removed"] == 2

    run_with_mock(scenario, score)


def test_beam_over_rests_only_inside_a_beat():
    score = drum_score("A")
    note = lambda tick, length: {"name": "Chord", "startTick": tick, "durationTicks": length, "voice": 0,
                                 "notes": [{"pitchMidi": 42, "tpc": 0, "pitchName": "F#"}]}
    rest = lambda tick, length: {"name": "Rest", "startTick": tick, "durationTicks": length, "voice": 0}
    # beat 1: 16th, 16th rest, eighth (rest inside the beat); beat 2: rest then a note (rest starts the beat)
    score.elements[0] = [note(0, 120), rest(120, 120), note(240, 240), rest(480, 240), note(720, 240),
                         rest(960, 960)]

    async def scenario(c, mock):
        result = (await c.call_tool("beam_over_rests", {})).data
        assert result["changed"] == 1
        assert [e.get("beamMode") for e in mock.score.elements[0] if e["name"] == "Rest"] == ["mid", None, None]
        assert mock.commands[-1]["params"] == {"startMeasure": 1, "endMeasure": 1, "startStaff": 0}
        cleared = (await c.call_tool("beam_over_rests", {"clear": True})).data
        assert cleared["changed"] == 1

    run_with_mock(scenario, score)


def test_file_edits_in_a_part_tab_detach_the_part_first(tmp_path, monkeypatch):
    """The agent worked in the drum part's tab: the score ID was saved into the part, not the full score."""
    from src.mscz.locate import read_score_id
    from tests.test_parts import score_with_part
    monkeypatch.setenv("MCP_MUSESCORE_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setenv("MUSESCORE_DATA_DIR", str(tmp_path / "no-musescore-data"))
    full, entry = score_with_part(tmp_path, score_id="mcp-part-1")
    score = open_in_mock(full, score=patterned_score("DDDD"))
    score.score_id, score.part_entry = "mcp-part-1", entry

    async def scenario(c, mock):
        result = (await c.call_tool("set_end_notes", {"lines": ["Verses x4"], "score_path": str(full)})).data
        part = tmp_path / "Quartet - Cello.mscz"
        assert result["file"] == str(part)
        # edited first, then opened once: two quick reopens crashed MuseScore
        assert mock.opened == [str(part)] and mock.score.file_path == str(part)
        assert [c["action"] for c in mock.commands].count("reopenScore") == 1
        assert any(child.tag == "TBox" for child in ScoreFile(part).staves()[0])
        assert read_score_id(part) and read_score_id(part) != "mcp-part-1"
        assert len(ScoreFile(full).staves()) == 4  # the full score file is untouched
        assert list((tmp_path / "backups").glob("Quartet.*.mscz"))

    run_with_mock(scenario, score)


def test_incomplete_bars_are_found():
    from src.tools.structure import incomplete_measures
    measures = [{"measure": 52, "durationTicks": 1440, "elements": {
        "staff0": [{"name": "Chord", "durationTicks": 960, "voice": 0}, {"name": "Rest", "durationTicks": 480, "voice": 0}],
        "staff1": [{"name": "Chord", "durationTicks": 1920, "voice": 0}, {"name": "Chord", "durationTicks": 480, "voice": 1}],
    }}]
    assert incomplete_measures(measures) == [
        {"measure": 52, "staff": 1, "found_ticks": {0: 1920}, "expected_ticks": 1440}]


def test_reopens_are_spaced(monkeypatch):
    """MuseScore crashed when a score was closed ~0.3 s after it was opened: the server waits in between."""
    import asyncio
    from src.tools import score_file
    monkeypatch.setattr(score_file, "REOPEN_GAP", 0.5)
    monkeypatch.setattr(score_file, "_last_reopen", 0.0)
    calls = []

    class Client:
        async def send_command(self, action, params=None):
            calls.append((action, asyncio.get_running_loop().time()))
            return {"status": "success", "result": {"success": True}}

    async def twice():
        await score_file.reopen_in_place(Client(), Path("/nonexistent/a.mscz"))
        await score_file.reopen_in_place(Client(), Path("/nonexistent/a.mscz"))

    asyncio.run(twice())
    reopens = [t for action, t in calls if action == "reopenScore"]
    assert len(reopens) == 2 and reopens[1] - reopens[0] >= 0.45


def test_section_counts_from_the_song_structure():
    """Bar 1 is a count-in (excluded from the bar count), bars 2-3 a lead-in before the intro groove."""
    score = drum_score("DEFAAAABBBBBBC")
    score.irregular = {1}
    score.markings += [{"staff": 0, "startTick": 0, "name": "RehearsalMark", "text": "Intro"},
                       {"staff": 0, "startTick": 7 * score.measure_ticks, "name": "RehearsalMark", "text": "Verse"}]

    async def scenario(c, mock):
        outline = (await c.call_tool("song_structure", {})).data
        intro, verse = outline["sections"]
        assert (intro["bars_played"], intro["lead_in_bars"], intro["count"], intro["not_counted"]) == (6, 2, "2+4", [1])
        assert (verse["bars_played"], verse["count"]) == (7, "4+3") and outline["total_bars_played"] == 13
        assert outline["suggested_rows"][0]["count"] == "2+4"

        result = (await c.call_tool("label_section_counts", {})).data
        assert result["counts"] == [{"measure": 1, "text": "2+4"}, {"measure": 8, "text": "4+3"}]
        assert [c["params"]["mode"] for c in mock.commands if c["action"] == "addSectionCounts"] == ["label"]
        assert [mk["text"] for mk in mock.score.markings] == ["Intro (2+4)", "Verse (4+3)"]
        assert (mock.score.style["rehearsalMarkFontSize"], mock.score.style["rehearsalMarkMinDistance"]) == (12, 1)
        # the counts written in the labels are kept when they still add up
        assert [sec["count"] for sec in (await c.call_tool("song_structure", {})).data["sections"]] == ["2+4", "4+3"]
        # the count in the label doesn't change the section names; running it again replaces the counts
        assert [sec["section"] for sec in (await c.call_tool("song_structure", {})).data["sections"]] == ["Intro", "Verse"]
        await c.call_tool("label_section_counts", {"counts": [{"measure": 8, "text": "(2x4)"}]})
        assert [mk["text"] for mk in mock.score.markings] == ["Intro (2+4)", "Verse (2x4)"]

        # counts left beside a label on another bar go when the counts move into the labels
        mock.score.texts.append({"measure": 2, "text": "2+4", "sectionCount": True})
        await c.call_tool("label_section_counts", {})
        assert not [t for t in mock.score.texts if t.get("sectionCount")]

        # beside the label instead: the count in the label goes
        await c.call_tool("label_section_counts", {"counts": [{"measure": 8, "text": "2x4"}], "placement": "beside"})
        assert mock.score.markings[1]["text"] == "Verse"
        assert [(t["measure"], t["text"]) for t in mock.score.texts if t.get("sectionCount")] == [(8, "2x4")]
        await c.call_tool("label_section_counts", {"clear": True})
        assert [mk["text"] for mk in mock.score.markings] == ["Intro", "Verse"]
        assert not [t for t in mock.score.texts if t.get("sectionCount")]
        bad = await c.call_tool("label_section_counts", {"counts": [{"measure": 8}]}, raise_on_error=False)
        assert bad.is_error

    run_with_mock(scenario, score)
