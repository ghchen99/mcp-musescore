"""Bar numbers as printed in the score, which is how users name bars.

Tools take and give the numbers printed in the score: a pickup bar is bar 0, and
a number printed on two bars (a split bar, or a section that starts again from
1) is 12a and 12b. Measures' positions stay inside the server.
"""

import pytest
from test_integration import patterned_score, run_with_mock


def pickup_score():
    """Five measures, the first a pickup: printed bars 0-4."""
    score = patterned_score("ABCDE")
    score.irregular = {1}
    return score


def text_of(result):
    return " ".join(c.text for c in result.content if c.type == "text")


def test_get_score_names_bars_as_printed():
    async def scenario(c, mock):
        text = text_of(await c.call_tool("get_score", {}))
        assert "% bar 0" in text and "% bar 4" in text
        assert "% m." not in text
        assert "Bars: 0-4" in text and "Bars shown: 0-4" in text

    run_with_mock(scenario, pickup_score())


def test_get_score_reads_from_a_printed_bar():
    async def scenario(c, mock):
        text = text_of(
            await c.call_tool(
                "get_score", {"start_measure": 2, "end_measure": 3}
            )
        )
        assert "Bars shown: 2-3" in text
        (request,) = [m for m in mock.commands if m["action"] == "getScore"]
        assert (
            request["params"]["startMeasure"],
            request["params"]["endMeasure"],
        ) == (3, 4)

    run_with_mock(scenario, pickup_score())


def test_a_number_printed_twice_is_asked_about():
    score = patterned_score("ABCDE")
    score.irregular = {3}  # a split bar: bars 1, 2, 3, 3, 4

    async def scenario(c, mock):
        result = await c.call_tool(
            "get_score", {"start_measure": 3}, raise_on_error=False
        )
        assert result.is_error
        assert "Bar 3 is printed twice" in result.content[0].text
        assert "3a" in result.content[0].text and "3b" in result.content[0].text
        text = text_of(
            await c.call_tool(
                "get_score", {"start_measure": "3b", "end_measure": "3b"}
            )
        )
        assert "% bar 3b" in text

    run_with_mock(scenario, score)


def test_a_bar_that_is_not_printed_is_refused():
    async def scenario(c, mock):
        result = await c.call_tool(
            "get_score", {"start_measure": 9}, raise_on_error=False
        )
        assert result.is_error
        assert "There is no bar 9: the score's bars are 0-4" in (
            result.content[0].text
        )

    run_with_mock(scenario, pickup_score())


def test_gaps_in_the_numbering_are_shown():
    score = patterned_score("ABCD")
    score.no_offsets = {3: 2}  # numbered as played: bars 1, 2, 5, 6

    async def scenario(c, mock):
        text = text_of(await c.call_tool("get_score", {}))
        assert "Bars: 1-2, 5-6," in text
        result = await c.call_tool(
            "get_score", {"start_measure": 3}, raise_on_error=False
        )
        assert "There is no bar 3: the score's bars are 1-2, 5-6" in (
            result.content[0].text
        )

    run_with_mock(scenario, score)


RANGE_TOOLS = [
    ("color_range", {}, "colorRange"),
    ("clear_color", {}, "colorRange"),
    ("highlight_bars", {}, "addHighlight"),
    ("highlight_notes", {}, "highlightNotes"),
    ("highlight_symbols", {}, "highlightSymbols"),
    ("highlight_markings", {}, "highlightMarkings"),
    ("remove_annotations", {}, "removeAnnotations"),
    ("add_articulation", {}, "addArticulation"),
    ("remove_articulations", {}, "removeArticulations"),
    ("ghost_notes", {}, "ghostNotes"),
    ("beam_over_rests", {}, "beamOverRests"),
    ("clear_highlights", {}, "clearHighlights"),
]


@pytest.mark.parametrize("tool, extra, action", RANGE_TOOLS)
def test_range_tools_take_printed_bars(tool, extra, action):
    async def scenario(c, mock):
        await c.call_tool(tool, {"start_measure": 1, "end_measure": 2, **extra})
        (request,) = [m for m in mock.commands if m["action"] == action]
        params = request["params"]
        assert (params["startMeasure"], params["endMeasure"]) == (2, 3)

    run_with_mock(scenario, pickup_score())


@pytest.mark.parametrize(
    "tool, args, action",
    [
        ("add_text", {"text": "cue"}, "addText"),
        ("add_label", {"text": "Fill"}, "addLabel"),
        ("go_to_measure", {}, "goToMeasure"),
        ("set_tempo", {"bpm": 90}, "setTempo"),
    ],
)
def test_bar_tools_take_a_printed_bar(tool, args, action):
    async def scenario(c, mock):
        result = await c.call_tool(tool, {"measure": 1, **args})
        (request,) = [m for m in mock.commands if m["action"] == action]
        assert request["params"]["measure"] == 2
        assert "measure 2" not in text_of(result)

    run_with_mock(scenario, pickup_score())


