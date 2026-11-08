"""Notes and measures tools for MuseScore MCP."""

from typing import Annotated, List, Optional
from ..client import MuseScoreClient


def setup_notes_measures_tools(mcp, client: MuseScoreClient):
    """Setup notes and measures tools."""
    
    @mcp.tool(
        description=(
            "Add a note at the current cursor position with the specified pitch and duration. "
            "Sequential notes write a melody. Set add_to_chord=True to stack a pitch on the current chord."
        ),
        tags={"notes"},
    )
    async def add_note(
        pitch: Annotated[int, "MIDI pitch value (0-127, where 60 is middle C)"] = 64,
        duration: Annotated[dict, 'Duration as {"numerator": int, "denominator": int} (e.g. {"numerator": 1, "denominator": 4} for a quarter note)'] = {"numerator": 1, "denominator": 4},
        advance_cursor_after_action: Annotated[bool, "Whether to move cursor to next position after adding note"] = True,
        add_to_chord: Annotated[bool, "If True, add this pitch to the current chord instead of writing the next melody note"] = False,
    ):
        return await client.send_command("addNote", {
            "pitch": pitch, 
            "duration": duration,
            "advanceCursorAfterAction": advance_cursor_after_action,
            "addToChord": add_to_chord
        })

    @mcp.tool(
        description=(
            "Tie notes of the chord at the cursor to the same pitches in the next chord of that staff. "
            "A tie joins two notes of the same pitch into one longer sound. Only pitches in both chords can be "
            "tied: by default every such pitch is tied; pass pitches to tie only some of them (e.g. tie C and E "
            "of C-E-G into C-E-A with pitches=[60, 64]). Afterwards the cursor is on the second chord, so calling "
            "add_tie again continues a tie chain. Note that after add_note the cursor is already on the next "
            "position: move back to the first note (e.g. with prev_element) before calling add_tie. "
            "Fails without changing the score when no pitch can be tied, e.g. when the next element is a rest."
        ),
        tags={"notes"},
    )
    async def add_tie(
        pitches: Annotated[Optional[List[int]], "MIDI pitches to tie (e.g. [60, 64]). Default: every pitch that is in both chords."] = None,
    ):
        params = {}
        if pitches is not None:
            params["pitches"] = pitches
        return await client.request("addTie", params)

    @mcp.tool(
        description="Add a rest at the current cursor position.",
        tags={"notes"},
    )
    async def add_rest(
        duration: Annotated[dict, 'Duration as {"numerator": int, "denominator": int} (e.g. {"numerator": 1, "denominator": 4} for a quarter rest)'] = {"numerator": 1, "denominator": 4},
        advance_cursor_after_action: Annotated[bool, "Whether to move cursor to next position after adding rest"] = True,
    ):
        return await client.send_command("addRest", {
            "duration": duration,
            "advanceCursorAfterAction": advance_cursor_after_action
        })

    @mcp.tool(
        description="Add a tuplet at the current cursor position.",
        tags={"notes"},
    )
    async def add_tuplet(
        duration: Annotated[dict, 'Base duration as {"numerator": int, "denominator": int}'] = {"numerator": 1, "denominator": 4},
        ratio: Annotated[dict, 'Tuplet ratio as {"numerator": int, "denominator": int} (e.g. {"numerator": 3, "denominator": 2} for a triplet)'] = {"numerator": 3, "denominator": 2},
        advance_cursor_after_action: Annotated[bool, "Whether to move cursor to next position after adding tuplet"] = True,
    ):
        return await client.send_command("addTuplet", {
            "duration": duration,
            "ratio": ratio,
            "advanceCursorAfterAction": advance_cursor_after_action
        })

    @mcp.tool(
        description="Add lyrics to consecutive notes starting from the current cursor position.",
        tags={"notes"},
    )
    async def add_lyrics(
        lyrics: Annotated[List[str], 'List of lyric syllables to add (e.g. ["Hel", "lo", "world"])'],
        verse: Annotated[int, "Verse number (0-based, default is 0 for first verse)"] = 0,
    ):
        return await client.send_command("addLyrics", {
            "lyrics": lyrics,
            "verse": verse
        })

    @mcp.tool(
        description="Insert a measure at the current position.",
        tags={"measures"},
    )
    async def insert_measure():
        return await client.send_command("insertMeasure")

    @mcp.tool(
        description="Append measures to the end of the score.",
        tags={"measures"},
    )
    async def append_measure(
        count: Annotated[int, "Number of empty measures to append"] = 1,
    ):
        return await client.send_command("appendMeasure", {"count": count})

    @mcp.tool(
        description="Delete the current selection, or the specified measure.",
        tags={"measures"},
    )
    async def delete_selection(
        measure: Annotated[Optional[int], "Measure number (1-based) to delete. If omitted, the current selection is deleted."] = None,
    ):
        params = {}
        if measure is not None:
            params["measure"] = measure
        return await client.send_command("deleteSelection", params)

    @mcp.tool(
        description=(
            "Remove whole measures (on every staff) from the score, like MuseScore's Remove selected range (Ctrl+Del). "
            "Works with multi-measure rests on (they are switched off meanwhile) and reports an error if MuseScore "
            "deleted fewer measures than asked. Later measures are renumbered, so when removing several ranges start "
            "from the last one."
        ),
        tags={"measures"},
    )
    async def delete_measures(
        start_measure: Annotated[int, "First measure to remove (1-based)"],
        end_measure: Annotated[Optional[int], "Last measure to remove (1-based, inclusive). Defaults to start_measure."] = None,
    ):
        return await client.send_command("deleteMeasures", {
            "startMeasure": start_measure,
            "endMeasure": end_measure if end_measure is not None else start_measure,
        })

    @mcp.tool(
        description="Undo the last action.",
        tags={"measures"},
    )
    async def undo():
        return await client.send_command("undo")