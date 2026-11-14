"""Repeat structure tools for MuseScore MCP: find repeated material and mark it."""

import re
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Dict, List, Literal, Optional, Tuple

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

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
PASSAGE_COLORS = ["#1f77b4", "#2ca02c", "#9467bd", "#8c564b", "#e377c2", "#17becf"]
MEASURE_REPEAT_COLOR = "#ff7f0e"


def _contiguous(indices: List[int]) -> List[List[int]]:
    """Split sorted staff indices into [first, last] runs of consecutive staves."""
    runs: List[List[int]] = []
    for idx in sorted(indices):
        if runs and runs[-1][1] + 1 == idx:
            runs[-1][1] = idx
        else:
            runs.append([idx, idx])
    return runs


def _apply_steps(passage: Dict) -> List[str]:
    """Tool calls that compress one passage, ordered so earlier measure numbers stay valid."""
    dup_first, dup_last = passage["duplicate_measures"]
    if passage["type"] == "repeat":
        return [
            f"delete_measures({dup_first}, {dup_last})",
            f"set_repeat_barlines({passage['start']}, {passage['end']}, play_count={passage['times']})",
        ]
    first_ending, second_ending = passage["first_ending"], passage["second_ending"]
    return [
        f"add_volta({second_ending[0]}, {second_ending[1]}, endings=[2])",
        f"delete_measures({dup_first}, {dup_last})",
        f"add_volta({first_ending[0]}, {first_ending[1]}, endings=[1])",
        f"set_repeat_barlines({passage['start']}, {first_ending[1]})",
    ]


async def fetch_measures(client: MuseScoreClient, start_measure: int, end_measure: Optional[int],
                         staves: Optional[List[int]]) -> Tuple[List[Dict], List[Dict]]:
    """Read measures start..end (default: to the end) in chunks; returns (measures, staff info)."""
    params: Dict[str, Any] = {"startMeasure": start_measure, "endMeasure": start_measure + FETCH_CHUNK - 1}
    if staves:
        params["staves"] = staves
    analysis = (await client.request("getScore", params))["analysis"]
    total = analysis.get("numMeasures", 0)
    last = min(end_measure, total) if end_measure is not None else total
    measures = [m for m in analysis.get("measures", []) if m["measure"] <= last]

    next_start = params["endMeasure"] + 1
    while next_start <= last:
        chunk = {**params, "startMeasure": next_start, "endMeasure": min(next_start + FETCH_CHUNK - 1, last)}
        measures.extend((await client.request("getScore", chunk))["analysis"].get("measures", []))
        next_start = chunk["endMeasure"] + 1
    return measures, analysis.get("staves", [])


def incomplete_measures(measures: List[Dict]) -> List[Dict]:
    """Bars where a voice's notes and rests don't add up to the bar's length (voice 1 must fill it)."""
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
                    totals[voice] = totals.get(voice, 0) + element.get("durationTicks", 0)
            bad = {v: t for v, t in totals.items() if t > length or (v == 0 and t != length)}
            if length and bad:
                out.append({"measure": measure["measure"], "staff": int(key.replace("staff", "")),
                            "found_ticks": bad, "expected_ticks": length})
    return out


def _road_map_line(section: Dict) -> str:
    """One line of the section map, e.g. "Bars 6-13: groove bar 6, 5 exact copies, near 9, fill 13"."""
    parts = [f"groove bar {section['groove_bar']}"]
    if section["exact"]:
        parts.append(f"{len(section['exact'])} exact cop{'y' if len(section['exact']) == 1 else 'ies'}")
    if section["near"]:
        parts.append("near " + ", ".join(str(n["bar"]) for n in section["near"]))
    if section["fills"]:
        parts.append("fill " + ", ".join(str(b) for b in section["fills"]))
    for run in section.get("runs", []):
        keep = f"{run['keep'][0]}" if run["phrase_bars"] == 1 else f"{run['keep'][0]}-{run['keep'][1]}"
        text = f"collapse {run['start']}-{run['end']} to {keep} x{run['play_count']}"
        crash = run["crash_on_1"]
        if crash.get("legend"):
            text += f" ({crash['mark']} {crash['legend']})"
        elif crash.get("pattern") == "irregular":
            text += f" (irregular crashes, passes {crash['run_bars']})"
        if run["dropped"]:
            text += f", drops differences in bars {', '.join(str(d['bar']) for d in run['dropped'])}"
        parts.append(text)
    return f"Bars {section['start']}-{section['end']}: " + ", ".join(parts)


