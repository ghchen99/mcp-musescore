"""Score coloring tools for MuseScore MCP."""

import re
from typing import Annotated, List, Literal, Optional

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from ..client import MuseScoreClient


def range_params(
    start_measure: int,
    end_measure: Optional[int],
    first_staff: int,
    last_staff: Optional[int],
) -> dict:
    """Build the plugin's range parameters from a tool's measures and staves.

    The plugin's endStaff is exclusive, the tools' last_staff inclusive.

    Args:
        start_measure (int): The first measure, 1-based.
        end_measure (Optional[int]): The last measure, 1-based and inclusive.
            Defaults to start_measure.
        first_staff (int): The first staff, 0-based.
        last_staff (Optional[int]): The last staff, 0-based and inclusive.
            Defaults to the last staff of the score.

    Returns:
        params (dict): "startMeasure", "endMeasure", "startStaff" and, with a
            last staff, "endStaff".
    """
    params = {
        "startMeasure": start_measure,
        "endMeasure": end_measure if end_measure is not None else start_measure,
        "startStaff": first_staff,
    }
    if last_staff is not None:
        params["endStaff"] = last_staff + 1
    return params


def beat_params(
    params: dict, start_beat: Optional[float], end_beat: Optional[float]
) -> dict:
    """Add the optional beat range to the plugin's range parameters.

    Args:
        params (dict): The range parameters, changed in place.
        start_beat (Optional[float]): The beat in the first measure where the
            range starts, 1-based.
        end_beat (Optional[float]): The last beat to include in the last
            measure.

    Returns:
        params (dict): The same parameters, with "startBeat" and "endBeat" when
            given.
    """
    if start_beat is not None:
        params["startBeat"] = start_beat
    if end_beat is not None:
        params["endBeat"] = end_beat
    return params


START_BEAT_HELP = (
    "Beat in start_measure where coloring starts (1-based; fractions allowed, e.g. 3.5 for the 'and' of 3). "
    "A beat is the time signature's denominator: a quarter in 4/4, an eighth in 6/8. Defaults to the start of the measure."
)
END_BEAT_HELP = "Last beat in end_measure to include, the whole beat (e.g. 4 = through the end of beat 4). Defaults to the end of the measure."


# Drum names accepted by highlight_notes, as General MIDI percussion pitches
DRUM_PITCHES = {
    "kick": [35, 36],
    "snare": [38, 40],
    "side stick": [37],
    "clap": [39],
    "hi-hat": [42, 44, 46],
    "closed hi-hat": [42],
    "pedal hi-hat": [44],
    "open hi-hat": [46],
    "crash": [49, 57],
    "ride": [51, 59],
    "ride bell": [53],
    "china": [52],
    "splash": [55],
    "tom": [41, 43, 45, 47, 48, 50],
    "low tom": [41, 43],
    "mid tom": [45, 47],
    "high tom": [48, 50],
    "tambourine": [54],
    "cowbell": [56],
}


def drum_pitches(names: List[str]) -> List[int]:
    """Look up the MIDI pitches of drum names.

    Plurals and spellings such as "hi-hats" or "hihat" are accepted.

    Args:
        names (List[str]): The drum names, e.g. ["crash", "hi-hats"].

    Returns:
        pitches (List[int]): Their General MIDI percussion pitches.

    Raises:
        ToolError: If a name is not a known drum.
    """
    pitches = []
    for name in names:
        key = (
            name.strip()
            .lower()
            .replace("hihat", "hi-hat")
            .replace("hi hat", "hi-hat")
        )
        for singular in (
            key,
            key[:-2] if key.endswith("es") else key,
            key[:-1] if key.endswith("s") else key,
        ):
            if singular in DRUM_PITCHES:
                key = singular
                break
        if key not in DRUM_PITCHES:
            raise ToolError(
                f"Unknown drum {name!r}; use one of {', '.join(sorted(DRUM_PITCHES))} or pass pitches"
            )
        pitches += DRUM_PITCHES[key]
    return pitches


def translucent(color: str, opacity: float) -> str:
    """Combine a "#rrggbb" color and an opacity into Qt's "#aarrggbb".

    Args:
        color (str): The color, e.g. "#2ca02c".
        opacity (float): The opacity, above 0 and up to 1.

    Returns:
        argb (str): The color with its alpha first, e.g. "#802ca02c".

    Raises:
        ToolError: If the color is not "#rrggbb" or the opacity is out of range.
    """
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise ToolError(f'Color must look like "#rrggbb", got {color!r}')
    if not 0 < opacity <= 1:
        raise ToolError("opacity must be between 0 (exclusive) and 1")
    return f"#{round(opacity * 255):02x}{color[1:]}"


