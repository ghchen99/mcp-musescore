"""Time signature and tempo tools for MuseScore MCP."""

from typing import Annotated, Optional

from ..client import MuseScoreClient


def setup_time_tempo_tools(mcp, client: MuseScoreClient):
    """Setup time signature and tempo tools."""
    
    @mcp.tool(
        description="Set the time signature.",
        tags={"time"},
    )
    async def set_time_signature(
        numerator: Annotated[int, "Top number of time signature (beats per measure)"] = 4,
        denominator: Annotated[int, "Bottom number of time signature (note value that gets the beat)"] = 4,
    ):
        return await client.send_command("setTimeSignature", {
            "numerator": numerator,
            "denominator": denominator
        })

    @mcp.tool(
        description=(
            "Set the tempo with a tempo marking (in quarter-note beats per minute) "
            "at the current cursor position, or at the start of the given measure."
        ),
        tags={"time"},
    )
    async def set_tempo(
        bpm: Annotated[float, "Tempo in quarter-note beats per minute (e.g. 120)"],
        measure: Annotated[Optional[int], "Measure number (1-based) to place the tempo at. Defaults to the cursor position."] = None,
    ):
        params = {"bpm": bpm}
        if measure is not None:
            params["measure"] = measure
        return await client.send_command("setTempo", params)
