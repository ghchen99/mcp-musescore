"""Time signature and tempo tools for MuseScore MCP."""

from typing import Annotated

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