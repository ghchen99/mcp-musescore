---
name: mcp-musescore
description: Use the ghchen99/mcp-musescore MCP server to inspect, navigate, compose, and edit an open MuseScore score through its QML WebSocket plugin.
metadata:
  short-description: Control an open MuseScore score with MCP
---

# mcp-musescore

Use this skill when the user wants to read or edit a score in MuseScore through a configured `mcp-musescore` MCP server.

## Preconditions

- MuseScore Studio is open with a score loaded.
- The `musescore-mcp-websocket` plugin is running in MuseScore and listening on `localhost:8765`.
- The MCP client has a stdio entry for the repository's `server.py`.

If a tool reports `Not connected to MuseScore`, start the plugin and call `ping_musescore` again.

## Operating sequence

1. Call `ping_musescore` to verify the bridge.
2. Call `get_score` before editing so the current score structure is known.
3. Use navigation and selection tools before mutations.
4. Use `processSequence` for a deliberate batch of note, rest, lyric, or measure operations.
5. After every mutation, call `get_score` or a navigation tool to verify the result.

## Tool groups

- Connection: `connect_to_musescore`, `ping_musescore`, `get_score`.
- Navigation and selection: `get_cursor_info`, `go_to_measure`, `go_to_final_measure`, `go_to_beginning_of_score`, `next_element`, `prev_element`, `next_staff`, `prev_staff`, `select_current_measure`, `select_custom_range`.
- Notes and measures: `add_note`, `add_rest`, `add_tuplet`, `add_lyrics`, `insert_measure`, `append_measure`, `delete_selection`, `undo`.
- Score setup: `add_instrument`, `set_staff_mute`, `set_instrument_sound`, `set_time_signature`, `processSequence`.

## Guardrails

- Treat the score returned by `get_score` as the source of truth; do not claim an edit succeeded without a follow-up read.
- Preserve the user's existing score and selection unless the requested operation requires changing them.
- Saving or exporting `.mscz`, PDF, or audio remains a MuseScore application action unless another configured tool is available.
