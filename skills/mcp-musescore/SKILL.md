---
name: mcp-musescore
description: Use the ghchen99/mcp-musescore MCP server to inspect, navigate, compose, and edit an open MuseScore score through its QML WebSocket plugin.
metadata:
  short-description: Control an open MuseScore score
---

# MuseScore MCP

Use this skill when a user asks to inspect, compose, edit, navigate, or analyze a score in MuseScore through the configured `mcp-musescore` server.

## Read the right detail

- Read [references/tools.md](references/tools.md) before choosing a tool or constructing a batch sequence. It is the source of truth for the 26 public MCP tools, parameters, defaults, and upstream README discrepancies.
- Read [references/architecture.md](references/architecture.md) when diagnosing connection, plugin, port, response-envelope, or MuseScore-version problems.
- Read [references/client-configuration.md](references/client-configuration.md) when a client needs a stdio configuration.
- Read [references/runtime.md](references/runtime.md) when installing, selecting a Python runtime, or using the repository's CLI helpers.

## Routing rule

Prefer a purpose-built CLI command when it is actually available in the current environment for the requested operation. If no such CLI command is available, use the public MCP tools documented in `references/tools.md`. Never invent a MuseScore CLI command. The repository's `mcp dev` command is an MCP inspector/development helper; it is not a replacement for the live MuseScore editing tools.

## Preconditions and startup

- MuseScore Studio must be open with a score loaded.
- The `musescore-mcp-websocket.qml` plugin must be enabled and running from MuseScore's Plugins menu.
- The plugin must listen on `ws://localhost:8765`.
- The MCP client must launch the repository's `server.py` over stdio. Use `scripts/start-mcp-musescore.sh` or `scripts/start-mcp-musescore.ps1` for a manual launch; set `MCP_MUSESCORE_DIR` when the repository is not in `~/Downloads/mcp-musescore`.
- Run `scripts/check-mcp-musescore.sh` or its PowerShell equivalent when a deterministic bridge probe is needed.

If a tool reports `Not connected to MuseScore`, do not retry mutations blindly: start or reload the MuseScore plugin, call `ping_musescore`, and only then continue.

## Operating sequence

1. Call `ping_musescore` to verify the bridge.
2. Call `get_score` before editing so the current title, measures, staves, and score state are known.
3. Use navigation and selection tools to place the cursor precisely.
4. Use a direct mutation for one or two deliberate edits; use `processSequence` for a known batch.
5. Call `get_score` or a navigation tool after each mutation batch and report what was verified.
6. Saving or exporting `.mscz`, PDF, or audio remains a MuseScore UI action unless another configured tool provides it.

## Guardrails

- Do not claim that an edit succeeded without a follow-up read from MuseScore.
- Preserve the user's score, cursor, and selection unless the requested operation changes them.
- Confirm pitch, duration, staff, voice, measure, and cursor-advance intent before destructive or cumulative edits.
- Use `undo` when a just-made mutation is wrong and the score state is still safe to reverse.
- Treat the JSON returned by the bridge as authoritative. The upstream README contains historical names such as `add_lyrics_to_current_note` and `set_title` that are not currently registered public MCP tools; do not call them unless the repository exposes them in a future version.
- `processSequence` is camelCase because that is the registered Python tool name. Its inner `action` values are also camelCase QML actions; see the reference for the supported set.

## Portability

This folder is a normal `SKILL.md` skill for Claude Code and compatible loaders. Codex also uses `agents/openai.yaml` for UI metadata. The skill does not embed secrets, API keys, or machine-specific absolute paths.

## Guardrails

- Treat the score returned by `get_score` as the source of truth; do not claim an edit succeeded without a follow-up read.
- Preserve the user's existing score and selection unless the requested operation requires changing them.
- Saving or exporting `.mscz`, PDF, or audio remains a MuseScore application action unless another configured tool is available.
