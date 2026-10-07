"""Smoke tests that exercise the MCP server in memory, without MuseScore running."""

import asyncio

from fastmcp import Client

import server


def run(coro):
    return asyncio.run(coro)


def test_tools_are_registered_and_documented():
    async def check():
        async with Client(server.mcp) as client:
            return await client.list_tools()

    tools = run(check())
    assert tools, "no tools registered"

    problems = []
    for tool in tools:
        if not tool.description:
            problems.append(f"{tool.name}: missing description")
        for prop, schema in (tool.input_schema.get("properties") or {}).items():
            if "description" not in schema:
                problems.append(f"{tool.name}.{prop}: missing description")
    assert not problems, "\n".join(problems)


def test_tool_forwards_command_to_musescore(monkeypatch):
    calls = []

    async def fake_send_command(action, params=None):
        calls.append((action, params))
        return {"success": True}

    monkeypatch.setattr(server.client, "send_command", fake_send_command)

    async def call():
        async with Client(server.mcp) as client:
            await client.call_tool("append_measure", {"count": 2})

    run(call())
    assert calls == [("appendMeasure", {"count": 2})]
