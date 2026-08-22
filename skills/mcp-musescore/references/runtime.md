# Runtime and CLI helpers

## Tested dependency line

The repository currently declares:

```text
mcp[cli]
websockets
```

Because `server.py` imports `mcp.server.fastmcp`, the compatible tested line is:

```text
mcp[cli]==1.29.0
websockets==17.0.1
```

Keep the Python environment isolated in the project venv. Do not put secrets in the skill or client entry.

## Start script

The skill scripts do not install dependencies or alter client configuration. They only launch or probe an already-installed checkout:

```bash
skills/mcp-musescore/scripts/start-mcp-musescore.sh
```

```powershell
& .\skills\mcp-musescore\scripts\start-mcp-musescore.ps1
```

Set `MCP_MUSESCORE_DIR` to override the default `~/Downloads/mcp-musescore` location. Set `MCP_MUSESCORE_PYTHON` to override the Python executable.

## Repository CLI

The upstream README documents `mcp dev server.py` and `mcp dev server.py --inspect` for development/inspection. Use those only when the user asks to inspect the MCP server itself. They do not start the MuseScore QML plugin and do not replace calls to the registered score tools.

## Verification script

`check-mcp-musescore.sh`/`.ps1` compiles the Python package, imports `server.py`, and sends a real `ping` WebSocket action to port 8765. It fails when MuseScore or the plugin is not reachable.
