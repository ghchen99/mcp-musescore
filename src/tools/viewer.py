"""Score viewer tool: renders the current score as sheet music inside MCP Apps hosts."""

import json
from pathlib import Path
from typing import Annotated, Optional

from fastmcp.apps import AppConfig, ResourceCSP
from fastmcp.exceptions import ToolError
from fastmcp.tools import ToolResult

from ..client import MuseScoreClient

VIEWER_URI = "ui://musescore/score-viewer.html"
VIEWER_HTML = Path(__file__).resolve().parent.parent / "ui" / "score_viewer.html"
DEFAULT_MEASURE_TICKS = 1920


def _unwrap(response: dict) -> dict:
    """Return the plugin's result payload or raise ToolError."""
    if response.get("status") == "error" or "error" in response:
        raise ToolError(response.get("message") or response.get("error") or "MuseScore error")
    result = response.get("result")
    if not isinstance(result, dict) or "error" in result:
        message = result.get("error") if isinstance(result, dict) else "Unexpected plugin response"
        raise ToolError(message)
    return result


def setup_viewer_tools(mcp, client: MuseScoreClient):
    """Setup the score viewer (an MCP App: tool plus ui:// resource)."""

    @mcp.resource(
        VIEWER_URI,
        app=AppConfig(csp=ResourceCSP(resource_domains=["https://unpkg.com"])),
    )
    def score_viewer() -> str:
        """Sheet music viewer used by show_score."""
        return VIEWER_HTML.read_text(encoding="utf-8")

    @mcp.tool(
        app=AppConfig(resource_uri=VIEWER_URI),
        description=(
            "Show the current score as rendered sheet music in an interactive viewer. "
            "Use it to check your edits visually. Tuplet brackets and ties are not drawn. "
            "Hosts without MCP Apps support only receive a short text summary; "
            "use get_score for the note data."
        ),
        tags={"score"},
        annotations={"readOnlyHint": True},
    )
    async def show_score(
        first_measure: Annotated[int, "First measure to show (1-based)"] = 1,
        last_measure: Annotated[
            Optional[int], "Last measure to show (1-based). Defaults to the end of the score."
        ] = None,
    ) -> ToolResult:
        analysis = _unwrap(await client.send_command("getScore")).get("analysis")
        if not isinstance(analysis, dict):
            raise ToolError("MuseScore returned no score data")

        measures = analysis.get("measures", [])
        measure_ticks = DEFAULT_MEASURE_TICKS
        if len(measures) > 1:
            measure_ticks = measures[1]["startTick"] - measures[0]["startTick"] or measure_ticks

        shown = [
            m for m in measures
            if m["measure"] >= first_measure and (last_measure is None or m["measure"] <= last_measure)
        ]
        payload = {**analysis, "measures": shown, "measureTicks": measure_ticks}

        title = analysis.get("title") or "Untitled"
        summary = (
            f'Score "{title}": showing {len(shown)} of {len(measures)} measure(s), '
            f'{len(analysis.get("staves", []))} staff/staves.'
        )
        return ToolResult(content=summary, structured_content=json.loads(json.dumps(payload)))
