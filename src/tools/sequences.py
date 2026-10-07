"""Sequence processing tools for MuseScore MCP."""

from typing import Annotated

from ..client import MuseScoreClient
from ..types import ActionSequence


def setup_sequence_tools(mcp, client: MuseScoreClient):
    """Setup sequence processing tools."""
    
    @mcp.tool(
        description=(
            "Run several score commands in order in a single call. "
            'Each item is {"action": <name>, "params": {...}}, using the same camelCase action names '
            'and parameters as the plugin (e.g. "addNote" with pitch, duration, advanceCursorAfterAction). '
            "Allowed actions: getScore, addNote, addRest, addTuplet, appendMeasure, deleteSelection, "
            "getCursorInfo, goToMeasure, nextElement, prevElement, nextStaff, prevStaff, "
            "selectCurrentMeasure, insertMeasure, goToFinalMeasure, goToBeginningOfScore, "
            "setTimeSignature, addLyrics, addInstrument, setStaffMute, setInstrumentSound, setTempo. "
            "Processing stops at the first invalid action."
        ),
        tags={"sequence"},
    )
    async def processSequence(
        sequence: Annotated[
            ActionSequence,
            'Ordered list of actions, e.g. [{"action": "goToMeasure", "params": {"measure": 1}}, '
            '{"action": "addNote", "params": {"pitch": 60, "duration": {"numerator": 1, "denominator": 4}, '
            '"advanceCursorAfterAction": true}}]',
        ],
    ):
        return await client.send_command("processSequence", {"sequence": sequence})