def test_whole_score_tools_run_from_the_pickup_to_the_end():
    async def scenario(c, mock):
        await c.call_tool("clear_highlights", {})
        (request,) = [
            m for m in mock.commands if m["action"] == "clearHighlights"
        ]
        assert (
            request["params"]["startMeasure"],
            request["params"]["endMeasure"],
        ) == (1, 5)

    run_with_mock(scenario, pickup_score())


def test_plugin_messages_name_bars_as_printed():
    async def scenario(c, mock):
        result = await c.call_tool(
            "delete_measures", {"start_measure": 1, "end_measure": 2}
        )
        assert "Deleted bars 1-2" in text_of(result)

    run_with_mock(scenario, pickup_score())


@pytest.mark.parametrize(
    "tool, args, action, expected",
    [
        (
            "set_repeat_barlines",
            {"start_measure": 1, "end_measure": 2},
            "setRepeatBarlines",
            {"startMeasure": 2, "endMeasure": 3},
        ),
        (
            "add_volta",
            {"start_measure": 3},
            "addVolta",
            {"startMeasure": 4, "endMeasure": 4},
        ),
        (
            "prepare_measure_repeat",
            {"start_measure": 2},
            "selectMeasures",
            {"startMeasure": 3, "endMeasure": 3},
        ),
        (
            "add_rehearsal_mark",
            {"measure": 0, "text": "A"},
            "addRehearsalMark",
            {"measure": 1},
        ),
        (
            "set_measure_number",
            {"measure": 2, "add_to_number": 0},
            "setMeasureNumbering",
            {"measure": 3},
        ),
        (
            "number_bars_as_played",
            {"exclude_from_count": [0]},
            "numberAsPlayed",
            {"exclude": [1]},
        ),
        (
            "label_section_counts",
            {"counts": [{"measure": 3, "text": "4"}]},
            "addSectionCounts",
            {"counts": [{"measure": 4, "text": "4"}]},
        ),
    ],
)
def test_structure_tools_take_printed_bars(tool, args, action, expected):
    async def scenario(c, mock):
        await c.call_tool(tool, args)
        (request,) = [m for m in mock.commands if m["action"] == action]
        assert {k: request["params"][k] for k in expected} == expected

    run_with_mock(scenario, pickup_score())


def test_repeated_passages_are_given_in_printed_bars():
    score = patterned_score("EABCABCF")
    score.irregular = {1}  # printed 0-7

    async def scenario(c, mock):
        result = (
            await c.call_tool("find_repeated_measures", {"highlight": True})
        ).data
        assert result["measures_analysed"] == ["0", "7"]
        (passage,) = result["passages"]
        assert (passage["start"], passage["end"]) == ("1", "3")
        assert passage["duplicate_measures"] == ["4", "6"]
        assert passage["times"] == 2 and passage["saves_measures"] == 3
        assert passage["apply"] == [
            "delete_measures(4, 6)",
            "set_repeat_barlines(1, 3, play_count=2)",
        ]
        assert (
            "duplicate of bars 1-3" in result["highlight_legend"][-1]["meaning"]
        )
        colored = {tick for _, tick, _ in mock.score.colors}
        assert min(colored) == 4 * 1920  # position 5, printed bar 4

        # the suggested calls are valid input as they are
        await c.call_tool(
            "delete_measures", {"start_measure": 4, "end_measure": 6}
        )
        await c.call_tool(
            "set_repeat_barlines", {"start_measure": 1, "end_measure": 3}
        )
        assert mock.score.num_measures == 5
        assert mock.score.repeats[2]["start"] and mock.score.repeats[4]["end"]

    run_with_mock(scenario, score)


def test_analysis_reads_from_a_printed_bar():
    async def scenario(c, mock):
        await c.call_tool(
            "find_repeated_measures", {"start_measure": 1, "end_measure": 3}
        )
        (request,) = [m for m in mock.commands if m["action"] == "getScore"]
        assert request["params"]["startMeasure"] == 2
        result = (
            await c.call_tool(
                "find_repeated_measures", {"start_measure": 1, "end_measure": 3}
            )
        ).data
        assert result["measures_analysed"] == ["1", "3"]

    run_with_mock(scenario, pickup_score())


