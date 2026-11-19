"""Repeat and song structure tools: find repeated material and mark it."""

import re
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import (
    Annotated,
    Any,
    Dict,
    List,
    Literal,
    Optional,
    Tuple,
    TypeVar,
    cast,
)

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from ..bars import BAR_HELP, Bar, BarNumbers, bar_numbers, send
from ..client import MuseScoreClient
from ..mscz import ScoreFile, ScoreFileError
from ..mscz.locate import (
    SCORE_ID_TAG,
    backup_dir,
    backup_score,
    locate_open_score,
    new_score_id,
)
from ..mscz.parts import keep_parts
from ..utils.repetition import (
    core_fingerprint,
    find_repeats,
    staff_fingerprints,
)
from ..utils.sections import find_sections
from ..utils.sections import song_structure as analyse_structure
from .formatting import range_params
from .score_file import (
    KNOWN_PATHS,
    PART_SOURCES,
    open_score_path,
    reopen_in_place,
)

FETCH_CHUNK = 16
PASSAGE_COLORS = [
    "#1f77b4",
    "#2ca02c",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#17becf",
]
MEASURE_REPEAT_COLOR = "#ff7f0e"


def _contiguous(indices: List[int]) -> List[List[int]]:
    """Group staff indices into runs of consecutive staves.

    Args:
        indices (List[int]): The staff indices, in any order.

    Returns:
        runs (List[List[int]]): The [first, last] of each run.
    """
    runs: List[List[int]] = []
    for idx in sorted(indices):
        if runs and runs[-1][1] + 1 == idx:
            runs[-1][1] = idx
        else:
            runs.append([idx, idx])
    return runs


BAR_FIELDS = {
    "start",
    "end",
    "from",
    "to",
    "bar",
    "groove_bar",
    "first_bar",
    "last_bar",
}
"""Fields of an analysis result that hold one bar's position."""

BAR_LIST_FIELDS = {
    "duplicate_measures",
    "first_ending",
    "second_ending",
    "keep",
    "exact",
    "fills",
    "already_repeat_signs",
    "not_counted",
}
"""Fields of an analysis result that hold a list of bars' positions."""


Result = TypeVar("Result")


def printed_bars(value: Result, bars: BarNumbers) -> Result:
    """Rename the bars in an analysis result as printed.

    Only the fields that hold bars (BAR_FIELDS, BAR_LIST_FIELDS) change; counts
    such as "times", "play_count", "phrase_bars" or "bars_played" stay numbers.

    Args:
        value (Result): A result of find_repeats, find_sections or
            song_structure, bars by position.
        bars (BarNumbers): The score's printed bar numbers.

    Returns:
        value (Result): The same result, bars as printed.
    """

    def bar(item: object) -> object:
        if isinstance(item, int) and not isinstance(item, bool):
            return bars.label(item)
        return rename(item)

    def rename(item: object) -> object:
        if isinstance(item, dict):
            return {
                key: bar(field)
                if key in BAR_FIELDS
                else [bar(i) for i in field]
                if key in BAR_LIST_FIELDS and isinstance(field, list)
                else rename(field)
                for key, field in item.items()
            }
        if isinstance(item, list):
            return [rename(i) for i in item]
        return item

    return cast(Result, rename(value))


def _arg(bar: str) -> str:
    """Write a printed bar as a tool call argument: 12, or "12b" quoted."""
    return bar if re.fullmatch(r"-?\d+", bar) else f'"{bar}"'


def _apply_steps(passage: Dict) -> List[str]:
    """List the tool calls that compress one repeated passage.

    The calls are ordered so that the bars in the later calls are still numbered
    so when they run: they all come before the deleted bars.

    Args:
        passage (Dict): A passage from find_repeats, bars as printed: a "repeat"
            or a "repeat_with_endings".

    Returns:
        steps (List[str]): The tool calls, e.g. "delete_measures(9, 16)".
    """
    dup_first, dup_last = (_arg(b) for b in passage["duplicate_measures"])
    start, end = _arg(passage["start"]), _arg(passage["end"])
    if passage["type"] == "repeat":
        return [
            f"delete_measures({dup_first}, {dup_last})",
            f"set_repeat_barlines({start}, {end}, play_count={passage['times']})",
        ]
    first_ending = [_arg(b) for b in passage["first_ending"]]
    second_ending = [_arg(b) for b in passage["second_ending"]]
    return [
        f"add_volta({second_ending[0]}, {second_ending[1]}, endings=[2])",
        f"delete_measures({dup_first}, {dup_last})",
        f"add_volta({first_ending[0]}, {first_ending[1]}, endings=[1])",
        f"set_repeat_barlines({start}, {first_ending[1]})",
    ]


async def fetch_measures(
    client: MuseScoreClient,
    start_measure: int,
    end_measure: Optional[int],
    staves: Optional[List[int]],
) -> Tuple[List[Dict], List[Dict]]:
    """Read a range of measures from the plugin, in chunks.

    Reading FETCH_CHUNK measures at a time keeps each reply small, so large
    scores work too. Measures are addressed by position here, as the analysis
    works on positions; the tools give the results as printed.

    Args:
        client (MuseScoreClient): The client to the plugin.
        start_measure (int): The first measure's position, 1-based.
        end_measure (Optional[int]): The last measure's position, 1-based and
            inclusive. Defaults to the end of the score.
        staves (Optional[List[int]]): The staves to read, 0-based. Defaults to
            all staves.

    Returns:
        result (Tuple[List[Dict], List[Dict]]): The measures, and the staff
            info.

    Raises:
        ToolError: If the plugin reports an error.
    """
    params: Dict[str, Any] = {
        "startMeasure": start_measure,
        "endMeasure": start_measure + FETCH_CHUNK - 1,
    }
    if staves:
        params["staves"] = staves
    analysis = (await client.request("getScore", params))["analysis"]
    total = analysis.get("numMeasures", 0)
    last = min(end_measure, total) if end_measure is not None else total
    measures = [m for m in analysis.get("measures", []) if m["measure"] <= last]

    next_start = params["endMeasure"] + 1
    while next_start <= last:
        chunk = {
            **params,
            "startMeasure": next_start,
            "endMeasure": min(next_start + FETCH_CHUNK - 1, last),
        }
        measures.extend(
            (await client.request("getScore", chunk))["analysis"].get(
                "measures", []
            )
        )
        next_start = chunk["endMeasure"] + 1
    return measures, analysis.get("staves", [])


