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
        description="Undo the last action.",
        tags={"measures"},
    )
    async def undo():
        return await client.send_command("undo")