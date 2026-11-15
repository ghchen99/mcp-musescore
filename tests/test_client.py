"""Tests for MuseScoreClient against small WebSocket servers.

Each server stands in for the plugin in one situation the client must handle: a
plugin that never answers, a connection dropped mid-command, and so on.
"""

import asyncio
import json
from contextlib import asynccontextmanager

import pytest
from fastmcp.exceptions import ToolError
from websockets.asyncio.server import serve

from src.client import MuseScoreClient


@asynccontextmanager
async def plugin(handler):
    """Run a stand-in plugin with the given connection handler.

    Args:
        handler: The websockets connection handler.

    Yields:
        port (int): The port it listens on.
    """
    async with serve(handler, "127.0.0.1", 0) as server:
        yield next(iter(server.sockets)).getsockname()[1]


def reply(command, result):
    """Build the plugin's success reply."""
    return json.dumps({"status": "success", "result": result})


def test_a_plugin_that_never_answers_times_out():
    received = []

    async def silent(ws):
        async for message in ws:
            received.append(json.loads(message))

    async def scenario():
        async with plugin(silent) as port:
            client = MuseScoreClient(host="127.0.0.1", port=port, timeout=0.2)
            with pytest.raises(ToolError, match="did not answer"):
                await asyncio.wait_for(client.request("ping"), 5)
            await client.close()
        assert received == [{"action": "ping", "params": {}}]

    asyncio.run(scenario())


def test_concurrent_requests_each_get_their_own_reply():
    received = []

    async def one_at_a_time(ws):
        async for message in ws:
            command = json.loads(message)
            received.append(command["action"])
            if command["action"] == "slow":
                await asyncio.sleep(0.2)
            await ws.send(reply(command, {"action": command["action"]}))

    async def scenario():
        async with plugin(one_at_a_time) as port:
            client = MuseScoreClient(host="127.0.0.1", port=port, timeout=5)
            await client.connect()
            slow, fast = await asyncio.gather(
                client.request("slow"), client.request("fast")
            )
            await client.close()
        assert slow == {"action": "slow"}
        assert fast == {"action": "fast"}
        assert sorted(received) == ["fast", "slow"]

    asyncio.run(scenario())


def test_a_command_lost_after_sending_is_not_sent_again():
    received = []

    async def drops_after_receiving(ws):
        async for message in ws:
            received.append(json.loads(message)["action"])
            await ws.close()

    async def scenario():
        async with plugin(drops_after_receiving) as port:
            client = MuseScoreClient(host="127.0.0.1", port=port, timeout=5)
            with pytest.raises(ToolError, match="may have been applied"):
                await client.request("addNote")
            await client.close()
        assert received == ["addNote"]

    asyncio.run(scenario())


def test_a_restarted_plugin_is_reconnected_to():
    received = []

    async def answers(ws):
        async for message in ws:
            command = json.loads(message)
            received.append(command["action"])
            await ws.send(reply(command, {"ok": True}))

    async def scenario():
        async with plugin(answers) as port:
            client = MuseScoreClient(host="127.0.0.1", port=port, timeout=5)
            assert await client.request("before") == {"ok": True}
        # The plugin is gone and comes back on the same port, like a MuseScore restart.
        await asyncio.sleep(0.1)
        async with serve(answers, "127.0.0.1", port):
            assert await client.request("after") == {"ok": True}
            await client.close()
        assert received == ["before", "after"]

    asyncio.run(scenario())
