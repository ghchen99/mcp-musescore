"""Connection and utility tools for MuseScore MCP."""

from typing import Annotated, Any, Dict, List, Literal, Optional

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from ..bars import BAR_HELP, Bar, bar_numbers
from ..client import MuseScoreClient

GET_SCORE_WINDOW = 16


def marking_text(marking: Dict[str, Any]) -> str:
    """Return a marking's text as get_score shows it.

    The plugin cannot read the name of a chord symbol imported from MusicXML
    until the score has been saved, closed and opened again, so its text arrives
    empty. Saving alone does not fill it in: MuseScore copies the name into the
    text only when it loads the file.

    Args:
        marking (Dict[str, Any]): A marking from the getScore analysis.

    Returns:
        text (str): The marking's text, or a note that it is not readable.
    """
    text = marking.get("text", "")
    if marking.get("name") == "Harmony" and not text:
        return "(name not readable: save the score, close it and open it again; saving alone is not enough)"
    return text


def setup_connection_tools(mcp: FastMCP, client: MuseScoreClient) -> None:
    """Register the connection and score-reading tools.

    Args:
        mcp (FastMCP): The server to register the tools on.
        client (MuseScoreClient): The client the tools send their commands
            through.
    """

    @mcp.tool(
        description="Connect to the MuseScore WebSocket API.",
        tags={"connection"},
    )
    async def connect_to_musescore():
        result = await client.connect()
        return {"success": result}

    @mcp.tool(
        description="Ping the MuseScore WebSocket API to check connection.",
        tags={"connection"},
    )
    async def ping_musescore():
        # The plugin answers the bare string "pong", not a result dictionary
        reply = await client.send_command("ping")
        if reply.get("status") != "success" or reply.get("result") != "pong":
            raise ToolError(f"The plugin did not answer the ping: {reply}")
        return {"success": True, "message": "pong"}

    @mcp.tool(
        description=(
            "Get the notes of the current score as LilyPond (or raw JSON), a range of bars at a time. "
            f"Without end_measure, returns at most {GET_SCORE_WINDOW} bars starting at start_measure; "
            "the header says which bars the score has, so page through long scores. "
            "Use staves to read only some staves of a large score. Each bar ends with '% bar N', N being the "
            "number printed in the score, as users and every tool's bar parameters name bars (a pickup bar is "
            "0, a number printed twice is 12a/12b); repeat barlines show as '|:' and ':|xN'."
        ),
        tags={"connection", "score"},
    )
    async def get_score(
        start_measure: Annotated[
            Optional[Bar],
            f"First bar to read, {BAR_HELP}. Defaults to the first bar.",
        ] = None,
        end_measure: Annotated[
            Optional[Bar],
            f"Last bar to read, inclusive. Defaults to {GET_SCORE_WINDOW} bars from start_measure.",
        ] = None,
        staves: Annotated[
            Optional[List[int]],
            "Staff indices to read (0-based). Defaults to all staves.",
        ] = None,
        format: Annotated[
            Literal["lilypond", "json"],
            '"lilypond" for compact notation text, "json" for the raw analysis',
        ] = "lilypond",
    ):
        bars = await bar_numbers(client)
        first = 1 if start_measure is None else bars.position(start_measure)
        if end_measure is None:
            last = min(first + GET_SCORE_WINDOW - 1, len(bars.labels))
        else:
            last = bars.position(end_measure)
        params: Dict[str, Any] = {"startMeasure": first, "endMeasure": last}
        if staves:
            params["staves"] = staves

        result = await client.request("getScore", params)
        if not isinstance(result.get("analysis"), dict):
            raise ToolError("MuseScore sent no score analysis")

        analysis = result["analysis"]
        for m in analysis.get("measures", []):
            m["label"] = bars.label(m["measure"])
        if format == "json":
            return analysis

        from ..utils.lilypond_converter import score_to_lilypond

        lily_str = score_to_lilypond(analysis)

        total = len(bars.labels)
        shown = [m.get("measure") for m in analysis.get("measures", [])]
        meta = []
        if analysis.get("title"):
            meta.append(f"Title: {analysis['title']}")
        if total:
            meta.append(f"Bars: {bars.describe()}")
        if shown:
            meta.append(f"Bars shown: {bars.describe(shown[0], shown[-1])}")
        num_staves = len(analysis.get("staves", []))
        if num_staves > 0:
            meta.append(f"Staves: {num_staves}")

        meta_str = ", ".join(meta) if meta else "No metadata"
        text = f"[Metadata] {meta_str}\n[Score]\n{lily_str}"
        markings = []
        for m in analysis.get("measures", []):
            markings += [
                f"bar {m['label']}: {el['name']} {el.get('text', '')}".rstrip()
                for el in m.get("measureElements", [])
            ]
            markings += [
                f"bar {m['label']} beat {(mk['startTick'] - m['startTick']) / 480 + 1:g}, "
                f"staff {mk['staff']}: {mk['name']} {marking_text(mk)}".rstrip()
                + (" (highlighted)" if mk.get("highlighted") else "")
                for mk in m.get("markings", [])
            ]
        if markings:
            text += "\n[Markings]\n" + "\n".join(markings)
        if shown and shown[-1] < total:
            following = bars.label(shown[-1] + 1)
            if not following.lstrip("-").isdigit():
                following = f'"{following}"'
            text += f"\n[More bars: call get_score(start_measure={following}) to continue]"
        return text
