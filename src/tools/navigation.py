"""Cursor and navigation tools for MuseScore MCP."""

from typing import Annotated

from ..client import MuseScoreClient


def setup_navigation_tools(mcp, client: MuseScoreClient):
    """Setup cursor and navigation tools."""
    
    async def _run_and_convert(action: str, params=None):
        res = await client.send_command(action, params)
        if res.get("success") and "currentSelection" in res:
            from ..utils.lilypond_converter import json_to_lilypond
            sel = res["currentSelection"]
            lily_str = json_to_lilypond(sel)
            
            meta = []
            score_info = res.get("currentScore", {})
            if not isinstance(score_info, dict):
                score_info = {}
                
            if "startTick" in sel:
                tick = sel["startTick"]
                # Default math fallback
                measure_num = (tick // 1920) + 1
                beat_num = ((tick % 1920) // 480) + 1
                
                if "measures" in score_info:
                    measures = score_info["measures"]
                    # Sort and find
                    measures = sorted(measures, key=lambda m: m.get("startTick", 0))
                    current_m = measures[0] if measures else {}
                    for i, m in enumerate(measures):
                        if m.get("startTick", 0) > tick:
                            break
                        current_m = m
                    measure_num = current_m.get("measure", measure_num)
                    m_start = current_m.get("startTick", 0)
                    beat_num = (max(0, tick - m_start) // 480) + 1

                meta.append(f"Mesure: {measure_num}")
                meta.append(f"Temps: {beat_num}")
                
            if "startStaff" in sel:
                start_s = sel["startStaff"]
                end_s = sel.get("endStaff", start_s)
                staff_name = f"{start_s}-{end_s}" if start_s != end_s else str(start_s)
                
                if "staves" in score_info:
                    staves = score_info["staves"]
                    if 0 <= start_s < len(staves):
                        st_info = staves[start_s]
                        name = st_info.get("shortName") or st_info.get("name")
                        if name:
                            staff_name = name
                            
                meta.append(f"Portée: {staff_name}")
            
            if "title" in score_info and score_info["title"]:
                meta.append(f"Titre: {score_info['title']}")
            if "numMeasures" in score_info:
                meta.append(f"Total Mesures: {score_info['numMeasures']}")
            
            meta_str = ", ".join(meta) if meta else "Aucune métadonnée"
            return f"[Métadonnées] {meta_str}\n[Partition]\n{lily_str}"
        return res
        return res

    @mcp.tool(
        description="Get information about the current cursor position.",
        tags={"navigation"},
    )
    async def get_cursor_info():
        return await _run_and_convert("getCursorInfo")

    @mcp.tool(
        description="Navigate to a specific measure and select it across all staves.",
        tags={"navigation"},
    )
    async def go_to_measure(
        measure: Annotated[int, "Measure number (1-based, must not exceed the number of measures in the score)"],
    ):
        return await _run_and_convert("goToMeasure", {"measure": measure})

    @mcp.tool(
        description="Navigate to the final measure of the score.",
        tags={"navigation"},
    )
    async def go_to_final_measure():
        return await _run_and_convert("goToFinalMeasure")

    @mcp.tool(
        description="Navigate to the beginning of the score.",
        tags={"navigation"},
    )
    async def go_to_beginning_of_score():
        return await _run_and_convert("goToBeginningOfScore")

    @mcp.tool(
        description="Move cursor to the next element.",
        tags={"navigation"},
    )
    async def next_element():
        return await _run_and_convert("nextElement")

    @mcp.tool(
        description="Move cursor to the previous element.",
        tags={"navigation"},
    )
    async def prev_element():
        return await _run_and_convert("prevElement")

    @mcp.tool(
        description="Move cursor to the next staff.",
        tags={"navigation"},
    )
    async def next_staff():
        return await _run_and_convert("nextStaff")

    @mcp.tool(
        description="Move cursor to the previous staff.",
        tags={"navigation"},
    )
    async def prev_staff():
        return await _run_and_convert("prevStaff")

    @mcp.tool(
        description="Select the current measure.",
        tags={"navigation"},
    )
    async def select_current_measure():
        return await _run_and_convert("selectCurrentMeasure")
        
    @mcp.tool(
        description=(
            "Select a custom range of ticks across staves. "
            "Useful for retrieving continuous phrasing that spans measure boundaries."
        ),
        tags={"navigation"},
    )
    async def select_custom_range(
        start_tick: Annotated[int, "Start of the range in ticks (0-based; a quarter note is 480 ticks, so a 4/4 measure is 1920)"],
        end_tick: Annotated[int, "End of the range in ticks (exclusive)"],
        start_staff: Annotated[int, "First staff index (0-based)"],
        end_staff: Annotated[int, "Last staff index (0-based)"],
    ):
        params = {
            "startTick": start_tick,
            "endTick": end_tick,
            "startStaff": start_staff,
            "endStaff": end_staff
        }
        return await _run_and_convert("selectCustomRange", params)