def setup_structure_tools(mcp: FastMCP, client: MuseScoreClient) -> None:
    """Setup repeat structure tools."""

    async def staff_header() -> List[Dict]:
        analysis = (await client.request(
            "getScore", {"startMeasure": 1, "endMeasure": 1, "includeElements": False}
        ))["analysis"]
        return analysis.get("staves", [])

    @mcp.tool(
        description=(
            "Find repeated material in the score. Returns (1) per-staff bars that repeat the previous 1, 2 or 4 bars, "
            "candidates for measure-repeat signs (these declutter the page but keep the length), and (2) whole-score "
            "passages played again right away, candidates for repeat barlines and 1st/2nd endings (these shorten the "
            "score once the duplicate measures are deleted). Each passage lists the tool calls that apply it. "
            "Reads the score in small chunks, so it works on large scores. Measure numbers refer to the score as it "
            "is now: apply passages from the last one backwards."
        ),
        tags={"structure"},
    )
    async def find_repeated_measures(
        start_measure: Annotated[int, "First measure to analyse (1-based)"] = 1,
        end_measure: Annotated[Optional[int], "Last measure to analyse (1-based, inclusive). Defaults to the end of the score."] = None,
        staves: Annotated[Optional[List[int]], "Staff indices to analyse (0-based). Defaults to all staves."] = None,
        highlight: Annotated[
            bool,
            "Also color the results in the score: duplicate measures of each passage in a passage color, "
            "per-staff measure repeats in orange. Undo or clear_color removes it.",
        ] = False,
    ):
        measures, staff_info = await fetch_measures(client, start_measure, end_measure, staves)
        staff_names = [st["name"] for st in staff_info]
        found = find_repeats(measures, staff_names)
        for passage in found["passages"]:
            passage["apply"] = _apply_steps(passage)

        result = {
            "measures_analysed": [measures[0]["measure"], measures[-1]["measure"]] if measures else [],
            "staves_analysed": [st.get("index", i) for i, st in enumerate(staff_info)],
            "passages": found["passages"],
            "measure_repeats": found["measure_repeats"],
            "notes": [
                "Apply passages from the last one backwards: delete_measures renumbers later measures.",
                "measure_repeats use the current measure numbers; re-run this tool after deleting measures.",
                "Place measure-repeat signs with apply_measure_repeats (one call per staff, all groups at once).",
            ],
        }

        if highlight:
            analysed = result["staves_analysed"]
            legend = []
            for group in found["measure_repeats"]:
                for first, last_staff in _contiguous(group["staves"]):
                    await client.request("colorRange", {
                        **range_params(group["from"], group["to"], first, last_staff),
                        "color": MEASURE_REPEAT_COLOR,
                    })
            if found["measure_repeats"]:
                legend.append({"color": MEASURE_REPEAT_COLOR, "meaning": "per-staff measure repeat"})
            for i, passage in enumerate(found["passages"]):
                color = PASSAGE_COLORS[i % len(PASSAGE_COLORS)]
                dup_first, dup_last = passage["duplicate_measures"]
                for first, last_staff in _contiguous(analysed):
                    await client.request("colorRange", {
                        **range_params(dup_first, dup_last, first, last_staff),
                        "color": color,
                    })
                legend.append({
                    "color": color,
                    "meaning": f"duplicate of measures {passage['start']}-{passage['end']} (passage {i + 1})",
                })
            result["highlight_legend"] = legend

        return result

    @mcp.tool(
        description=(
            "Put start and end repeat barlines around a range of measures, or remove them. "
            "Needs MuseScore 4.6 or newer; on older versions the measures are selected and the reply "
            "says which palette items to click."
        ),
        tags={"structure"},
    )
    async def set_repeat_barlines(
        start_measure: Annotated[int, "Measure that gets the start repeat (1-based)"],
        end_measure: Annotated[int, "Measure that gets the end repeat (1-based, inclusive)"],
        play_count: Annotated[int, "How many times the passage is played in total"] = 2,
        clear: Annotated[bool, "True to remove the repeat barlines instead of adding them"] = False,
    ):
        return await client.request("setRepeatBarlines", {
            "startMeasure": start_measure,
            "endMeasure": end_measure,
            "playCount": play_count,
            "clear": clear,
        })

    @mcp.tool(
        description=(
            "Add a volta (1st/2nd ending bracket) over a range of measures. Experimental: the plugin API has no "
            "dedicated volta call, so check the result; if it fails, the measures are selected and the reply "
            "says which palette item to click."
        ),
        tags={"structure"},
    )
    async def add_volta(
        start_measure: Annotated[int, "First measure under the volta (1-based)"],
        end_measure: Annotated[Optional[int], "Last measure under the volta (1-based, inclusive). Defaults to start_measure."] = None,
        endings: Annotated[List[int], "Which repeat passes play this ending, e.g. [1] for a first ending, [2] for a second"] = [1],
        text: Annotated[Optional[str], 'Volta label. Defaults to the endings, e.g. "1." or "1, 2."'] = None,
    ):
        params = {
            "startMeasure": start_measure,
            "endMeasure": end_measure if end_measure is not None else start_measure,
            "endings": endings,
        }
        if text:
            params["text"] = text
        return await client.request("addVolta", params)

    @mcp.tool(
        description=(
            "Prepare measure-repeat signs: selects the measures that should become repeat signs, on the given staves, "
            "and returns what to click in MuseScore. The plugin API cannot place measure-repeat signs itself."
        ),
        tags={"structure"},
    )
    async def prepare_measure_repeat(
        start_measure: Annotated[int, "First measure to turn into a repeat sign (1-based); it repeats the bars before it"],
        end_measure: Annotated[Optional[int], "Last measure (1-based, inclusive). Defaults to start_measure + bars - 1."] = None,
        bars: Annotated[Literal[1, 2, 4], "Size of the measure-repeat sign: 1, 2 or 4 bars"] = 1,
        first_staff: Annotated[int, "First staff (0-based)"] = 0,
        last_staff: Annotated[Optional[int], "Last staff (0-based, inclusive). Defaults to the last staff."] = None,
    ):
        if end_measure is None:
            end_measure = start_measure + bars - 1
        result = await client.request(
            "selectMeasures", range_params(start_measure, end_measure, first_staff, last_staff)
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
        staves: Annotated[Optional[List[int]], "Staff indices to analyse (0-based). Defaults to the drum staves."] = None,
        start_measure: Annotated[int, "First measure to analyse (1-based)"] = 1,
        end_measure: Annotated[Optional[int], "Last measure to analyse (1-based, inclusive). Defaults to the end of the score."] = None,
        tolerance: Annotated[float, "How similar (0-1, share of identical hits) a bar must be to its groove to count as a near copy"] = 0.85,
    ):
        if not staves:
            staves = [st["index"] for st in await staff_header() if st.get("isDrums")]
            if not staves:
                raise ToolError("No drum staff found in the score; pass the staves to analyse")

        measures, staff_info = await fetch_measures(client, start_measure, end_measure, staves)
        result = []
        for st in staff_info:
            sections = find_sections(measures, st["name"], tolerance)
            groups = [g for sec in sections for g in sec["proposed_repeat_signs"]]
            result.append({
                "staff": st.get("index"),
                "name": st.get("partName") or st["name"],
                "road_map": [_road_map_line(sec) for sec in sections],
                "sections": sections,
                "apply_exact_copies": {"staff": st.get("index"), "groups": groups} if groups else None,
            })
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
        staff: Annotated[Optional[int], "Staff to analyse (0-based). Defaults to the first drum staff."] = None,
        tolerance: Annotated[float, "How similar (0-1, share of identical hits) bars must be to share a groove name"] = 0.8,
    ):
        if staff is None:
            drums = [st["index"] for st in await staff_header() if st.get("isDrums")]
            staff = drums[0] if drums else 0
        measures, staff_info = await fetch_measures(client, 1, None, [staff])
        if not staff_info:
            raise ToolError(f"Staff {staff} not found")
        result = analyse_structure(measures, staff_info[0]["name"], tolerance)
        result["suggested_rows"] = [{
            "section": sec["section"],
            "bars": sec["bars_played"],
            "count": sec["count"],
            "groove": ", ".join(g["name"] for g in sec["grooves"]),
            "fill": "; ".join(f"bar {f['bar']} ({', '.join(f['drums'])})" for f in sec["fills"]),
        } for sec in result["sections"]]
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
        counts: Annotated[Optional[List[Dict[str, Any]]], 'Counts to write: [{"measure": 8, "text": "2x4+2"}] (measure '
                                                         '= the bar holding the section label). Defaults to song_structure\'s counts.'] = None,
        staff: Annotated[Optional[int], "Staff to analyse when counts are computed (0-based). Defaults to the first drum staff."] = None,
        placement: Annotated[Literal["label", "beside"], "In parentheses in the section label, or as red text beside it"] = "label",
        color: Annotated[str, "Text color (placement='beside')"] = "#d62728",
        size: Annotated[float, "Font size in points (placement='beside')"] = 12,
        label_size: Annotated[Optional[float], "Section label font size in points (placement='label'; MuseScore's default is 14); None leaves it"] = 12,
        label_clearance: Annotated[Optional[float], "Minimum space around section labels in staff spaces (placement='label'; MuseScore's default is 0.5); None leaves it"] = 1,
        clear: Annotated[bool, "Remove the counts instead (at the given measures, or at every section label)"] = False,
    ):
        computed = counts is None
        if counts is None:
            if staff is None:
                drums = [st["index"] for st in await staff_header() if st.get("isDrums")]
                staff = drums[0] if drums else 0
            measures, staff_info = await fetch_measures(client, 1, None, [staff])
            if not staff_info:
                raise ToolError(f"Staff {staff} not found")
            sections = analyse_structure(measures, staff_info[0]["name"])["sections"]
            counts = [{"measure": sec["first_bar"], "text": sec["count"]} for sec in sections if sec["section"] != "Start"]
        for c in counts:
            if not isinstance(c, dict) or not isinstance(c.get("measure"), int) or not str(c.get("text") or "").strip():
                raise ToolError(f'Each count needs a measure and a text, e.g. {{"measure": 8, "text": "2x4+2"}}: {c!r}')
        params = {"counts": [{"measure": c["measure"], "text": str(c["text"]).strip().strip("()").strip()} for c in counts],
                  "mode": placement, "color": color, "fontSize": size}
        if computed or placement == "label":
            params["clearAll"] = True  # counts beside the labels left anywhere by earlier edits go too
        if clear:
            params["clear"] = True
        result = await client.request("addSectionCounts", params)
        result["counts"] = params["counts"]
        if placement == "label" and not clear:
            styles = {"rehearsalMarkFontSize": label_size, "rehearsalMarkMinDistance": label_clearance}
            for key, value in styles.items():
                if value is not None:
                    await client.request("setStyle", {"key": key, "value": value})
            result["label_style"] = {k: v for k, v in styles.items() if v is not None}
        return result

    @mcp.tool(
        description=(
            "Collapse a run of repeated bars or phrases into one played N times: keeps the first phrase_bars bars "
            "from start, deletes the rest of the run, and puts start/end repeat barlines with a play count around "
            "the kept bars (shown as e.g. '7x'). With phrase_bars=2, bars start..end must be a 2-bar phrase "
            "repeated (e.g. 28-35 becomes 28-29 x4). This changes every staff, so use it in a score that contains "
            "only the part being charted (make_part_score). It refuses when any staff's copies differ in anything "
            "but ghost notes and crashes on beat 1, unless force=True. Later measures are renumbered: collapse from "
            "the end of the score backwards. Needs MuseScore 4.6+."
        ),
        tags={"structure"},
    )
    async def collapse_to_repeat(
        start: Annotated[int, "First bar of the run (1-based); the phrase starting here is kept"],
        end: Annotated[int, "Last bar of the run (1-based, inclusive)"],
        phrase_bars: Annotated[int, "Length of the repeated phrase in bars (1, 2, 4...); the run must be a whole number of phrases"] = 1,
        force: Annotated[bool, "Collapse even if copies differ in more than ghost notes and crashes on beat 1 (those differences are lost)"] = False,
    ):
        length = end - start + 1
        if phrase_bars < 1 or length < 2 * phrase_bars or length % phrase_bars:
            raise ToolError(f"Bars {start}-{end} are not a whole number (at least 2) of {phrase_bars}-bar phrases")
        measures, staff_info = await fetch_measures(client, start, end, None)
        differing, minor = [], []
        for st in staff_info:
            core, _ = staff_fingerprints(measures, st["name"], core_fingerprint)
            full, _ = staff_fingerprints(measures, st["name"])
            name = st.get("partName") or st["name"]
            bars = [measures[i]["measure"] for i in range(phrase_bars, len(core)) if core[i] != core[i % phrase_bars]]
            if bars:
                differing.append({"staff": st.get("index"), "name": name, "bars": bars})
            small = [measures[i]["measure"] for i in range(phrase_bars, len(full))
                     if full[i] != full[i % phrase_bars] and measures[i]["measure"] not in bars]
            if small:
                minor.append({"staff": st.get("index"), "name": name, "bars": small})
        if differing and not force:
            listed = "; ".join(f"{d['name']} (staff {d['staff']}): bars {d['bars']}" for d in differing)
            raise ToolError(
                f"Not every phrase in {start}-{end} is a copy of bars {start}-{start + phrase_bars - 1}: {listed}. "
                "Collapsing would delete those differences (kicks, snares, hats or articulations). Try a longer "
                "phrase_bars, chart a single part (make_part_score), or pass force=True after the user agrees."
            )

        play_count = length // phrase_bars
        kept_end = start + phrase_bars - 1
        repeat = await client.request(
            "setRepeatBarlines", {"startMeasure": start, "endMeasure": kept_end, "playCount": play_count}
        )
        if repeat.get("fallback"):
            return repeat
        await client.request("deleteMeasures", {"startMeasure": kept_end + 1, "endMeasure": end})
        try:
            await client.request("setStyle", {"key": "repeatPlayCountShow", "value": True})
        except ToolError:
            pass
        kept = f"Bar {start}" if phrase_bars == 1 else f"Bars {start}-{kept_end}"
        return {
            "success": True,
            "message": (
                f"{kept} now play{'s' if phrase_bars == 1 else ''} {play_count} times; bars {kept_end + 1}-{end} "
                f"were removed, so later bars moved up by {length - phrase_bars}."
            ),
            "differences_dropped": differing,
            "ghost_or_crash_differences_dropped": minor,
        }

    async def remove_other_parts(staves: List[int], score_path: Optional[str]) -> Dict:
        """make_part_score(in_place=True). Nothing is saved before the other parts are gone: saving the full
        score would write again (and MuseScore would flag as corrupted) a damaged bar in another instrument, and
        an imported score would first ask where to save.
        """
        score_id = (await client.request("ensureScoreId"))["scoreId"]
        info = await client.request("scoreFileInfo")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        name = re.sub(r'[\\/:*?"<>|]+', "-", info.get("scoreName") or "score").strip(" -.") or "score"
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
            path = locate_open_score(score_id, info.get("numStaves", 0), info.get("numMeasures", 0),
                                     explicit=score_path, known=[KNOWN_PATHS[score_id]] if score_id in KNOWN_PATHS else [])
            backups.append(str(backup_score(path)))
        except ScoreFileError:
            pass
        if not backups:
            warnings.append("No backup of the full score could be made; its file on disk is untouched until the "
                            "score is saved.")

        result = await client.request("removeParts", {"keepStaves": staves})
        measures, _ = await fetch_measures(client, 1, None, None)
        incomplete = incomplete_measures(measures)
        if incomplete:
            warnings.append(
                "Bars whose notes don't fill the bar (MuseScore calls the file corrupted when it has these): "
                + ", ".join(f"bar {i['measure']} staff {i['staff']}" for i in incomplete[:10])
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
                       + (", ".join(backups) or "none") + " (open the .mxl with File > Open).",
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
        staves: Annotated[List[int], "Staff indices (0-based) whose parts to keep"],
        output_path: Annotated[Optional[str], "Where to save the new score (.mscz). Defaults to next to the original, named after the part."] = None,
        score_path: Annotated[Optional[str], "Path of the current score's file. Defaults to the file of the score open in MuseScore."] = None,
        in_place: Annotated[bool, "Remove the other instruments from the open score (after backing up the full score) instead of making a copy"] = False,
    ):
        header = await staff_header()
        kept = [st for st in header if st["index"] in staves]
        if not kept:
            raise ToolError(f"None of the staves {staves} exist")
        if in_place:
            return await remove_other_parts(staves, score_path)
        # The plugin's writeScore() cannot write .mscz in MuseScore 4.7, so copy the saved file instead.
        source = await open_score_path(client, score_path, reopen_part=False)
        fallback = PART_SOURCES.pop(source, source)  # a part tab's own file isn't open yet: fall back to the full score

        if output_path:
            target = Path(output_path).expanduser()
            if target.suffix.lower() != source.suffix.lower():
                target = target.with_suffix(source.suffix)
        else:
            # Part names can be long ("Player | Instrument | Drums"): use the short name or the last segment
            label = kept[0].get("shortName") or (kept[0].get("partName") or "part").split("|")[-1]
            label = re.sub(r'[\\/:*?"<>|]+', "-", label).strip(" -.") or "part"
            target = source.with_name(f"{source.stem} - {label}{source.suffix}")
            n = 2
            while target.exists():
                target = source.with_name(f"{source.stem} - {label} ({n}){source.suffix}")
                n += 1
        if target.exists():
            raise ToolError(f"{target} already exists; choose another output_path")

        # The other instruments are removed in the file, before MuseScore opens it: a damaged bar in a removed
        # instrument (common in Guitar Pro imports) would otherwise stop MuseScore from opening the copy.
        try:
            copy_score = ScoreFile(source)
            report = keep_parts(copy_score, staves)
        except ScoreFileError as e:
            raise ToolError(f"Could not make the copy: {e}. Nothing was changed.")
        copy_id = new_score_id()  # its own score ID, so it can never be mistaken for the original
        for tag in copy_score.score.findall("metaTag"):
            if tag.get("name") == SCORE_ID_TAG:
                copy_score.score.remove(tag)
        copy_score.score.insert(0, ET.Element("metaTag", {"name": SCORE_ID_TAG}))
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
            "Voltas are not taken into account. Needs MuseScore 4.6+. Tools keep addressing bars by position."
        ),
        tags={"structure"},
    )
    async def number_bars_as_played(
        exclude_from_count: Annotated[
            Optional[List[int]], "Bar positions (1-based) to exclude from the count, e.g. [1]"
        ] = None,
        reset: Annotated[bool, "Undo the numbering: plain 1..N, no offsets or excluded bars"] = False,
    ):
        params = {"exclude": exclude_from_count} if exclude_from_count else {}
        if reset:
            params = {"reset": True}
        return await client.request("numberAsPlayed", params)

    @mcp.tool(
        description=(
            "Set the displayed number of one bar: add_to_number is MuseScore's 'Add to measure number' (the offset "
            "carries on to all later bars), exclude_from_count is 'Exclude from measure count'."
        ),
        tags={"structure"},
    )
    async def set_measure_number(
        measure: Annotated[int, "Bar position (1-based)"],
        add_to_number: Annotated[Optional[int], "Value for 'Add to measure number' (0 to remove an offset)"] = None,
        exclude_from_count: Annotated[Optional[bool], "Value for 'Exclude from measure count'"] = None,
    ):
        if add_to_number is None and exclude_from_count is None:
            raise ToolError("Pass add_to_number and/or exclude_from_count")
        params = {"measure": measure}
        if add_to_number is not None:
            params["addToNumber"] = add_to_number
        if exclude_from_count is not None:
            params["excludeFromCount"] = exclude_from_count
        return await client.request("setMeasureNumbering", params)

    @mcp.tool(
        description="Add a rehearsal mark (section label such as 'A' or 'Verse') at the start of a measure. Experimental: check the score afterwards.",
        tags={"structure"},
    )
    async def add_rehearsal_mark(
        measure: Annotated[int, "Measure number (1-based)"],
        text: Annotated[str, 'Label, e.g. "A" or "Verse 1"'],
    ):
        return await client.request("addRehearsalMark", {"measure": measure, "text": text})

