# Architecture and connection model

```text
Claude Code / Codex / another MCP client
                 │ MCP stdio
                 ▼
server.py ─ FastMCP("MuseScore Assistant")
                 │ src/tools/*
                 ▼
MuseScoreClient ─ WebSocket ws://localhost:8765
                 │ JSON actions
                 ▼
musescore-mcp-websocket.qml ─ MuseScore plugin API
                 ▼
open score in MuseScore Studio
```

## Components

- `server.py` creates the FastMCP server and registers the public Python tools.
- `src/tools/` translates typed MCP calls into camelCase JSON actions.
- `src/client/websocket_client.py` owns the localhost WebSocket connection and retries once after a stale socket.
- `musescore-mcp-websocket.qml` runs inside MuseScore and exposes a WebSocket server on port 8765.
- `src/utils/lilypond_converter.py` converts score analysis/selection data into LilyPond text for supported read paths.

## Startup order

1. Start MuseScore Studio and open a score.
2. Enable the plugin once in MuseScore's plugin manager.
3. Run `Plugins > musescore-mcp-websocket`.
4. Let the MCP client launch `server.py` over stdio, or run the skill's start script manually.
5. Call `ping_musescore` before using a score tool.

The Python backend is not the WebSocket server. The QML plugin is the process that listens on port 8765. Starting only `server.py` cannot make MuseScore reachable.

## Wire format

The Python client sends:

```json
{"action": "ping", "params": {}}
```

The QML plugin replies with a success envelope:

```json
{"status": "success", "result": "pong"}
```

Errors use:

```json
{"status": "error", "message": "..."}
```

A command the plugin refuses comes back as `{"status": "success", "result": {"error": "..."}}`. Every tool unwraps the envelope: on success it returns `result` (or, for `get_score` and the navigation tools, LilyPond text), and on either kind of error it raises an MCP tool error with the plugin's message. `ping_musescore` checks for the bare `pong` and returns `{"success": true, "message": "pong"}`.

## Files and versions

- Plugin source: `musescore-mcp-websocket.qml`.
- Python entry point: `server.py`.
- Dependency declaration: `pyproject.toml`, with the exact versions in `uv.lock`. `requirements.txt` is generated from `uv.lock` for setups without uv.
- The current source imports `fastmcp` (standalone FastMCP 4, declared as `fastmcp>=4.1,<5` in `pyproject.toml`).
- Supported MuseScore versions: 4.7 or newer. MuseScore 3 is not supported. CI runs the full test suite on MuseScore 4.7.0 and on the latest release; this integration was first verified with MuseScore Studio 4.7.4 on macOS.

## Failure diagnosis

- `Not connected to MuseScore`: the plugin is not running, the port is unavailable, or MuseScore closed/reloaded the plugin.
- `Unknown command`: the requested action is not in the QML dispatcher or is using the wrong camelCase spelling.
- Empty or stale score data: refresh the plugin/cursor state and call `get_score` again.
- Python import failure: inspect the venv and the installed MCP version; the unpinned upstream requirement may have selected an incompatible major version.