def incomplete_measures(measures: List[Dict]) -> List[Dict]:
    """Find bars whose notes and rests don't add up to the bar's length.

    Voice 1 must fill the bar exactly; other voices may not be longer than it.
    Measures without a length are skipped.

    Args:
        measures (List[Dict]): The measures from the plugin's analysis.

    Returns:
        incomplete (List[Dict]): Per bad bar and staff: "measure", "staff",
            "found_ticks" (per voice) and "expected_ticks".
    """
    out = []
    for measure in measures:
        length = measure.get("durationTicks")
        if not length:  # without a length nothing can be checked (a length of 0 was never reported either)
            continue
        for key, elements in (measure.get("elements") or {}).items():
            totals: Dict[int, int] = {}
            for element in elements:
                if element.get("name") in ("Chord", "Rest", "MeasureRepeat"):
                    voice = element.get("voice", 0)
                    totals[voice] = totals.get(voice, 0) + element.get(
                        "durationTicks", 0
                    )
            bad = {
                v: t
                for v, t in totals.items()
                if t > length or (v == 0 and t != length)
            }
            if length and bad:
                out.append(
                    {
                        "measure": measure["measure"],
                        "staff": int(key.replace("staff", "")),
                        "found_ticks": bad,
                        "expected_ticks": length,
                    }
                )
    return out


def _road_map_line(section: Dict) -> str:
    """Write one line of the section map.

    Args:
        section (Dict): A section from find_sections, bars as printed.

    Returns:
        line (str): E.g. "Bars 6-13: groove bar 6, 5 exact copies, near 9, fill
            13", followed by its runs.
    """
    parts = [f"groove bar {section['groove_bar']}"]
    if section["exact"]:
        parts.append(
            f"{len(section['exact'])} exact cop{'y' if len(section['exact']) == 1 else 'ies'}"
        )
    if section["near"]:
        parts.append(
            "near " + ", ".join(str(n["bar"]) for n in section["near"])
        )
    if section["fills"]:
        parts.append("fill " + ", ".join(str(b) for b in section["fills"]))
    for run in section.get("runs", []):
        keep = (
            f"{run['keep'][0]}"
            if run["phrase_bars"] == 1
            else f"{run['keep'][0]}-{run['keep'][1]}"
        )
        text = f"collapse {run['start']}-{run['end']} to {keep} x{run['play_count']}"
        crash = run["crash_on_1"]
        if crash.get("legend"):
            text += f" ({crash['mark']} {crash['legend']})"
        elif crash.get("pattern") == "irregular":
            text += f" (irregular crashes, passes {crash['run_bars']})"
        if run["dropped"]:
            text += f", drops differences in bars {', '.join(str(d['bar']) for d in run['dropped'])}"
        parts.append(text)
    bars = (
        f"Bar {section['start']}"
        if section["start"] == section["end"]
        else f"Bars {section['start']}-{section['end']}"
    )
    return f"{bars}: " + ", ".join(parts)


def by_position(measures: List[Dict]) -> List[Dict]:
    """Number measures by position, for an analysis that names bars by number.

    song_structure names bars by their "number" (as printed, without the letter
    of a number printed twice); with the position in its place, the tool can
    name them as printed itself.

    Args:
        measures (List[Dict]): The measures from the plugin's analysis.

    Returns:
        measures (List[Dict]): Copies of them, "number" set to the position.
    """
    return [{**m, "number": m["measure"]} for m in measures]


