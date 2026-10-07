"""Integration tests: real MCP tools and WebSocket client against the in-memory mock plugin."""

import asyncio

from fastmcp import Client

import server
from mock_musescore import MockScore, demo_score, running_mock

QUARTER = {"numerator": 1, "denominator": 4}


def run_with_mock(scenario, score=None):
    """Run `scenario(mcp_client, mock)` with server.client pointed at a mock plugin."""

    async def runner():
        original_uri = server.client.uri
        async with running_mock(score) as mock:
            server.client.uri = mock.uri
            server.client.websocket = None
            try:
                async with Client(server.mcp) as mcp_client:
                    await scenario(mcp_client, mock)
            finally:
                await server.client.close()
                server.client.uri = original_uri

    asyncio.run(runner())


def test_ping_reaches_plugin():
    async def scenario(c, mock):
        await c.call_tool("ping_musescore", {})
        assert mock.commands == [{"action": "ping", "params": {}}]

    run_with_mock(scenario)


def test_melody_is_written_sequentially():
    async def scenario(c, mock):
        for pitch in (60, 62, 64):
            await c.call_tool("add_note", {"pitch": pitch, "duration": QUARTER})
        chords = mock.score.elements[0]
        assert [e["notes"][0]["pitchMidi"] for e in chords] == [60, 62, 64]
        assert [e["startTick"] for e in chords] == [0, 480, 960]

    run_with_mock(scenario)


def test_add_to_chord_stacks_pitches():
    async def scenario(c, mock):
        await c.call_tool(
            "add_note", {"pitch": 60, "duration": QUARTER, "advance_cursor_after_action": False}
        )
        await c.call_tool("add_note", {"pitch": 64, "duration": QUARTER, "add_to_chord": True})
        (chord,) = mock.score.elements[0]
        assert [n["pitchMidi"] for n in chord["notes"]] == [60, 64]

    run_with_mock(scenario)


def test_process_sequence_runs_actions_in_order():
    sequence = [
        {"action": "goToMeasure", "params": {"measure": 2}},
        {"action": "addRest", "params": {"duration": QUARTER, "advanceCursorAfterAction": True}},
        {
            "action": "addNote",
            "params": {"pitch": 67, "duration": QUARTER, "advanceCursorAfterAction": True},
        },
    ]

    async def scenario(c, mock):
        await c.call_tool("processSequence", {"sequence": sequence})
        names = [(e["name"], e["startTick"]) for e in mock.score.elements[0]]
        assert names == [("Rest", 1920), ("Chord", 2400)]

    run_with_mock(scenario)


def test_undo_reverts_last_edit():
    async def scenario(c, mock):
        await c.call_tool("add_note", {"pitch": 60, "duration": QUARTER})
        await c.call_tool("undo", {})
        assert mock.score.elements[0] == []

    run_with_mock(scenario)


def test_append_measure_and_get_score():
    async def scenario(c, mock):
        await c.call_tool("append_measure", {"count": 2})
        assert mock.score.num_measures == 6
        await c.call_tool("get_score", {})
        assert mock.commands[-1]["action"] == "getScore"

    run_with_mock(scenario, MockScore(measures=4))


def test_plugin_errors_surface_in_result():
    async def scenario(c, mock):
        result = await c.call_tool("go_to_measure", {"measure": 99})
        assert "Invalid measure number" in str(result)

    run_with_mock(scenario)


def test_show_score_returns_structured_score_for_the_viewer():
    async def scenario(c, mock):
        result = await c.call_tool("show_score", {"first_measure": 2, "last_measure": 3})
        score = result.structured_content
        assert [m["measure"] for m in score["measures"]] == [2, 3]
        assert score["measureTicks"] == 1920
        assert score["title"] == "Twinkle Twinkle (demo)"
        assert "2 of 4" in result.content[0].text

    run_with_mock(scenario, demo_score())


def test_show_score_declares_its_ui_resource_and_serves_it():
    async def scenario(c, mock):
        tools = {t.name: t for t in await c.list_tools()}
        assert tools["show_score"].meta["ui"]["resourceUri"] == "ui://musescore/score-viewer.html"
        (page,) = await c.read_resource("ui://musescore/score-viewer.html")
        assert page.mime_type == "text/html;profile=mcp-app"
        assert "Vex.Flow" in page.text

    run_with_mock(scenario)
