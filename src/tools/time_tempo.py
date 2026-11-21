"""Time signature and tempo tools for MuseScore MCP."""

from typing import Annotated, Optional

from fastmcp import FastMCP

from ..bars import BAR_HELP, Bar, bar_numbers, send
from ..client import MuseScoreClient


def setup_time_tempo_tools(mcp: FastMCP, client: MuseScoreClient) -> None:
    """Register the time signature and tempo tools.

    Args:
        mcp (FastMCP): The server to register the tools on.
        client (MuseScoreClient): The client the tools send their commands
            through.
    """

    @mcp.tool(
        description="Set the time signature.",
        tags={"time"},
    )
    async def set_time_signature(
        numerator: Annotated[
            int, "Top number of time signature (beats per measure)"
        ] = 4,
        denominator: Annotated[
            int,
            "Bottom number of time signature (note value that gets the beat)",
        ] = 4,
    ):
        return await client.request(
            "setTimeSignature",
            {"numerator": numerator, "denominator": denominator},
        )

    @mcp.tool(
        description=(
            "Set the tempo with a tempo marking (in quarter-note beats per minute) "
            "at the current cursor position, or at the start of the given bar."
        ),
        tags={"time"},
    )
    async def set_tempo(
        bpm: Annotated[
            float, "Tempo in quarter-note beats per minute (e.g. 120)"
        ],
        measure: Annotated[
            Optional[Bar],
            f"Bar to place the tempo at, {BAR_HELP}. Defaults to the cursor position.",
        ] = None,
    ):
        params: dict = {"bpm": bpm}
        if measure is None:
            return await client.request("setTempo", params)
        bars = await bar_numbers(client)
        params["measure"] = bars.position(measure)
        return await send(client, bars, "setTempo", params)