def drum_pickup_score(pattern):
    score = patterned_score(pattern)
    score.drum_staves = {0}
    score.part_names[0] = "Drum Kit"
    score.irregular = {1}
    return score


def test_groove_sections_are_given_in_printed_bars():
    async def scenario(c, mock):
        result = (await c.call_tool("find_groove_sections", {})).data
        (staff,) = result["staves"]
        sections = staff["sections"]
        groove = [s for s in sections if s["groove_bar"] == "1"]
        assert groove, sections
        assert groove[0]["exact"] == ["2", "3", "4"]
        assert groove[0]["proposed_repeat_signs"] == [
            {"start": "2", "end": "4", "bars": 1}
        ]
        assert staff["road_map"] == [
            "Bar 0: groove bar 0",
            "Bars 1-5: groove bar 1, 3 exact copies, fill 5, collapse 1-4 to 1 x4",
        ]
        assert staff["apply_exact_copies"]["groups"] == [
            {"start": "2", "end": "4", "bars": 1}
        ]

    run_with_mock(scenario, drum_pickup_score("BAAAAC"))


def test_song_structure_names_printed_bars():
    score = drum_pickup_score("DAAAABBBBC")
    score.markings += [
        {
            "staff": 0,
            "startTick": 5 * score.measure_ticks,
            "name": "RehearsalMark",
            "text": "Verse",
        },
    ]

    async def scenario(c, mock):
        outline = (await c.call_tool("song_structure", {})).data
        start, verse = outline["sections"]
        assert (start["first_bar"], start["last_bar"]) == ("0", "4")
        assert start["not_counted"] == ["0"]
        assert (verse["first_bar"], verse["last_bar"]) == ("5", "9")
        assert verse["bars_played"] == 5
        assert [f["bar"] for f in verse["fills"]] == ["9"]
        assert outline["suggested_rows"][1]["fill"].startswith("bar 9 (")
        assert [g["first_bar"] for g in outline["grooves"]] == ["1", "5"]

    run_with_mock(scenario, score)


def test_collapse_to_repeat_takes_printed_bars():
    async def scenario(c, mock):
        result = (
            await c.call_tool("collapse_to_repeat", {"start": 1, "end": 4})
        ).data
        assert mock.score.repeats[2] == {"start": True, "end": True, "count": 4}
        assert mock.score.num_measures == 3
        assert result["message"].startswith("Bar 1 now plays 4 times; bars 2-4")

    run_with_mock(scenario, drum_pickup_score("BAAAAC"))


def test_sequence_steps_take_printed_bars():
    async def scenario(c, mock):
        await c.call_tool(
            "processSequence",
            {
                "sequence": [
                    {"action": "goToMeasure", "params": {"measure": "0"}},
                    {
                        "action": "colorRange",
                        "params": {
                            "startMeasure": 1,
                            "endMeasure": 2,
                            "color": "#ff0000",
                        },
                    },
                ]
            },
        )
        (request,) = [
            m for m in mock.commands if m["action"] == "processSequence"
        ]
        steps = request["params"]["sequence"]
        assert steps[0]["params"]["measure"] == 1
        assert (
            steps[1]["params"]["startMeasure"],
            steps[1]["params"]["endMeasure"],
        ) == (2, 3)
        result = await c.call_tool(
            "processSequence",
            {"sequence": [{"action": "goToMeasure", "params": {"measure": 7}}]},
            raise_on_error=False,
        )
        assert result.is_error and "There is no bar 7" in result.content[0].text

    run_with_mock(scenario, pickup_score())


def test_file_edits_take_printed_bars(tmp_path, monkeypatch):
    from test_integration import bass_staff_repeat, jazz_copy, open_in_mock

    path = jazz_copy(tmp_path, monkeypatch)
    score = open_in_mock(path)
    score.irregular = {1}  # printed 0-7

    async def scenario(c, mock):
        result = (
            await c.call_tool(
                "apply_measure_repeats",
                {
                    "staff": 1,
                    "groups": [{"start": 2, "end": 3}],
                    "score_path": str(path),
                },
            )
        ).data
        assert [g["start"] for g in result["applied"]] == ["2", "3"]
        assert (
            bass_staff_repeat(path, 3) == "1"
            and bass_staff_repeat(path, 4) == "1"
        )
        assert bass_staff_repeat(path, 2) is None

        refused = await c.call_tool(
            "simplify_roll",
            {
                "staff": 0,
                "start_measure": 8,
                "end_measure": 8,
                "score_path": str(path),
            },
            raise_on_error=False,
        )
        assert refused.is_error
        assert (
            "There is no bar 8: the score's bars are 0-7"
            in refused.content[0].text
        )

    run_with_mock(scenario, score)