def setup_structure_tools(mcp: FastMCP, client: MuseScoreClient) -> None:
    """Register the repeat, section and song structure tools.

    Args:
        mcp (FastMCP): The server to register the tools on.
        client (MuseScoreClient): The client the tools send their commands
            through.
    """

    async def staff_header() -> List[Dict]:
        """Read the staff info of the open score, without the notes.

        Returns:
            staves (List[Dict]): The info of each staff.
        """
        analysis = (
            await client.request(
                "getScore",
                {"startMeasure": 1, "endMeasure": 1, "includeElements": False},
            )
        )["analysis"]
        return analysis.get("staves", [])

    async def renumber(
        bars: BarNumbers, action: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Run a plugin command that renumbers bars, its reply as printed after.

        Args:
            bars (BarNumbers): The bar numbers before the command, for its
                errors.
            action (str): The plugin action.
            params (Dict[str, Any]): Its parameters, measures by position.

        Returns:
            result (Dict[str, Any]): The plugin's result, bars as now printed.

        Raises:
            ToolError: If the plugin reports an error, bars as printed before.
        """
        try:
            result = await client.request(action, params)
        except ToolError as error:
            raise ToolError(bars.relabel_text(str(error))) from error
        return (await bar_numbers(client)).relabel(result)

    @mcp.tool(
        description=(
            "Find repeated material in the score. Returns (1) per-staff bars that repeat the previous 1, 2 or 4 bars, "
            "candidates for measure-repeat signs (these declutter the page but keep the length), and (2) whole-score "
            "passages played again right away, candidates for repeat barlines and 1st/2nd endings (these shorten the "
            "score once the duplicate measures are deleted). Each passage lists the tool calls that apply it. "
            "Reads the score in small chunks, so it works on large scores. Bars are as printed in the score as it "
            "is now: apply passages from the last one backwards."
        ),
        tags={"structure"},
    )
    async def find_repeated_measures(
        start_measure: Annotated[
            Optional[Bar],
            f"First bar to analyse, {BAR_HELP}. Defaults to the first bar.",
        ] = None,
        end_measure: Annotated[
            Optional[Bar],
            "Last bar to analyse, inclusive. Defaults to the end of the score.",
        ] = None,
        staves: Annotated[
            Optional[List[int]],
            "Staff indices to analyse (0-based). Defaults to all staves.",
        ] = None,
        highlight: Annotated[
            bool,
            "Also color the results in the score: duplicate measures of each passage in a passage color, "
            "per-staff measure repeats in orange. Undo or clear_color removes it.",
        ] = False,
    ):
        bars = await bar_numbers(client)
        first, last = bars.bounds(start_measure, end_measure, to_end=True)
        measures, staff_info = await fetch_measures(client, first, last, staves)
        staff_names = [st["name"] for st in staff_info]
        found = find_repeats(measures, staff_names)
        passages = printed_bars(found["passages"], bars)
        for passage in passages:
            passage["apply"] = _apply_steps(passage)

        result = {
            "measures_analysed": [
                bars.label(measures[0]["measure"]),
                bars.label(measures[-1]["measure"]),
            ]
            if measures
            else [],
            "staves_analysed": [
                st.get("index", i) for i, st in enumerate(staff_info)
            ],
            "passages": passages,
            "measure_repeats": printed_bars(found["measure_repeats"], bars),
            "notes": [
                "Apply passages from the last one backwards: delete_measures moves later bars up.",
                "measure_repeats use the bars as printed now; re-run this tool after deleting bars.",
                "Place measure-repeat signs with apply_measure_repeats (one call per staff, all groups at once).",
            ],
        }

        if highlight:
            analysed = result["staves_analysed"]
            legend = []
            for group in found["measure_repeats"]:
                for first, last_staff in _contiguous(group["staves"]):
                    await client.request(
                        "colorRange",
                        {
                            **range_params(
                                group["from"], group["to"], first, last_staff
                            ),
                            "color": MEASURE_REPEAT_COLOR,
                        },
                    )
            if found["measure_repeats"]:
                legend.append(
                    {
                        "color": MEASURE_REPEAT_COLOR,
                        "meaning": "per-staff measure repeat",
                    }
                )
            for i, passage in enumerate(found["passages"]):
                color = PASSAGE_COLORS[i % len(PASSAGE_COLORS)]
                dup_first, dup_last = passage["duplicate_measures"]
                for first, last_staff in _contiguous(analysed):
                    await client.request(
                        "colorRange",
                        {
                            **range_params(
                                dup_first, dup_last, first, last_staff
                            ),
                            "color": color,
                        },
                    )
                legend.append(
                    {
                        "color": color,
                        "meaning": f"duplicate of bars {bars.span(passage['start'], passage['end'])} (passage {i + 1})",
                    }
                )
            result["highlight_legend"] = legend

        return result

    @mcp.tool(
        description=(
            "Put start and end repeat barlines around a range of bars, or remove them. "
            "Needs MuseScore 4.6 or newer; on older versions the measures are selected and the reply "
            "says which palette items to click."
        ),
        tags={"structure"},
    )
    async def set_repeat_barlines(
        start_measure: Annotated[
            Bar, f"Bar that gets the start repeat, {BAR_HELP}"
        ],
        end_measure: Annotated[Bar, "Bar that gets the end repeat"],
        play_count: Annotated[
            int, "How many times the passage is played in total"
        ] = 2,
        clear: Annotated[
            bool, "True to remove the repeat barlines instead of adding them"
        ] = False,
    ):
        bars = await bar_numbers(client)
        first, last = bars.bounds(start_measure, end_measure)
        return await send(
            client,
            bars,
            "setRepeatBarlines",
            {
                "startMeasure": first,
                "endMeasure": last,
                "playCount": play_count,
                "clear": clear,
            },
        )

    @mcp.tool(
        description=(
            "Add a volta (1st/2nd ending bracket) over a range of bars. Experimental: the plugin API has no "
            "dedicated volta call, so check the result; if it fails, the measures are selected and the reply "
            "says which palette item to click."
        ),
        tags={"structure"},
    )
    async def add_volta(
        start_measure: Annotated[Bar, f"First bar under the volta, {BAR_HELP}"],
        end_measure: Annotated[
            Optional[Bar],
            "Last bar under the volta, inclusive. Defaults to start_measure.",
        ] = None,
        endings: Annotated[
            List[int],
            "Which repeat passes play this ending, e.g. [1] for a first ending, [2] for a second",
        ] = [1],
        text: Annotated[
            Optional[str],
            'Volta label. Defaults to the endings, e.g. "1." or "1, 2."',
        ] = None,
    ):
        bars = await bar_numbers(client)
        first, last = bars.bounds(start_measure, end_measure)
        params = {"startMeasure": first, "endMeasure": last, "endings": endings}
        if text:
            params["text"] = text
        return await send(client, bars, "addVolta", params)

    @mcp.tool(
        description=(
            "Add a repeat marker or jump to a bar, as from MuseScore's Repeats & jumps palette: 'segno', 'coda', "
            "'to_coda' (the words To Coda), 'to_coda_symbol' (To and the coda sign), 'fine', or a jump: 'dc', 'dc_al_fine', 'dc_al_coda', 'ds', 'ds_al_fine', 'ds_al_coda'. "
            "Segno and Coda go on the bar they start; To Coda, Fine and the jumps on the bar they end. A jump's "
            "reply lists under `missing` the markers it needs that the score doesn't have yet (D.S. al Coda needs "
            "a Segno, a To Coda and a Coda): add them too, or ask the user where they go. A marker the bar "
            "already has is refused. Remove with remove_annotations (kinds 'markers', 'jumps')."
        ),
        tags={"structure"},
    )
    async def add_marker(
        measure: Annotated[Bar, f"The bar, {BAR_HELP}"],
        marker: Annotated[
            Literal[
                "segno",
                "coda",
                "to_coda",
                "to_coda_symbol",
                "fine",
                "dc",
                "dc_al_fine",
                "dc_al_coda",
                "ds",
                "ds_al_fine",
                "ds_al_coda",
            ],
            "The marker or jump",
        ],
    ):
        bars = await bar_numbers(client)
        return await send(
            client,
            bars,
            "addMarker",
            {"measure": bars.position(measure), "marker": marker},
        )

    @mcp.tool(
        description=(
            "Set the chord symbol on a beat: adds one, or changes the one there (the reply's `replaced` gives the old "
            "name). MuseScore reads the name as when typed, e.g. 'Bb7', 'F#m7b5', 'C/E'. A chord symbol sits on a note "
            "or rest: on a beat that none starts on (e.g. inside a half note) one already there can be changed, but a new "
            "one can't be added (a plugin limit): that is refused, with the beats that have one, and the user can add it "
            "by hand. "
            "Remove with remove_annotations(kinds=['chord_symbols'])."
        ),
        tags={"notation"},
    )
    async def set_chord_symbol(
        measure: Annotated[Bar, f"The bar, {BAR_HELP}"],
        chord: Annotated[str, "The chord's name, e.g. 'Cm7' or 'G7/B'"],
        beat: Annotated[
            float,
            "Beat (1-based) by the time signature's denominator; 3.5 is the 'and' of beat 3",
        ] = 1,
        staff: Annotated[int, "Staff (0-based)"] = 0,
    ):
        bars = await bar_numbers(client)
        return await send(
            client,
            bars,
            "setChordSymbol",
            {
                "measure": bars.position(measure),
                "chord": chord,
                "beat": beat,
                "staff": staff,
            },
        )

    @mcp.tool(
        description=(
            "Move a chord symbol to another beat or bar, keeping its name. Refused when its name isn't readable (a "
            "chord symbol imported from MusicXML, until the score is saved, closed and opened again; saving alone is "
            "not enough): ask the user for the name, "
            "then set_chord_symbol at the new place and remove the old one. A target beat that already has a chord "
            "symbol, or that no note or rest starts on (a plugin can't add one there), is refused too."
        ),
        tags={"notation"},
    )
    async def move_chord_symbol(
        measure: Annotated[Bar, f"The chord symbol's bar, {BAR_HELP}"],
        to_measure: Annotated[Bar, "The bar to move it to"],
        beat: Annotated[float, "Its beat (1-based)"] = 1,
        to_beat: Annotated[float, "The beat to move it to (1-based)"] = 1,
        staff: Annotated[int, "Staff (0-based)"] = 0,
    ):
        bars = await bar_numbers(client)
        return await send(
            client,
            bars,
            "moveChordSymbol",
            {
                "measure": bars.position(measure),
                "toMeasure": bars.position(to_measure),
                "beat": beat,
                "toBeat": to_beat,
                "staff": staff,
            },
        )

    @mcp.tool(
        description=(
            "End a system (line), page or section after a bar, as from MuseScore's Breaks & spacers palette. A "
            "break of that kind the bar already has is refused. get_score lists breaks under [Markings]; remove "
            "them with remove_annotations(kinds=['breaks']). For a fixed number of bars on every system, use "
            "set_measures_per_system."
        ),
        tags={"layout"},
    )
    async def add_break(
        measure: Annotated[Bar, f"The bar the break comes after, {BAR_HELP}"],
        kind: Annotated[
            Literal["line", "page", "section"],
            "'line' (system break), 'page' or 'section'",
        ] = "line",
    ):
        bars = await bar_numbers(client)
        return await send(
            client,
            bars,
            "addBreak",
            {"measure": bars.position(measure), "kind": kind},
        )

    @mcp.tool(
        description=(
            "Put the same number of bars on every system over a range of bars (the whole score by default). "
            "method 'locks' (default) works as Format > Measures per system: system locks, which keep each "
            "system's bars when bars before them change. method 'breaks' puts a system break after every N bars "
            "instead (shown by get_score, and fixed to their bars). Either way the range's system breaks and "
            "locks are removed first, so the result is exactly N bars a system; per_system=0 only removes them, "
            "back to MuseScore's own layout. Page and section breaks stay. The reply's `systems` gives each "
            "system's first and last bar afterwards; render a page to see it."
        ),
        tags={"layout"},
    )
    async def set_measures_per_system(
        per_system: Annotated[
            int, "Bars on each system; 0 removes the locks and system breaks"
        ],
        start_measure: Annotated[
            Optional[Bar], "First bar. Defaults to the first bar of the score."
        ] = None,
        end_measure: Annotated[
            Optional[Bar],
            "Last bar, inclusive. Defaults to the end of the score.",
        ] = None,
        method: Annotated[
            Literal["locks", "breaks"], "'locks' (default) or 'breaks'"
        ] = "locks",
    ):
        if per_system < 0:
            raise ToolError("per_system must be 0 or more")
        bars = await bar_numbers(client)
        first, last = bars.bounds(start_measure, end_measure, to_end=True)
        return await send(
            client,
            bars,
            "setMeasuresPerSystem",
            {
                "startMeasure": first,
                "endMeasure": last,
                "perSystem": per_system,
                "method": method,
            },
        )

    @mcp.tool(
        description=(
            "Make bars wider or narrower, as Format > Stretch does: 1 is MuseScore's own width, 1.5 half as wide "
            "again, 0.8 narrower. Wider bars can push the next bars onto the next system; render to check."
        ),
        tags={"layout"},
    )
    async def set_measure_stretch(
        stretch: Annotated[float, "1 is MuseScore's own width; more than 0"],
        start_measure: Annotated[Bar, f"First bar, {BAR_HELP}"],
        end_measure: Annotated[
            Optional[Bar], "Last bar, inclusive. Defaults to start_measure."
        ] = None,
    ):
        if stretch <= 0:
            raise ToolError("stretch must be more than 0")
        bars = await bar_numbers(client)
        first, last = bars.bounds(start_measure, end_measure)
        return await send(
            client,
            bars,
            "setMeasureStretch",
            {"startMeasure": first, "endMeasure": last, "stretch": stretch},
        )

    @mcp.tool(
        description=(
            "Prepare measure-repeat signs: selects the measures that should become repeat signs, on the given staves, "
            "and returns what to click in MuseScore. The plugin API cannot place measure-repeat signs itself."
        ),
        tags={"structure"},
    )
    async def prepare_measure_repeat(
        start_measure: Annotated[
            Bar,
            f"First bar to turn into a repeat sign, {BAR_HELP}; it repeats the bars before it",
        ],
        end_measure: Annotated[
            Optional[Bar],
            "Last bar, inclusive. Defaults to the size of the sign from start_measure on.",
        ] = None,
        bars: Annotated[
            Literal[1, 2, 4], "Size of the measure-repeat sign: 1, 2 or 4 bars"
        ] = 1,
        first_staff: Annotated[int, "First staff (0-based)"] = 0,
        last_staff: Annotated[
            Optional[int],
            "Last staff (0-based, inclusive). Defaults to the last staff.",
        ] = None,
    ):
        numbers = await bar_numbers(client)
        first, last = numbers.bounds(start_measure, end_measure)
        if end_measure is None:
            last = first + bars - 1
        result = await send(
            client,
            numbers,
            "selectMeasures",
            range_params(first, last, first_staff, last_staff),
        )
        sign = "measure repeat" if bars == 1 else f"{bars}-measure repeat"
        result["next_step"] = (
            f"In MuseScore, with the selection still active, click the {sign} sign in the Repeats & jumps palette. "
            "The selected measures' content is replaced by the sign."
        )
        return result

    @mcp.tool(
        description=(
            "Map the sections of a groove-based part (drums by default): for each section the groove bar, the bars "
            "that copy it exactly, near copies (with the hits that differ), and fills. Proposes measure-repeat signs "
            "for exact copies only, as ready-made apply_measure_repeats groups, and a collapse_to_repeat range for a "
            "'groove bar x N' chart. Show near copies to the user and only replace them once approved: a repeat sign "
            "deletes their differences."
        ),
        tags={"structure"},
    )
    async def find_groove_sections(
        staves: Annotated[
            Optional[List[int]],
            "Staff indices to analyse (0-based). Defaults to the drum staves.",
        ] = None,
        start_measure: Annotated[
            Optional[Bar],
            f"First bar to analyse, {BAR_HELP}. Defaults to the first bar.",
        ] = None,
        end_measure: Annotated[
            Optional[Bar],
            "Last bar to analyse, inclusive. Defaults to the end of the score.",
        ] = None,
        tolerance: Annotated[
            float,
            "How similar (0-1, share of identical hits) a bar must be to its groove to count as a near copy",
        ] = 0.85,
    ):
        if not staves:
            staves = [
                st["index"] for st in await staff_header() if st.get("isDrums")
            ]
            if not staves:
                raise ToolError(
                    "No drum staff found in the score; pass the staves to analyse"
                )

        bars = await bar_numbers(client)
        first, last = bars.bounds(start_measure, end_measure, to_end=True)
        measures, staff_info = await fetch_measures(client, first, last, staves)
        result = []
        for st in staff_info:
            sections = printed_bars(
                find_sections(measures, st["name"], tolerance), bars
            )
            groups = [
                g for sec in sections for g in sec["proposed_repeat_signs"]
            ]
            result.append(
                {
                    "staff": st.get("index"),
                    "name": st.get("partName") or st["name"],
                    "road_map": [_road_map_line(sec) for sec in sections],
                    "sections": sections,
                    "apply_exact_copies": {
                        "staff": st.get("index"),
                        "groups": groups,
                    }
                    if groups
                    else None,
                }
            )
        return {
            "staves": result,
            "notes": [
                "apply_exact_copies can be passed to apply_measure_repeats as is.",
                "Near copies are not included: ask the user per section. A bar can only become a 1-bar sign if it "
                "equals the bar before it, so approving a near bar also makes the exact bars right after it eligible.",
                "For a 'groove bar x N' chart, collapse each section's runs with collapse_to_repeat(start, end, "
                "phrase_bars), in a score that contains only this part (make_part_score), from the last run "
                "backwards. A run's copies only differ by ghost notes and crashes on beat 1 (crash_on_1 gives the "
                "mark and legend); 'dropped' lists the hits that collapsing removes.",
            ],
        }

    @mcp.tool(
        description=(
            "Outline the song for a structure page: the sections (from the rehearsal marks) with how many bars each "
            "lasts as played (repeats counted), the grooves in it (bars that recur, named Groove A, B... with the "
            "drums they use; hi-hat openings, crashes and ghost notes don't make a new groove) and the fills "
            "(bars that don't recur). Each section's `count` is its length in fours as drummers count it (6 -> "
            "'4+2', 12 -> '3x4', bars before the first groove bar counted on their own: '2+4+2'); bars excluded "
            "from the bar count (a count-in) are left out. suggested_rows can go to set_song_structure as they are, "
            "but give the grooves and fills musical names first (e.g. 'Verse shuffle', 'Tom fill into chorus')."
        ),
        tags={"structure"},
    )
    async def song_structure(
        staff: Annotated[
            Optional[int],
            "Staff to analyse (0-based). Defaults to the first drum staff.",
        ] = None,
        tolerance: Annotated[
            float,
            "How similar (0-1, share of identical hits) bars must be to share a groove name",
        ] = 0.8,
    ):
        if staff is None:
            drums = [
                st["index"] for st in await staff_header() if st.get("isDrums")
            ]
            staff = drums[0] if drums else 0
        bars = await bar_numbers(client)
        measures, staff_info = await fetch_measures(client, 1, None, [staff])
        if not staff_info:
            raise ToolError(f"Staff {staff} not found")
        result = printed_bars(
            analyse_structure(
                by_position(measures), staff_info[0]["name"], tolerance
            ),
            bars,
        )
        result["suggested_rows"] = [
            {
                "section": sec["section"],
                "bars": sec["bars_played"],
                "count": sec["count"],
                "groove": ", ".join(g["name"] for g in sec["grooves"]),
                "fill": "; ".join(
                    f"bar {f['bar']} ({', '.join(f['drums'])})"
                    for f in sec["fills"]
                ),
            }
            for sec in result["sections"]
        ]
        result["staff"] = staff
        return result

    @mcp.tool(
        description=(
            "Write each section's bar count (e.g. '2x4+2'). placement='label' (default, the chart style the user "
            "chose) puts it in parentheses in the section label (rehearsal mark): 'Chorus 1 (2x4)', and sets the "
            "labels to label_size points with label_clearance spaces around them, so MuseScore places and spaces "
            "them. placement='beside' writes it in bold red right of the label at the label's height (moved past a "
            "text already there or up over notes); MuseScore doesn't leave room for it between systems, so it can run "
            "into dynamics of the system above: only on request. Without counts, uses song_structure's counts (the "
            "ones already written in the labels where they still add up). Running it again replaces the counts in "
            "either form; clear=True removes them."
        ),
        tags={"formatting"},
    )
    async def label_section_counts(
        counts: Annotated[
            Optional[List[Dict[str, Any]]],
            'Counts to write: [{"measure": 8, "text": "2x4+2"}] (measure = the bar holding the section label, '
            f"{BAR_HELP}). Defaults to song_structure's counts.",
        ] = None,
        staff: Annotated[
            Optional[int],
            "Staff to analyse when counts are computed (0-based). Defaults to the first drum staff.",
        ] = None,
        placement: Annotated[
            Literal["label", "beside"],
            "In parentheses in the section label, or as red text beside it",
        ] = "label",
        color: Annotated[str, "Text color (placement='beside')"] = "#d62728",
        size: Annotated[float, "Font size in points (placement='beside')"] = 12,
        label_size: Annotated[
            Optional[float],
            "Section label font size in points (placement='label'; MuseScore's default is 14); None leaves it",
        ] = 12,
        label_clearance: Annotated[
            Optional[float],
            "Minimum space around section labels in staff spaces (placement='label'; MuseScore's default is 0.5); None leaves it",
        ] = 1,
        clear: Annotated[
            bool,
            "Remove the counts instead (at the given bars, or at every section label)",
        ] = False,
    ):
        computed = counts is None
        bars = await bar_numbers(client)
        if counts is None:
            if staff is None:
                drums = [
                    st["index"]
                    for st in await staff_header()
                    if st.get("isDrums")
                ]
                staff = drums[0] if drums else 0
            measures, staff_info = await fetch_measures(
                client, 1, None, [staff]
            )
            if not staff_info:
                raise ToolError(f"Staff {staff} not found")
            sections = analyse_structure(measures, staff_info[0]["name"])[
                "sections"
            ]
            counts = [
                {"measure": bars.label(sec["first_bar"]), "text": sec["count"]}
                for sec in sections
                if sec["section"] != "Start"
            ]
        for c in counts:
            if (
                not isinstance(c, dict)
                or not isinstance(c.get("measure"), (int, str))
                or isinstance(c.get("measure"), bool)
                or not str(c.get("text") or "").strip()
            ):
                raise ToolError(
                    f'Each count needs a measure and a text, e.g. {{"measure": 8, "text": "2x4+2"}}: {c!r}'
                )
        params = {
            "counts": [
                {
                    "measure": bars.position(c["measure"]),
                    "text": str(c["text"]).strip().strip("()").strip(),
                }
                for c in counts
            ],
            "mode": placement,
            "color": color,
            "fontSize": size,
        }
        if computed or placement == "label":
            params["clearAll"] = (
                True  # counts beside the labels left anywhere by earlier edits go too
            )
        if clear:
            params["clear"] = True
        result = await send(client, bars, "addSectionCounts", params)
        result["counts"] = bars.relabel(params["counts"])
        if placement == "label" and not clear:
            styles = {
                "rehearsalMarkFontSize": label_size,
                "rehearsalMarkMinDistance": label_clearance,
            }
            for key, value in styles.items():
                if value is not None:
                    await client.request(
                        "setStyle", {"key": key, "value": value}
                    )
            result["label_style"] = {
                k: v for k, v in styles.items() if v is not None
            }
        return result

    @mcp.tool(
        description=(
            "Collapse a run of repeated bars or phrases into one played N times: keeps the first phrase_bars bars "
            "from start, deletes the rest of the run, and puts start/end repeat barlines with a play count around "
            "the kept bars (shown as e.g. '7x'). With phrase_bars=2, bars start..end must be a 2-bar phrase "
            "repeated (e.g. 28-35 becomes 28-29 x4). This changes every staff, so use it in a score that contains "
            "only the part being charted (make_part_score). It refuses when any staff's copies differ in anything "
            "but ghost notes and crashes on beat 1, unless force=True. Later bars move up: collapse from the end of "
            "the score backwards. Needs MuseScore 4.6+."
        ),
        tags={"structure"},
    )
    async def collapse_to_repeat(
        start: Annotated[
            Bar,
            f"First bar of the run, {BAR_HELP}; the phrase starting here is kept",
        ],
        end: Annotated[Bar, "Last bar of the run, inclusive"],
        phrase_bars: Annotated[
            int,
            "Length of the repeated phrase in bars (1, 2, 4...); the run must be a whole number of phrases",
        ] = 1,
        force: Annotated[
            bool,
            "Collapse even if copies differ in more than ghost notes and crashes on beat 1 (those differences are lost)",
        ] = False,
    ):
        numbers = await bar_numbers(client)
        first, last = numbers.bounds(start, end)
        length = last - first + 1
        if phrase_bars < 1 or length < 2 * phrase_bars or length % phrase_bars:
            raise ToolError(
                f"Bars {numbers.span(first, last)} are not a whole number (at least 2) of {phrase_bars}-bar phrases"
            )
        measures, staff_info = await fetch_measures(client, first, last, None)
        differing, minor = [], []
        for st in staff_info:
            core, _ = staff_fingerprints(measures, st["name"], core_fingerprint)
            full, _ = staff_fingerprints(measures, st["name"])
            name = st.get("partName") or st["name"]
            bars = [
                measures[i]["measure"]
                for i in range(phrase_bars, len(core))
                if core[i] != core[i % phrase_bars]
            ]
            if bars:
                differing.append(
                    {
                        "staff": st.get("index"),
                        "name": name,
                        "bars": [numbers.label(b) for b in bars],
                    }
                )
            small = [
                measures[i]["measure"]
                for i in range(phrase_bars, len(full))
                if full[i] != full[i % phrase_bars]
                and measures[i]["measure"] not in bars
            ]
            if small:
                minor.append(
                    {
                        "staff": st.get("index"),
                        "name": name,
                        "bars": [numbers.label(b) for b in small],
                    }
                )
        kept_end = first + phrase_bars - 1
        if differing and not force:
            listed = "; ".join(
                f"{d['name']} (staff {d['staff']}): bar{'s' if len(d['bars']) > 1 else ''} {', '.join(d['bars'])}"
                for d in differing
            )
            phrase = (
                f"bar {numbers.label(first)}"
                if phrase_bars == 1
                else f"bars {numbers.span(first, kept_end)}"
            )
            raise ToolError(
                f"Not every phrase in {numbers.span(first, last)} is a copy of {phrase}: {listed}. "
                "Collapsing would delete those differences (kicks, snares, hats or articulations). Try a longer "
                "phrase_bars, chart a single part (make_part_score), or pass force=True after the user agrees."
            )

        play_count = length // phrase_bars
        repeat = await send(
            client,
            numbers,
            "setRepeatBarlines",
            {
                "startMeasure": first,
                "endMeasure": kept_end,
                "playCount": play_count,
            },
        )
        if repeat.get("fallback"):
            return repeat
        await send(
            client,
            numbers,
            "deleteMeasures",
            {"startMeasure": kept_end + 1, "endMeasure": last},
        )
        try:
            await client.request(
                "setStyle", {"key": "repeatPlayCountShow", "value": True}
            )
        except ToolError:
            pass
        kept = (
            f"Bar {numbers.label(first)}"
            if phrase_bars == 1
            else f"Bars {numbers.span(first, kept_end)}"
        )
        return {
            "success": True,
            "message": (
                f"{kept} now play{'s' if phrase_bars == 1 else ''} {play_count} times; bars "
                f"{numbers.span(kept_end + 1, last)} were removed, so later bars moved up by {length - phrase_bars}."
            ),
            "differences_dropped": differing,
            "ghost_or_crash_differences_dropped": minor,
        }

    async def remove_other_parts(
        staves: List[int], score_path: Optional[str]
    ) -> Dict:
        """Remove the other parts from the open score itself.

        This is make_part_score(in_place=True).

        Nothing is saved before the other parts are gone: saving the full score
        would write again (and MuseScore would flag as corrupted) a damaged bar
        in another instrument, and an imported score would first ask where to
        save. The full score is backed up first, as MusicXML and, if its file is
        found, as a copy.

        Args:
            staves (List[int]): The staves to keep, 0-based.
            score_path (Optional[str]): A score file given by the user, for the
                backup. Defaults to the open score's own file.

        Returns:
            result (Dict): "kept_parts", "staves_now", "full_score_backups",
                "incomplete_bars", "warnings" and a "message".

        Raises:
            ToolError: If the plugin reports an error.
        """
        score_id = (await client.request("ensureScoreId"))["scoreId"]
        info = await client.request("scoreFileInfo")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        name = (
            re.sub(
                r'[\\/:*?"<>|]+', "-", info.get("scoreName") or "score"
            ).strip(" -.")
            or "score"
        )
        backups, warnings = [], []
        # The full score as MusicXML: always possible, without saving
        export = backup_dir() / f"{name}.{stamp}.full-score.mxl"
        export.parent.mkdir(parents=True, exist_ok=True)
        try:
            await client.request("exportScore", {"path": str(export)})
            backups.append(str(export))
        except ToolError as e:
            warnings.append(f"MusicXML backup failed: {e}")
        # The score's own file, if it is certainly this score (it carries its ID and shape)
        try:
            path = locate_open_score(
                score_id,
                info.get("numStaves", 0),
                info.get("numMeasures", 0),
                explicit=score_path,
                known=[KNOWN_PATHS[score_id]]
                if score_id in KNOWN_PATHS
                else [],
            )
            backups.append(str(backup_score(path)))
        except ScoreFileError:
            pass
        if not backups:
            warnings.append(
                "No backup of the full score could be made; its file on disk is untouched until the "
                "score is saved."
            )

        result = await client.request("removeParts", {"keepStaves": staves})
        measures, _ = await fetch_measures(client, 1, None, None)
        incomplete = (await bar_numbers(client)).relabel(
            incomplete_measures(measures)
        )
        if incomplete:
            warnings.append(
                "Bars whose notes don't fill the bar (MuseScore calls the file corrupted when it has these): "
                + ", ".join(
                    f"bar {i['measure']} staff {i['staff']}"
                    for i in incomplete[:10]
                )
                + (" ..." if len(incomplete) > 10 else "")
            )
        return {
            "kept_parts": result.get("kept"),
            "staves_now": result.get("numStaves"),
            "full_score_backups": backups,
            "incomplete_bars": incomplete,
            "warnings": warnings,
            "message": "Removed the other instruments from the open score (Ctrl+Z undoes it). Nothing was saved: "
            "the first file edit (or File > Save) saves the chart. If the score was imported (e.g. from "
            "Guitar Pro), MuseScore asks once where to save it. Full-score backups: "
            + (", ".join(backups) or "none")
            + " (open the .mxl with File > Open).",
        }

    @mcp.tool(
        description=(
            "Make a separate score containing only some parts (e.g. the drum kit) to build a chart in: saves the "
            "current score, writes a copy of its file without the other instruments (tempo, rehearsal marks, "
            "repeats and the title move to the kept staff), closes the original and opens the copy in its place "
            "(the plugin can only work in its own window). The original is saved and unchanged; if the copy can't "
            "be opened, the original is reopened. Works even when another instrument has a damaged bar. "
            "in_place=True instead removes the other instruments from the open score itself, without saving "
            "anything first (so a damaged bar in another instrument is never written again) and after backing up "
            "the full score (MusicXML export, plus a copy of its .mscz when it can be identified); it reports "
            "bars left that don't add up. Staff indices in the new score start again from 0."
        ),
        tags={"structure"},
    )
    async def make_part_score(
        staves: Annotated[
            List[int], "Staff indices (0-based) whose parts to keep"
        ],
        output_path: Annotated[
            Optional[str],
            "Where to save the new score (.mscz). Defaults to next to the original, named after the part.",
        ] = None,
        score_path: Annotated[
            Optional[str],
            "Path of the current score's file. Defaults to the file of the score open in MuseScore.",
        ] = None,
        in_place: Annotated[
            bool,
            "Remove the other instruments from the open score (after backing up the full score) instead of making a copy",
        ] = False,
    ):
        header = await staff_header()
        kept = [st for st in header if st["index"] in staves]
        if not kept:
            raise ToolError(f"None of the staves {staves} exist")
        if in_place:
            return await remove_other_parts(staves, score_path)
        # The plugin's writeScore() cannot write .mscz in MuseScore 4.7, so copy the saved file instead.
        source = await open_score_path(client, score_path, reopen_part=False)
        fallback = PART_SOURCES.pop(
            source, source
        )  # a part tab's own file isn't open yet: fall back to the full score

        if output_path:
            target = Path(output_path).expanduser()
            if target.suffix.lower() != source.suffix.lower():
                target = target.with_suffix(source.suffix)
        else:
            # Part names can be long ("Player | Instrument | Drums"): use the short name or the last segment
            label = (
                kept[0].get("shortName")
                or (kept[0].get("partName") or "part").split("|")[-1]
            )
            label = re.sub(r'[\\/:*?"<>|]+', "-", label).strip(" -.") or "part"
            target = source.with_name(f"{source.stem} - {label}{source.suffix}")
            n = 2
            while target.exists():
                target = source.with_name(
                    f"{source.stem} - {label} ({n}){source.suffix}"
                )
                n += 1
        if target.exists():
            raise ToolError(
                f"{target} already exists; choose another output_path"
            )

        # The other instruments are removed in the file, before MuseScore opens it: a damaged bar in a removed
        # instrument (common in Guitar Pro imports) would otherwise stop MuseScore from opening the copy.
        try:
            copy_score = ScoreFile(source)
            report = keep_parts(copy_score, staves)
        except ScoreFileError as e:
            raise ToolError(
                f"Could not make the copy: {e}. Nothing was changed."
            )
        copy_id = (
            new_score_id()
        )  # its own score ID, so it can never be mistaken for the original
        for tag in copy_score.score.findall("metaTag"):
            if tag.get("name") == SCORE_ID_TAG:
                copy_score.score.remove(tag)
        copy_score.score.insert(
            0, ET.Element("metaTag", {"name": SCORE_ID_TAG})
        )
        copy_score.score[0].text = copy_id
        copy_score.save(target)
        KNOWN_PATHS[copy_id] = target

        # MuseScore 4 opens another score in a new window, where the plugin cannot reach it, so the
        # original (saved, unchanged) is closed and the copy opened in its place; if that fails, the
        # original is reopened.
        reopened = await reopen_in_place(client, target, fallback=fallback)
        if not reopened["reopened"]:
            raise ToolError(
                f"Made {target} with only {', '.join(report['kept_parts'])}, but MuseScore could not open it, so "
                f"the original was reopened unchanged. {reopened.get('next_step', '')}"
            )
        info = await client.request("scoreFileInfo")
        return {
            "file": str(target),
            "kept_parts": report["kept_parts"],
            "staves_now": info.get("numStaves"),
            "system_texts_moved": report["system_texts"],
            "message": f"Opened {target.name} with only {', '.join(report['kept_parts'])}. "
            f"The original ({source.name}) is saved and unchanged; it was closed so the plugin "
            "works on the copy (reopen it from File > Open Recent when needed).",
        }

    @mcp.tool(
        description=(
            "Make the displayed bar numbers count repeated bars, as played: after a passage between repeat "
            "barlines played N times, the next bar's number jumps by (N - 1) x the passage length. Recomputes all "
            "bars (MuseScore's 'Add to measure number'), so it can be run again after changing repeats. "
            "exclude_from_count leaves bars out of the count, e.g. [1] for a silent pickup or intro bar. "
            "reset=True removes all offsets and exclusions instead (plain 1..N numbering). "
            "Voltas are not taken into account. Needs MuseScore 4.6+. Tools take and give bars as printed, so after "
            "this call they go by the new numbers."
        ),
        tags={"structure"},
    )
    async def number_bars_as_played(
        exclude_from_count: Annotated[
            Optional[List[Bar]],
            f"Bars to exclude from the count, {BAR_HELP} before this call, e.g. [1]",
        ] = None,
        reset: Annotated[
            bool, "Undo the numbering: plain 1..N, no offsets or excluded bars"
        ] = False,
    ):
        bars = await bar_numbers(client)
        params = (
            {"exclude": [bars.position(b) for b in exclude_from_count]}
            if exclude_from_count
            else {}
        )
        if reset:
            params = {"reset": True}
        return await renumber(bars, "numberAsPlayed", params)

    @mcp.tool(
        description=(
            "Set the displayed number of one bar: add_to_number is MuseScore's 'Add to measure number' (the offset "
            "carries on to all later bars), exclude_from_count is 'Exclude from measure count'."
        ),
        tags={"structure"},
    )
    async def set_measure_number(
        measure: Annotated[Bar, f"The bar, {BAR_HELP} before this call"],
        add_to_number: Annotated[
            Optional[int],
            "Value for 'Add to measure number' (0 to remove an offset)",
        ] = None,
        exclude_from_count: Annotated[
            Optional[bool], "Value for 'Exclude from measure count'"
        ] = None,
    ):
        if add_to_number is None and exclude_from_count is None:
            raise ToolError("Pass add_to_number and/or exclude_from_count")
        bars = await bar_numbers(client)
        params = {"measure": bars.position(measure)}
        if add_to_number is not None:
            params["addToNumber"] = add_to_number
        if exclude_from_count is not None:
            params["excludeFromCount"] = exclude_from_count
        return await renumber(bars, "setMeasureNumbering", params)

    @mcp.tool(
        description="Add a rehearsal mark (section label such as 'A' or 'Verse') at the start of a bar. Experimental: check the score afterwards.",
        tags={"structure"},
    )
    async def add_rehearsal_mark(
        measure: Annotated[Bar, f"The bar, {BAR_HELP}"],
        text: Annotated[str, 'Label, e.g. "A" or "Verse 1"'],
    ):
        bars = await bar_numbers(client)
        return await send(
            client,
            bars,
            "addRehearsalMark",
            {"measure": bars.position(measure), "text": text},
        )