def setup_formatting_tools(mcp: FastMCP, client: MuseScoreClient) -> None:
    """Register the coloring, highlighting and annotation tools.

    Args:
        mcp (FastMCP): The server to register the tools on.
        client (MuseScoreClient): The client the tools send their commands
            through.
    """

    @mcp.tool(
        description=(
            "Color the notes and rests (with their stems, beams, accidentals, dots, ties and grace notes such as flams) "
            "in a range of measures and staves, e.g. to highlight a passage. Use start_beat/end_beat to "
            "color only part of a bar, e.g. a fill on beats 3-4: notes and rests starting in that span are colored."
        ),
        tags={"formatting"},
    )
    async def color_range(
        start_measure: Annotated[int, "First measure to color (1-based)"],
        end_measure: Annotated[
            Optional[int],
            "Last measure to color (1-based, inclusive). Defaults to start_measure.",
        ] = None,
        first_staff: Annotated[int, "First staff to color (0-based)"] = 0,
        last_staff: Annotated[
            Optional[int],
            "Last staff to color (0-based, inclusive). Defaults to the last staff.",
        ] = None,
        color: Annotated[
            str, 'Color as "#rrggbb" (e.g. "#d62728" for red)'
        ] = "#d62728",
        voices: Annotated[
            Optional[List[int]],
            "Voices to color (0-3). Defaults to all voices.",
        ] = None,
        start_beat: Annotated[Optional[float], START_BEAT_HELP] = None,
        end_beat: Annotated[Optional[float], END_BEAT_HELP] = None,
    ):
        params = beat_params(
            range_params(start_measure, end_measure, first_staff, last_staff),
            start_beat,
            end_beat,
        )
        params["color"] = color
        if voices:
            params["voices"] = voices
        return await client.request("colorRange", params)

    @mcp.tool(
        description="Reset notes and rests in a range of measures and staves (optionally only some beats) to the default black.",
        tags={"formatting"},
    )
    async def clear_color(
        start_measure: Annotated[int, "First measure to reset (1-based)"],
        end_measure: Annotated[
            Optional[int],
            "Last measure to reset (1-based, inclusive). Defaults to start_measure.",
        ] = None,
        first_staff: Annotated[int, "First staff to reset (0-based)"] = 0,
        last_staff: Annotated[
            Optional[int],
            "Last staff to reset (0-based, inclusive). Defaults to the last staff.",
        ] = None,
        start_beat: Annotated[Optional[float], START_BEAT_HELP] = None,
        end_beat: Annotated[Optional[float], END_BEAT_HELP] = None,
    ):
        params = beat_params(
            range_params(start_measure, end_measure, first_staff, last_staff),
            start_beat,
            end_beat,
        )
        params["color"] = "#000000"
        return await client.request("colorRange", params)

    @mcp.tool(
        description=(
            "Highlight bars like a highlighter pen: a thick, semi-transparent band behind the notes of each staff in "
            "the range, following the bars across line breaks. start_beat/end_beat limit it to part of a bar. "
            "Saved in the score; remove with clear_highlights. Experimental: check the result in the score."
        ),
        tags={"formatting"},
    )
    async def highlight_bars(
        start_measure: Annotated[int, "First measure to highlight (1-based)"],
        end_measure: Annotated[
            Optional[int],
            "Last measure (1-based, inclusive). Defaults to start_measure.",
        ] = None,
        first_staff: Annotated[int, "First staff (0-based)"] = 0,
        last_staff: Annotated[
            Optional[int],
            "Last staff (0-based, inclusive). Defaults to first_staff.",
        ] = None,
        color: Annotated[
            str, 'Highlight color as "#rrggbb" (default yellow)'
        ] = "#ffe600",
        opacity: Annotated[float, "Opacity from 0 to 1"] = 0.35,
        start_beat: Annotated[Optional[float], START_BEAT_HELP] = None,
        end_beat: Annotated[Optional[float], END_BEAT_HELP] = None,
    ):
        params = beat_params(
            range_params(
                start_measure,
                end_measure,
                first_staff,
                last_staff if last_staff is not None else first_staff,
            ),
            start_beat,
            end_beat,
        )
        params["color"] = translucent(color, opacity)
        return await client.request("addHighlight", params)

    @mcp.tool(
        description=(
            "Highlight individual hits like a highlighter pen: a translucent box around each matching note, as wide "
            "as the note and as tall as the whole staff (taller if the note sits above or below it). Hits close "
            'enough for their boxes to touch share one box. Use drums (e.g. ["crash"]) or pitches to pick notes '
            "in a chord. start_beat/end_beat limit it to part of a bar. Boxes are sized to the current layout: if "
            "the layout changes a lot, clear and highlight again. Remove with clear_highlights."
        ),
        tags={"formatting"},
    )
    async def highlight_notes(
        start_measure: Annotated[int, "First measure (1-based)"],
        end_measure: Annotated[
            Optional[int],
            "Last measure (1-based, inclusive). Defaults to start_measure.",
        ] = None,
        first_staff: Annotated[int, "First staff (0-based)"] = 0,
        last_staff: Annotated[
            Optional[int],
            "Last staff (0-based, inclusive). Defaults to first_staff.",
        ] = None,
        drums: Annotated[
            Optional[List[str]],
            'Drum kit pieces to mark, e.g. ["crash"], ["kick", "snare"], ["hi-hat"]',
        ] = None,
        pitches: Annotated[
            Optional[List[int]],
            "MIDI pitches to mark (e.g. 57 for crash 2). Combined with drums; all notes if both are empty.",
        ] = None,
        start_beat: Annotated[Optional[float], START_BEAT_HELP] = None,
        end_beat: Annotated[Optional[float], END_BEAT_HELP] = None,
        color: Annotated[
            str, 'Highlight color as "#rrggbb" (default yellow)'
        ] = "#ffd600",
        opacity: Annotated[float, "Opacity from 0 to 1"] = 0.45,
    ):
        params = beat_params(
            range_params(
                start_measure,
                end_measure,
                first_staff,
                last_staff if last_staff is not None else first_staff,
            ),
            start_beat,
            end_beat,
        )
        selected = (pitches or []) + drum_pitches(drums or [])
        if selected:
            params["pitches"] = sorted(set(selected))
        params["color"] = translucent(color, opacity)
        return await client.request("highlightNotes", params)

    @mcp.tool(
        description=(
            "Highlight or recolor time signatures, repeat barlines (start/end repeat signs with their dots) and "
            "measure-repeat signs. mode='highlight' draws a full-staff-height translucent box around each one "
            "(pastel light blue by default); mode='color' recolors the symbol itself (clear=True resets it to black)."
        ),
        tags={"formatting"},
    )
    async def highlight_symbols(
        start_measure: Annotated[int, "First measure (1-based)"] = 1,
        end_measure: Annotated[
            Optional[int],
            "Last measure (1-based, inclusive). Defaults to the end of the score.",
        ] = None,
        first_staff: Annotated[int, "First staff (0-based)"] = 0,
        last_staff: Annotated[
            Optional[int],
            "Last staff (0-based, inclusive). Defaults to the last staff.",
        ] = None,
        kinds: Annotated[
            List[
                Literal["time_signatures", "repeat_barlines", "measure_repeats"]
            ],
            "Which symbols",
        ] = ["time_signatures", "repeat_barlines", "measure_repeats"],
        mode: Annotated[
            Literal["highlight", "color"],
            "Box behind the symbol, or recolor the symbol itself",
        ] = "highlight",
        color: Annotated[
            str, 'Color as "#rrggbb" (default pastel light blue)'
        ] = "#a7d8f0",
        opacity: Annotated[
            float, "Box opacity from 0 to 1 (highlight mode)"
        ] = 0.6,
        clear: Annotated[
            bool, "Color mode only: reset the symbols to black"
        ] = False,
    ):
        if end_measure is None:
            end_measure = (await client.request("scoreFileInfo"))["numMeasures"]
        params = range_params(
            start_measure, end_measure, first_staff, last_staff
        )
        params.update({"kinds": kinds, "mode": mode, "clear": clear})
        if mode == "highlight":
            params["color"] = translucent(color, opacity)
        else:
            translucent(color, 1)  # validates the color
            params["color"] = color
        return await client.request("highlightSymbols", params)

    @mcp.tool(
        description=(
            "Highlight markings such as dynamics (f, mf, ff) with a translucent box behind each one. get_score "
            "lists the markings in each measure. Remove with clear_highlights."
        ),
        tags={"formatting"},
    )
    async def highlight_markings(
        start_measure: Annotated[int, "First measure (1-based)"] = 1,
        end_measure: Annotated[
            Optional[int],
            "Last measure (1-based, inclusive). Defaults to the end of the score.",
        ] = None,
        first_staff: Annotated[int, "First staff (0-based)"] = 0,
        last_staff: Annotated[
            Optional[int],
            "Last staff (0-based, inclusive). Defaults to the last staff.",
        ] = None,
        types: Annotated[
            List[
                Literal[
                    "Dynamic", "StaffText", "SystemText", "Tempo", "Expression"
                ]
            ],
            "Kinds of markings to highlight",
        ] = ["Dynamic"],
        color: Annotated[
            str, 'Highlight color as "#rrggbb" (default yellow)'
        ] = "#ffd600",
        opacity: Annotated[float, "Opacity from 0 to 1"] = 0.55,
    ):
        if end_measure is None:
            end_measure = (await client.request("scoreFileInfo"))["numMeasures"]
        params = range_params(
            start_measure, end_measure, first_staff, last_staff
        )
        params["types"] = types
        params["color"] = translucent(color, opacity)
        return await client.request("highlightMarkings", params)

    @mcp.tool(
        description=(
            "Add free text at a bar (optionally at a beat) with its own look: size, italic/bold, color, above or "
            "below the staff. Defaults give a small, italic, light-grey cue, e.g. the first words of a section's "
            "lyrics as a reminder for the player. kind='expression' makes it an expression text. Use the text the "
            "user provides. Remove with Ctrl+Z, or select the texts in MuseScore and delete them."
        ),
        tags={"formatting"},
    )
    async def add_text(
        measure: Annotated[int, "Bar position (1-based)"],
        text: Annotated[str, "The text to add"],
        staff: Annotated[int, "Staff (0-based)"] = 0,
        beat: Annotated[
            Optional[float],
            "Beat within the bar (1-based, fractions allowed). Defaults to the start of the bar.",
        ] = None,
        size: Annotated[float, "Font size in points"] = 8,
        italic: Annotated[bool, "Italic text"] = True,
        bold: Annotated[bool, "Bold text"] = False,
        color: Annotated[
            str, 'Text color as "#rrggbb" (default light grey)'
        ] = "#9e9e9e",
        placement: Annotated[
            Literal["above", "below"], "Above or below the staff"
        ] = "above",
        kind: Annotated[
            Literal["staff", "expression"], "Staff text, or expression text"
        ] = "staff",
    ):
        translucent(color, 1)  # validates the color
        params = {
            "measure": measure,
            "text": text,
            "staff": staff,
            "fontSize": size,
            "italic": italic,
            "bold": bold,
            "color": color,
            "placement": placement,
            "kind": kind,
        }
        if beat is not None:
            params["beat"] = beat
        return await client.request("addText", params)

    @mcp.tool(
        description=(
            "Remove texts and marks from a range of bars, e.g. to redo part of a chart. kinds: 'texts' (add_text: "
            "cues, '*' marks, legends), 'labels' (boxed add_label texts), 'rehearsal_marks', 'tempo' (tempo "
            "markings, which also changes playback), 'voltas'. `contains` limits it to texts containing that string, "
            "e.g. '**'. Defaults to the whole score. Highlights and note colors are removed with clear_highlights / "
            "clear_color instead."
        ),
        tags={"formatting"},
    )
    async def remove_annotations(
        start_measure: Annotated[int, "First bar (1-based position)"] = 1,
        end_measure: Annotated[
            Optional[int],
            "Last bar (inclusive). Defaults to the end of the score.",
        ] = None,
        first_staff: Annotated[int, "First staff (0-based)"] = 0,
        last_staff: Annotated[
            Optional[int],
            "Last staff (0-based, inclusive). Defaults to the last staff.",
        ] = None,
        kinds: Annotated[
            List[
                Literal["texts", "labels", "rehearsal_marks", "tempo", "voltas"]
            ],
            "What to remove",
        ] = ["texts"],
        contains: Annotated[
            Optional[str],
            "Only remove texts containing this string (text-based kinds)",
        ] = None,
        exact: Annotated[
            bool,
            'Only remove texts equal to `contains` (e.g. "*" but not "**" or a legend)',
        ] = False,
    ):
        if end_measure is None:
            end_measure = (await client.request("scoreFileInfo"))["numMeasures"]
        params = range_params(
            start_measure, end_measure, first_staff, last_staff
        )
        params["kinds"] = kinds
        if contains:
            params["contains"] = contains
            params["exact"] = exact
        return await client.request("removeAnnotations", params)

    @mcp.tool(
        description=(
            "Add an articulation to the chords that contain the chosen drums in a range of bars (and beats): "
            "'half_open' (half-open hi-hat), 'open', 'closed' (hi-hat), 'accent', 'marcato', 'staccato', 'tenuto'. "
            "E.g. drums=['hi-hat'], symbol='half_open' marks the hi-hats of bars 72-85 as half-open. Chords that "
            "already have it are left alone. Remove with remove_articulations."
        ),
        tags={"notation"},
    )
    async def add_articulation(
        start_measure: Annotated[int, "First bar (1-based position)"],
        end_measure: Annotated[
            Optional[int], "Last bar (inclusive). Defaults to start_measure."
        ] = None,
        symbol: Annotated[
            Literal[
                "half_open",
                "open",
                "closed",
                "accent",
                "marcato",
                "staccato",
                "tenuto",
            ],
            "Articulation to add",
        ] = "half_open",
        drums: Annotated[
            Optional[List[str]], 'Drums whose chords get it, e.g. ["hi-hat"]'
        ] = None,
        pitches: Annotated[
            Optional[List[int]],
            "MIDI pitches whose chords get it (with drums; all chords if both empty)",
        ] = None,
        first_staff: Annotated[int, "First staff (0-based)"] = 0,
        last_staff: Annotated[
            Optional[int],
            "Last staff (0-based, inclusive). Defaults to the last staff.",
        ] = None,
        start_beat: Annotated[Optional[float], START_BEAT_HELP] = None,
        end_beat: Annotated[Optional[float], END_BEAT_HELP] = None,
    ):
        params = beat_params(
            range_params(start_measure, end_measure, first_staff, last_staff),
            start_beat,
            end_beat,
        )
        selected = (pitches or []) + drum_pitches(drums or [])
        if selected:
            params["pitches"] = sorted(set(selected))
        params["symbol"] = symbol
        return await client.request("addArticulation", params)

    @mcp.tool(
        description=(
            "Remove articulations (by default the hi-hat symbols half_open, open, closed) from the chords that "
            "contain the chosen drums in a range of bars."
        ),
        tags={"notation"},
    )
    async def remove_articulations(
        start_measure: Annotated[int, "First bar (1-based position)"] = 1,
        end_measure: Annotated[
            Optional[int],
            "Last bar (inclusive). Defaults to the end of the score.",
        ] = None,
        symbols: Annotated[
            List[
                Literal[
                    "half_open",
                    "open",
                    "closed",
                    "accent",
                    "marcato",
                    "staccato",
                    "tenuto",
                ]
            ],
            "Articulations to remove",
        ] = ["half_open", "open", "closed"],
        drums: Annotated[
            Optional[List[str]], 'Only chords with these drums, e.g. ["hi-hat"]'
        ] = None,
        pitches: Annotated[
            Optional[List[int]], "Only chords with these MIDI pitches"
        ] = None,
        first_staff: Annotated[int, "First staff (0-based)"] = 0,
        last_staff: Annotated[
            Optional[int],
            "Last staff (0-based, inclusive). Defaults to the last staff.",
        ] = None,
    ):
        if end_measure is None:
            end_measure = (await client.request("scoreFileInfo"))["numMeasures"]
        params = range_params(
            start_measure, end_measure, first_staff, last_staff
        )
        selected = (pitches or []) + drum_pitches(drums or [])
        if selected:
            params["pitches"] = sorted(set(selected))
        params["symbols"] = symbols
        return await client.request("removeArticulations", params)

    @mcp.tool(
        description=(
            "List the ghost notes (notes in parentheses) per bar, or remove them (mode='remove'). A chord made only "
            "of ghost notes becomes a rest. Show the list to the user before removing: whether a chart keeps ghost "
            "notes is their choice."
        ),
        tags={"notation"},
    )
    async def ghost_notes(
        start_measure: Annotated[int, "First bar (1-based position)"] = 1,
        end_measure: Annotated[
            Optional[int],
            "Last bar (inclusive). Defaults to the end of the score.",
        ] = None,
        mode: Annotated[
            Literal["list", "remove"], "List them, or remove them"
        ] = "list",
        drums: Annotated[
            Optional[List[str]], 'Only these drums, e.g. ["hi-hat"]'
        ] = None,
        pitches: Annotated[
            Optional[List[int]], "Only these MIDI pitches"
        ] = None,
        first_staff: Annotated[int, "First staff (0-based)"] = 0,
        last_staff: Annotated[
            Optional[int],
            "Last staff (0-based, inclusive). Defaults to the last staff.",
        ] = None,
    ):
        if end_measure is None:
            end_measure = (await client.request("scoreFileInfo"))["numMeasures"]
        params = range_params(
            start_measure, end_measure, first_staff, last_staff
        )
        selected = (pitches or []) + drum_pitches(drums or [])
        if selected:
            params["pitches"] = sorted(set(selected))
        params["mode"] = mode
        return await client.request("ghostNotes", params)

    @mcp.tool(
        description=(
            "Beam eighths and shorter across rests inside a beat group (a dotted quarter in 12/8, a beat in 4/4), "
            "as drum charts write them: one beamed group per beat with the rest under the beam, instead of "
            "separate flags broken at every rest. Only rests with beamable notes before and after them in the "
            "same group change. Run it over the whole drum staff once the chart is done. clear=True puts the rests "
            "back on automatic beaming."
        ),
        tags={"notation"},
    )
    async def beam_over_rests(
        start_measure: Annotated[int, "First bar (1-based position)"] = 1,
        end_measure: Annotated[
            Optional[int],
            "Last bar (inclusive). Defaults to the end of the score.",
        ] = None,
        first_staff: Annotated[int, "First staff (0-based)"] = 0,
        last_staff: Annotated[
            Optional[int],
            "Last staff (0-based, inclusive). Defaults to the last staff.",
        ] = None,
        clear: Annotated[
            bool, "Undo: put the rests back on automatic beaming"
        ] = False,
    ):
        if end_measure is None:
            end_measure = (await client.request("scoreFileInfo"))["numMeasures"]
        params = range_params(
            start_measure, end_measure, first_staff, last_staff
        )
        if clear:
            params["clear"] = True
        return await client.request("beamOverRests", params)

    @mcp.tool(
        description=(
            "Add a label in a colored box (a boxed staff text) at the start of a measure, e.g. a section tag like "
            "'Groove x7' or 'Fill'. Saved in the score; remove with clear_highlights."
        ),
        tags={"formatting"},
    )
    async def add_label(
        measure: Annotated[int, "Measure number (1-based)"],
        text: Annotated[str, "Label text"],
        staff: Annotated[int, "Staff to attach the label to (0-based)"] = 0,
        background: Annotated[
            str, 'Box color as "#rrggbb" (default pale yellow)'
        ] = "#fff2a8",
        border: Annotated[str, 'Box border color as "#rrggbb"'] = "#000000",
    ):
        for value in (background, border):
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
                raise ToolError(
                    f'Colors must look like "#rrggbb", got {value!r}'
                )
        return await client.request(
            "addLabel",
            {
                "measure": measure,
                "text": text,
                "staff": staff,
                "background": background,
                "border": border,
            },
        )

    @mcp.tool(
        description=(
            "Remove highlights from a range of measures and staves. kinds: 'highlights' = bands and boxes from "
            "highlight_bars, highlight_notes and highlight_symbols; 'markings' = boxes behind dynamics "
            "(highlight_markings); 'labels' = boxed labels (add_label); 'notes' = small notehead boxes made by older "
            "versions. Recolored notes and symbols are reset with clear_color / highlight_symbols(mode='color', clear=True)."
        ),
        tags={"formatting"},
    )
    async def clear_highlights(
        start_measure: Annotated[int, "First measure (1-based)"] = 1,
        end_measure: Annotated[
            Optional[int],
            "Last measure (1-based, inclusive). Defaults to the end of the score.",
        ] = None,
        first_staff: Annotated[int, "First staff (0-based)"] = 0,
        last_staff: Annotated[
            Optional[int],
            "Last staff (0-based, inclusive). Defaults to the last staff.",
        ] = None,
        kinds: Annotated[
            List[Literal["highlights", "notes", "markings", "labels"]],
            "What to remove: highlight bands, note boxes, marking boxes, boxed labels",
        ] = ["highlights", "notes", "markings", "labels"],
    ):
        if end_measure is None:
            end_measure = (await client.request("scoreFileInfo"))["numMeasures"]
        params = range_params(
            start_measure, end_measure, first_staff, last_staff
        )
        params["kinds"] = kinds
        return await client.request("clearHighlights", params)
