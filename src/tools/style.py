"""Score style tools for MuseScore MCP."""

from typing import Annotated, Any, Dict, List

from fastmcp import FastMCP

from ..client import MuseScoreClient


def setup_style_tools(mcp: FastMCP, client: MuseScoreClient) -> None:
    """Register the tools that read and change the score's style settings.

    Args:
        mcp (FastMCP): The server to register the tools on.
        client (MuseScoreClient): The client the tools send their commands
            through.
    """

    @mcp.tool(
        description=(
            "Read score style settings (Format → Style) by MuseScore's internal key, e.g. "
            '"createMultiMeasureRests", "chordSymbolAFontSize", "minMeasureWidth". Returns the current '
            'values, and lists under "unknown" the keys MuseScore does not have.'
        ),
        tags={"style"},
    )
    async def get_style(
        keys: Annotated[List[str], "Style keys to read"],
    ) -> Dict[str, Any]:
        result = await client.request("getStyle", {"keys": keys})
        return {"styles": result["styles"], "unknown": result["unknown"]}

    @mcp.tool(
        description=(
            "Change score style settings (Format → Style), given as {key: value} with MuseScore's internal "
            "keys. An unknown key is refused, and the settings before it stay applied. Returns each value as "
            "MuseScore reads it back after the change; check it with get_style or render when unsure."
        ),
        tags={"style"},
    )
    async def set_style(
        styles: Annotated[Dict[str, Any], "Style keys and their new values"],
    ) -> Dict[str, Any]:
        applied = {}
        for key, value in styles.items():
            result = await client.request(
                "setStyle", {"key": key, "value": value}
            )
            applied[key] = result["value"]
        return applied
