# Runtime and CLI helpers

## Tested dependency line

`pyproject.toml` declares the runtime dependencies, and `uv.lock` pins the exact tested versions:

```text
fastmcp>=4.1,<5
pydantic>=2.12
websockets>=14
```

`server.py` imports `from fastmcp import FastMCP` (standalone FastMCP 4, built on MCP SDK v2).

Keep the Python environment isolated in the project venv. Create it with `uv sync` in the repository: uv puts it in `.venv`, where the start and check scripts look for it. Do not put secrets in the skill or client entry.

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

The upstream README documents `fastmcp dev inspector server.py` and `fastmcp inspect server.py` for development/inspection. Use those only when the user asks to inspect the MCP server itself. They do not start the MuseScore QML plugin and do not replace calls to the registered score tools.

## Verification script

`check-mcp-musescore.sh`/`.ps1` compiles the Python package, imports `server.py`, and sends a real `ping` WebSocket action to port 8765. It fails when MuseScore or the plugin is not reachable.
