"""Checks against the step types, the one list of the plugin's actions."""

import asyncio
import re
from pathlib import Path

import pytest
from fastmcp import Client
from mock_musescore import MockMuseScore, MockScore

import server
from src.types import SEQUENCE_STEPS

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = (ROOT / "musescore-mcp-websocket.qml").read_text(encoding="utf-8")

MOCK_GAPS = {
    "addTuplet",
    "deleteSelection",
    "insertMeasure",
    "nextElement",
    "prevElement",
    "nextStaff",
    "prevStaff",
    "selectCurrentMeasure",
    "selectCustomRange",
    "setStaffMute",
    "setInstrumentSound",
    "syncStateToSelection",
}
"""Plugin commands the mock does not implement yet. Tests of them run against
the real plugin only.
"""


def plugin_sequence_actions():
    block = re.search(r"var validCommands = \[(.*?)\];", PLUGIN, re.S)
    assert block, "validCommands not found in the plugin"
    return set(re.findall(r'"(\w+)"', block.group(1)))


def plugin_commands():
    body = re.search(
        r"function processCommand\(command\) \{(.*?)default:", PLUGIN, re.S
    )
    assert body, "processCommand not found in the plugin"
    return set(re.findall(r'case "(\w+)":', body.group(1)))


def mock_commands():
    return {
        name.removeprefix("_do_")
        for name in dir(MockMuseScore)
        if name.startswith("_do_")
    }


def test_the_plugin_runs_exactly_the_registered_steps():
    # processSequence may nest in the plugin; the step types don't offer it
    assert plugin_sequence_actions() - {"processSequence"} == set(
        SEQUENCE_STEPS
    )


def test_every_registered_step_is_a_plugin_command():
    assert set(SEQUENCE_STEPS) <= plugin_commands()


def test_the_mock_implements_every_plugin_command_but_the_known_gaps():
    plugin, mock = plugin_commands(), mock_commands()
    assert mock <= plugin, f"the plugin has no {sorted(mock - plugin)}"
    assert plugin - mock == MOCK_GAPS, (
        "update MOCK_GAPS: "
        f"newly missing {sorted(plugin - mock - MOCK_GAPS)}, "
        f"now implemented {sorted(MOCK_GAPS - (plugin - mock))}"
    )


def test_the_mock_refuses_a_parameter_no_step_type_names():
    mock = MockMuseScore(MockScore(measures=2))
    reply = mock.handle_message(
        '{"action": "goToMeasure", "params": {"measure": 1, "bar": 2}}'
    )
    assert reply["status"] == "error"
    assert "bar" in reply["message"]


@pytest.mark.parametrize(
    "docs",
    [
        ("docs/tools.md", "docs/drum-charts.md"),
        ("skills/mcp-musescore/references/tools.md",),
    ],
)
def test_every_tool_is_documented(docs):
    async def names():
        async with Client(server.mcp) as client:
            return [t.name for t in await client.list_tools()]

    doc = " and ".join(docs)
    text = "".join((ROOT / d).read_text(encoding="utf-8") for d in docs)
    missing = [
        n for n in asyncio.run(names()) if not re.search(rf"`{n}[`(]", text)
    ]
    assert not missing, f"{doc} does not mention {missing}"
