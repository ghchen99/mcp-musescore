"""Sequence processing tools for MuseScore MCP."""

from typing import Annotated, Any, Dict, List, cast

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from ..bars import BarNumbers, bar_numbers
from ..client import MuseScoreClient, unwrap_result
from ..types import ActionSequence

BAR_PARAMS = ("measure", "startMeasure", "endMeasure", "toMeasure")
"""Step parameters that name a bar."""


def step_positions(sequence: ActionSequence, bars: BarNumbers) -> List[Dict]:
    """Turn the bars named in a sequence's steps into positions.

    Args:
        sequence (ActionSequence): The steps, bars as printed.
        bars (BarNumbers): The score's printed bar numbers.

    Returns:
        sequence (List[Dict]): Copies of the steps, measures by position.

    Raises:
        ToolError: If a step names a bar that is not printed so.
    """
    steps = []
    for i, typed in enumerate(sequence):
        step = cast(Dict[str, Any], typed)
        params = dict(step.get("params") or {})
        try:
            for key in BAR_PARAMS:
                if params.get(key) is not None:
                    params[key] = bars.position(params[key])
            if isinstance(params.get("exclude"), list):
                params["exclude"] = [
                    bars.position(b) for b in params["exclude"]
                ]
            if isinstance(params.get("counts"), list):
                params["counts"] = [
                    {**c, "measure": bars.position(c["measure"])}
                    if isinstance(c, dict) and "measure" in c
                    else c
                    for c in params["counts"]
                ]
        except ToolError as error:
            raise ToolError(
                f"Step {i + 1} ({step.get('action')}): {error}. No step was applied."
            ) from error
        steps.append({**step, "params": params} if "params" in step else step)
    return steps


def setup_sequence_tools(mcp: FastMCP, client: MuseScoreClient) -> None:
    """Register the tool that runs a sequence of plugin actions.

    Args:
        mcp (FastMCP): The server to register the tools on.
        client (MuseScoreClient): The client the tools send their commands
            through.
    """

    @mcp.tool(
        description=(
            "Run several score commands in order in a single call. "
            'Each item is {"action": <name>, "params": {...}}, using the same camelCase action names '
            'and parameters as the plugin (e.g. "addNote" with pitch, duration, advanceCursorAfterAction). '
            "Allowed actions: getScore, addNote, addTie, addTiedNote, addRest, addTuplet, appendMeasure, deleteSelection, "
            "getCursorInfo, goToMeasure, nextElement, prevElement, nextStaff, prevStaff, "
            "selectCurrentMeasure, insertMeasure, goToFinalMeasure, goToBeginningOfScore, "
            "setTimeSignature, addLyrics, addInstrument, setStaffMute, setInstrumentSound, setTempo, "
            "selectMeasures, deleteMeasures, setRepeatBarlines, addVolta, colorRange, setStyle, "
            "addRehearsalMark, addMarker, setChordSymbol, moveChordSymbol, addBreak, setMeasuresPerSystem, findElements, setProperties, setMeasureStretch, removeParts, addHighlight, addLabel, clearHighlights, highlightNotes, "
            "highlightMarkings, highlightSymbols, setMeasureNumbering, numberAsPlayed, addText, removeAnnotations, "
            "addArticulation, removeArticulations, ghostNotes, beamOverRests, addSectionCounts. "
            "Bars (measure, toMeasure, startMeasure/endMeasure, inclusive) are as printed in the score before the sequence "
            'runs (a pickup bar is 0; a number printed twice is "12a"/"12b"), even after a step that inserts or '
            "deletes bars; staves use startStaff/endStaff (0-based, endStaff exclusive). "
            "Processing stops at the first invalid action or failing step, and the error names it; "
            "the steps before it stay applied."
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
        bars = await bar_numbers(client)
        reply = await client.send_command(
            "processSequence", {"sequence": step_positions(sequence, bars)}
        )
        try:
            unwrap_result(reply)  # raises ToolError when a step failed
        except ToolError as error:
            raise ToolError(bars.relabel_text(str(error))) from error
        return bars.relabel(reply)
