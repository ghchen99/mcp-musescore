#!/usr/bin/env python3
"""Send one real ping through the MuseScore plugin WebSocket."""

import asyncio
import json
import os
import sys

import websockets


async def main() -> None:
    """Ping the plugin and check that it answers "pong".

    The plugin's address comes from MCP_MUSESCORE_HOST and MCP_MUSESCORE_PORT
    (default localhost:8765).

    Raises:
        RuntimeError: If the plugin's reply is not a successful "pong".
    """
    host = os.environ.get("MCP_MUSESCORE_HOST", "localhost")
    port = int(os.environ.get("MCP_MUSESCORE_PORT", "8765"))
    uri = f"ws://{host}:{port}"
    async with websockets.connect(uri) as websocket:
        await websocket.send(json.dumps({"action": "ping", "params": {}}))
        response = json.loads(await websocket.recv())
    if response.get("status") != "success" or response.get("result") != "pong":
        raise RuntimeError(
            f"Unexpected MuseScore bridge response: {response!r}"
        )
    print(f"MuseScore bridge OK: {uri}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(f"MuseScore bridge check failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
