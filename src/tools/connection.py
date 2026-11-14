"""Connection and utility tools for MuseScore MCP."""

from typing import Annotated, Any, Dict, List, Literal, Optional

from fastmcp import FastMCP

from ..client import MuseScoreClient

GET_SCORE_WINDOW = 16


def setup_connection_tools(mcp: FastMCP, client: MuseScoreClient) -> None:
    """Setup connection and utility tools."""

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
        return await client.send_command("ping")

    @mcp.tool(
        description=(
            "Get the notes of the current score as LilyPond (or raw JSON), a range of measures at a time. "
            f"Without end_measure, returns at most {GET_SCORE_WINDOW} measures starting at start_measure; "
            "the header says how many measures the score has, so page through long scores. "
            "Use staves to read only some staves of a large score. Each bar ends with '% m.N': N is the bar's "
            "position, which is what every tool's measure parameters mean. When the score's displayed bar numbers "
            "differ (e.g. they count repeats), the displayed number follows as '(bar M)'; repeat barlines show as "
            "'|:' and ':|xN'."
        ),
        tags={"connection", "score"},
    )
    async def get_score(
        start_measure: Annotated[int, "First measure to read (1-based)"] = 1,
        end_measure: Annotated[
            Optional[int],
            f"Last measure to read (1-based, inclusive). Defaults to start_measure + {GET_SCORE_WINDOW - 1}.",
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
        if end_measure is None:
            end_measure = start_measure + GET_SCORE_WINDOW - 1
        params: Dict[str, Any] = {
            "startMeasure": start_measure,
            "endMeasure": end_measure,
        }
        if staves:
            params["staves"] = staves

        res = await client.send_command("getScore", params)
        result = res.get("result")
        if not (
            isinstance(result, dict)
            and result.get("success")
            and isinstance(result.get("analysis"), dict)
        ):
            return res

        analysis = result["analysis"]
        if format == "json":
            return analysis

        from ..utils.lilypond_converter import score_to_lilypond

        lily_str = score_to_lilypond(analysis)

        total = analysis.get("numMeasures")
        shown = [m.get("measure") for m in analysis.get("measures", [])]
        meta = []
        if analysis.get("title"):
            meta.append(f"Titre: {analysis['title']}")
        if total is not None:
            meta.append(f"Total Mesures: {total}")
        if shown:
            meta.append(f"Mesures affichées: {shown[0]}-{shown[-1]}")
        num_staves = len(analysis.get("staves", []))
        if num_staves > 0:
            meta.append(f"Nombre de portées: {num_staves}")

        meta_str = ", ".join(meta) if meta else "Aucune métadonnée"
        text = f"[Métadonnées] {meta_str}\n[Partition]\n{lily_str}"
        markings = [
            f"m.{m['measure']} beat {(mk['startTick'] - m['startTick']) / 480 + 1:g}, staff {mk['staff']}: "
            f"{mk['name']} {mk.get('text', '')}".rstrip()
            + (" (highlighted)" if mk.get("highlighted") else "")
            for m in analysis.get("measures", [])
            for mk in m.get("markings", [])
        ]
        if markings:
            text += "\n[Markings]\n" + "\n".join(markings)
        if shown and total is not None and shown[-1] < total:
            text += f"\n[More measures: call get_score(start_measure={shown[-1] + 1}) to continue]"
        return text
