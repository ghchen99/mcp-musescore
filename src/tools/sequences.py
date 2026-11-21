"""Sequence processing tools for MuseScore MCP."""

from typing import Annotated, Any, Dict, List, cast

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from ..bars import BarNumbers, bar_numbers, send
from ..client import MuseScoreClient
from ..types import SEQUENCE_STEPS, ActionSequence, with_positions


def step_positions(sequence: ActionSequence, bars: BarNumbers) -> List[Dict]:
    """Turn the bars named in a sequence's steps into positions.

    Every params value typed Bar in the step types is a bar, however deep.

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
        if "params" not in step:
            steps.append(step)
            continue
        kind = SEQUENCE_STEPS.get(step.get("action"))
        try:
            params = with_positions(step["params"], kind, bars.position)
        except ToolError as error:
            raise ToolError(
                f"Step {i + 1} ({step.get('action')}): {error}. No step was applied."
            ) from error
        steps.append({**step, "params": params})
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
            f"Allowed actions: {', '.join(SEQUENCE_STEPS)}. "
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
        return await send(
            client,
            bars,
            "processSequence",
            {"sequence": step_positions(sequence, bars)},
        )
