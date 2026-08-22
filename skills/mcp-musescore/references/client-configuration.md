# MCP client configuration

This skill is client-agnostic. The client must launch the Python MCP server as a stdio process. No secret, public URL, or HTTP proxy is needed.

The command is conceptually:

```text
<project-venv-python> <project>/server.py
```

Use absolute paths in client configuration. The default project location used by the helper scripts is `~/Downloads/mcp-musescore`; set `MCP_MUSESCORE_DIR` when using another location.

## Claude Code

Claude Code can add a user-scoped stdio server with:

```bash
claude mcp add --scope user musescore -- \
  "$HOME/Downloads/mcp-musescore/.venv/bin/python" \
  "$HOME/Downloads/mcp-musescore/server.py"
```

Verify with:

```bash
claude mcp get musescore
claude mcp list
```

On Windows PowerShell:

```powershell
claude mcp add --scope user musescore -- `
  "$HOME\Downloads\mcp-musescore\.venv\Scripts\python.exe" `
  "$HOME\Downloads\mcp-musescore\server.py"
```

## Codex CLI

Codex can add the same stdio server to the user configuration:

```bash
codex mcp add musescore -- \
  "$HOME/Downloads/mcp-musescore/.venv/bin/python" \
  "$HOME/Downloads/mcp-musescore/server.py"
```

Verify with `codex mcp get musescore` and `codex mcp list`.

## Claude Desktop

Add this object under `mcpServers` in the Claude Desktop configuration, adapting the paths:

```json
{
  "musescore": {
    "command": "/absolute/path/to/mcp-musescore/.venv/bin/python",
    "args": ["/absolute/path/to/mcp-musescore/server.py"]
  }
}
```

The server is stdio. Do not configure `ws://localhost:8765` as the MCP endpoint; that port belongs to the MuseScore plugin and is not an MCP transport.

## Other MCP clients

Choose a local/stdio server entry with the venv Python as the command and `server.py` as its only argument. If the client starts the server on demand, no separate background backend is needed. The MuseScore plugin still has to be running for tool calls to succeed.
