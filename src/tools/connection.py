"""Connection and utility tools for MuseScore MCP."""

from ..client import MuseScoreClient


def setup_connection_tools(mcp, client: MuseScoreClient):
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
        description="Get information about the current score.",
        tags={"connection", "score"},
    )
    async def get_score():
        res = await client.send_command("getScore")
        if res.get("success") and "analysis" in res:
            from ..utils.lilypond_converter import json_to_lilypond
            analysis = res["analysis"]
            lily_str = json_to_lilypond(analysis)
            
            meta = []
            if "numMeasures" in analysis:
                meta.append(f"Total Mesures: {analysis['numMeasures']}")
                
            num_staves = len(analysis.get("staves", []))
            if num_staves > 0:
                meta.append(f"Nombre de portées: {num_staves}")
                
            meta_str = ", ".join(meta) if meta else "Aucune métadonnée"
            
            return f"[Métadonnées] {meta_str}\n[Partition]\n{lily_str}"
        return res