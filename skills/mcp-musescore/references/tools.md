# Public MCP tool reference

This reference describes the tools currently registered by `server.py` and the JSON actions sent to the MuseScore QML plugin. Use the Python function names when calling MCP. Use the camelCase action names only inside `processSequence`.

The server currently registers 26 public tools.

## Connection and score inspection

| MCP tool | Parameters | What it does |
|---|---|---|
| `connect_to_musescore` | none | Opens the WebSocket client connection to `ws://localhost:8765`. Returns `{success: bool}`. |
| `ping_musescore` | none | Sends the `ping` action. A healthy plugin returns `pong`. |
| `get_score` | none | Requests the current score analysis, including title, measure data, staves, voices, durations, lyrics, and pitch information when available. |

Call `ping_musescore` before a mutation. Call `get_score` before and after a complex edit.

## Navigation and selection

| MCP tool | Parameters | What it does |
|---|---|---|
| `get_cursor_info` | none | Reads the current cursor/selection state and the related score context. |
| `go_to_measure` | `measure: int` | Moves the cursor to a zero-based measure index in the plugin's cursor implementation. Verify the result because the UI displays human-facing measure numbers. |
| `go_to_final_measure` | none | Moves to the final measure. |
| `go_to_beginning_of_score` | none | Resets the plugin cursor/selection to the beginning of the score. |
| `next_element` | none | Moves the cursor to the next score element. |
| `prev_element` | none | Moves the cursor to the previous score element. |
| `next_staff` | none | Moves the cursor to the next staff. |
| `prev_staff` | none | Moves the cursor to the previous staff. |
| `select_current_measure` | none | Selects the current measure. |
| `select_custom_range` | `start_tick: int`, `end_tick: int`, `start_staff: int`, `end_staff: int` | Selects a precise tick range across one or more zero-based staves. MuseScore uses 480 ticks per quarter note in this project. |

Navigation wrappers may return a response envelope from the bridge. Read the returned state instead of assuming a move succeeded.

## Notes, rests, lyrics, and measures

Duration values are JSON objects such as `{"numerator": 1, "denominator": 4}` for a quarter note. MIDI pitch 60 is middle C (C4); valid MIDI pitch values are 0–127.

| MCP tool | Parameters | What it does |
|---|---|---|
| `add_note` | `pitch: int = 64`, `duration: dict = {numerator: 1, denominator: 4}`, `advance_cursor_after_action: bool = true` | Adds a note at the current cursor position. |
| `add_rest` | `duration: dict = {numerator: 1, denominator: 4}`, `advance_cursor_after_action: bool = true` | Adds a rest at the current cursor position. |
| `add_tuplet` | `duration: dict = {numerator: 1, denominator: 4}`, `ratio: dict = {numerator: 3, denominator: 2}`, `advance_cursor_after_action: bool = true` | Adds a tuplet; the default ratio represents a triplet. |
| `add_lyrics` | `lyrics: list[str]`, `verse: int = 0` | Adds syllables to consecutive notes from the current cursor. Verse is zero-based. |
| `insert_measure` | none | Inserts a measure at the current position. |
| `append_measure` | `count: int = 1` | Appends one or more measures to the end of the score. |
| `delete_selection` | `measure: int | null = null` | Deletes the current selection, or a specified measure when provided. Treat as destructive and verify immediately. |
| `undo` | none | Undoes the last MuseScore operation. |

## Staff, instruments, and time

| MCP tool | Parameters | What it does |
|---|---|---|
| `add_instrument` | `instrument_id: str` | Adds a staff/instrument using the MuseScore instrument identifier. |
| `set_staff_mute` | `staff: int`, `mute: bool` | Mutes or unmutes a zero-based staff. |
| `set_instrument_sound` | `staff: int`, `instrument_id: str` | Changes the sound/instrument identifier for a zero-based staff. |
| `set_time_signature` | `numerator: int = 4`, `denominator: int = 4` | Sets the time signature at the current score context. |

## Batch execution

| MCP tool | Parameters | What it does |
|---|---|---|
| `processSequence` | `sequence: list[object]` | Sends a list of camelCase actions to the plugin in order. Use only when the complete sequence is known and safe. |

The currently accepted inner actions are:

```text
getScore, addNote, addRest, addTuplet, appendMeasure, deleteSelection,
getCursorInfo, goToMeasure, nextElement, prevElement, nextStaff, prevStaff,
selectCurrentMeasure, processSequence, insertMeasure, goToFinalMeasure,
goToBeginningOfScore, setTimeSignature, addLyrics, addInstrument,
setStaffMute, setInstrumentSound, setTempo
```

Each action uses a `params` object. Examples:

```json
{
  "sequence": [
    {"action": "goToBeginningOfScore", "params": {}},
    {"action": "addNote", "params": {"pitch": 60, "duration": {"numerator": 1, "denominator": 4}, "advanceCursorAfterAction": true}},
    {"action": "addRest", "params": {"duration": {"numerator": 1, "denominator": 4}, "advanceCursorAfterAction": true}}
  ]
}
```

`setTempo` is accepted by the QML sequence dispatcher but does not currently have a direct Python MCP wrapper. `syncStateToSelection` is also an internal QML action, not a public MCP tool.

## Names not currently exposed

The upstream README mentions `add_lyrics_to_current_note` and `set_title`, but the current `src/tools/` registration does not expose those tools. Do not call them as if they existed. They require a future repository change before they can be used through MCP.
