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

The current Python wrappers sometimes test the inner `success` key without first unwrapping `status/result`. If a read tool returns the raw envelope, use `result`/`result.analysis` as the authoritative score data and do not claim that a formatted LilyPond response was produced.

## Files and versions

- Plugin source: `musescore-mcp-websocket.qml`.
- Python entry point: `server.py`.
- Dependency declaration: `requirements.txt`.
- The current source imports `mcp.server.fastmcp`; the tested compatible dependency line is `mcp[cli]==1.29.0` with `websockets==17.0.1`. Do not silently upgrade the MCP package to a major version that removes that import.
- The upstream project documents MuseScore 3.x and 4.x, but this integration was verified with MuseScore Studio 4.7.4 on macOS. Treat other versions as needing a bridge check.

## Failure diagnosis

- `Not connected to MuseScore`: the plugin is not running, the port is unavailable, or MuseScore closed/reloaded the plugin.
- `Unknown command`: the requested action is not in the QML dispatcher or is using the wrong camelCase spelling.
- Empty or stale score data: refresh the plugin/cursor state and call `get_score` again.
- Python import failure: inspect the venv and the installed MCP version; the unpinned upstream requirement may have selected an incompatible major version.
