# Tool reference

[Overview](../README.md) · [Setup](setup.md) · [Tools](tools.md) · [Repeats & drum charts](drum-charts.md) · [Skills](skills.md) · [Development](development.md) · [Troubleshooting](troubleshooting.md)

Measure numbers are 1-based and staff indices 0-based throughout. Ranges are inclusive (`start_measure`..`end_measure`, `first_staff`..`last_staff`). Tools address bars by their position in the score; when the displayed bar numbers differ (for example after `number_bars_as_played`), `get_score` shows both.

Repeats, drum charts and drum notation have [their own page](drum-charts.md).

## Reading the Score
- `get_score(start_measure, end_measure, staves, format)` - Read the score as LilyPond (`format="json"` for the raw analysis), 16 measures at a time by default, optionally only some staves. Each staff is reported with its instrument name, and markings such as dynamics are listed per measure
- `show_score(first_measure, last_measure)` - Render the score as sheet music in an interactive viewer (see [Score viewer](#score-viewer-mcp-apps))
- `ping_musescore()` - Test connection to MuseScore
- `connect_to_musescore()` - Establish WebSocket connection

## Navigation & Cursor Control
- `get_cursor_info()` - Get current cursor position and selection info
- `go_to_measure(measure)` - Select a measure on every staff and move the cursor to its first beat on staff 0. The next cursor tool (`add_note`, `add_rest`, `add_lyrics`, `set_time_signature`...) acts there; follow with `next_staff()` to write on another staff
- `go_to_beginning_of_score()` / `go_to_final_measure()` - Navigate to start/end
- `next_element()` / `prev_element()` - Move cursor element by element
- `next_staff()` / `prev_staff()` - Move between staves
- `select_current_measure()` - Select the whole measure the cursor is in, on every staff (the cursor moves to its first beat on staff 0)
- `select_custom_range(start_tick, end_tick, start_staff, end_staff)` - Slicing tool to extract cross-measure, multi-staff phrasing

Navigation results come back as LilyPond with measure, beat and staff metadata.

## Polyphony & LilyPond Integration
- **Temporal Rhythm Padding**: Voices with gaps or rests automatically receive LilyPond spacer sequences (`s4.`) to hold their mathematical place accurately.
- **Concurrent Voice Rendering**: Full 4-voice (`\voiceOne`, `\voiceTwo`, etc.) arrays correctly structured and sharded per staff for advanced Agent processing.
- **Bar markers**: every measure ends with a bar check and a `% m.N` comment, so bars are easy to compare.

## Note & Rest Creation
- `add_note(pitch, duration, advance_cursor_after_action, add_to_chord)` - Add notes with MIDI pitch. Sequential notes write a melody; set `add_to_chord=True` to stack a pitch on the current chord.
- `add_tie(pitches)` - Tie notes of the chord at the cursor to the same pitches in the next chord. By default every pitch that is in both chords is tied; pass `pitches` to tie only some (e.g. `[60, 64]` ties C and E of C–E–G into C–E–A). The cursor then moves to the second chord, so calling it again continues a tie chain. Write both chords completely before tying: MuseScore treats tied chords as one, so a pitch added afterwards with `add_to_chord` is also added, tied, to the first chord. Fails without changing the score when no pitch can be tied. `get_score` shows ties as `~` in LilyPond and as `tieForward`/`tieBack` per note in JSON.
- `add_tied_note(duration, pitches, extra_pitches, advance_cursor_after_action)` - Write the next note or chord tied to the chord before the cursor, like `+` in MuseScore's note input. By default every pitch of the chord before is continued; `pitches` ties only some, and `extra_pitches` adds new pitches to the chord without a tie (C–E–G into C–E–A: `pitches=[60, 64], extra_pitches=[69]`). A note longer than the rest of the bar is split at the barline into tied notes.
- `add_rest(duration, advance_cursor_after_action)` - Add rests
- `add_tuplet(duration, ratio, advance_cursor_after_action)` - Add tuplets (triplets, etc.)
- `add_lyrics(lyrics, verse)` - Add lyric syllables to consecutive notes from the cursor

## Measures, Time & Tempo
- `insert_measure()` - Insert measure at current position
- `append_measure(count)` - Add measures to end of score
- `delete_selection(measure)` - Delete current selection or specific measure
- `delete_measures(start_measure, end_measure)` - Remove whole measures on every staff (later measures are renumbered; works with multi-measure rests on, and reports an error if MuseScore deleted fewer measures)
- `set_time_signature(numerator, denominator)` - Change time signature
- `set_tempo(bpm, measure)` - Add a tempo marking at the cursor or at a measure
- `undo()` - Undo last action

## Staves & Instruments
- `add_instrument(instrument_id)` - Add a staff/instrument
- `set_staff_mute(staff, mute)` - Mute or unmute a staff
- `set_instrument_sound(staff, instrument_id)` - Change a staff's sound

## Highlighting & Coloring
- `highlight_notes(start_measure, end_measure, first_staff, last_staff, drums, pitches, start_beat, end_beat, color, opacity)` - Highlighter-pen box around individual hits: as wide as the note, as tall as the whole staff (taller if the note sits above or below it). Pick notes in a chord by drum name (`drums=["crash"]`, `["kick", "snare"]`, `["hi-hat"]`, `["ride"]`, `["tom"]`) or MIDI pitch. Hits close enough to touch share one box
- `highlight_symbols(start_measure, end_measure, first_staff, last_staff, kinds, mode, color, opacity, clear)` - Time signatures, repeat barlines (with their dots) and measure-repeat signs: a pastel light-blue box around each (`mode="highlight"`) or the symbol itself recolored (`mode="color"`)
- `highlight_markings(start_measure, end_measure, first_staff, last_staff, types, color, opacity)` - Translucent box behind each dynamic (f, mf, ff) or other marking (staff text, tempo...)
- `highlight_bars(start_measure, end_measure, first_staff, last_staff, color, opacity, start_beat, end_beat)` - Full-height band over whole bars of a staff, following the bars across line breaks
- `add_label(measure, text, staff, background, border)` - Label in a colored box at a measure, e.g. "Groove x7" or "Fill"
- `set_score_header(title, subtitle, composer, lyricist, part_name, score_path)` - Tidy the title frame, e.g. subtitle "Drum chart" and a short part name ("Drums") instead of a long one that runs into the title
- `set_end_notes(lines, heading, score_path)` - Print notes after the last bar, e.g. how the chart differs from the original, so they end up in the PDF
- `set_song_structure(rows, heading, song, artist, score_path)` - Print the song structure (song and artist, then section, bar count, groove, fills) as a table on its own page at the end
- `add_text(measure, text, staff, beat, size, italic, bold, color, placement, kind)` - Free text with its own look; by default a small, italic, light-grey cue above the staff, e.g. the first words of each section as a reminder for the player
- `color_range(start_measure, end_measure, first_staff, last_staff, color, voices, start_beat, end_beat)` / `clear_color(...)` - Recolor the notes and rests themselves (grace notes such as flams included), or reset them to black
- `clear_highlights(start_measure, end_measure, first_staff, last_staff, kinds)` - Remove highlight boxes and bands, marking boxes and labels (note colors are reset with `clear_color`)
- `remove_annotations(start_measure, end_measure, first_staff, last_staff, kinds, contains, exact)` - Remove added texts, labels, rehearsal marks, tempo markings or voltas, optionally only those containing (or equal to) a given text, e.g. the `**` marks

Everything these tools add can be taken off again, so a chart can be refined step by step; the drum-chart skill lists how to undo each step.

| To mark... | Use |
|---|---|
| Single hits or notes (e.g. crashes) | `highlight_notes` |
| Time signatures, repeat signs | `highlight_symbols` |
| Dynamics and other markings | `highlight_markings` |
| Whole bars | `highlight_bars` |
| A named section | `add_label` or `add_rehearsal_mark` |
| A cue or note to the player | `add_text` |
| The notes' own color | `color_range` |

`start_beat`/`end_beat` limit coloring and highlighting to part of a bar: `start_beat=3, end_beat=4` covers beats 3 and 4, and `3.5` means the "and" of beat 3. A beat follows the time signature's denominator (a quarter in 4/4, an eighth in 6/8). Highlight boxes are sized to the layout at the moment they are drawn; after big layout changes, clear them and highlight again.

## Batch Operations
- `processSequence(sequence)` - Execute multiple plugin commands in one call (camelCase action names, see the tool description)

## Score viewer (MCP Apps)

`show_score` is an [MCP App](https://gofastmcp.com/apps/overview): the tool result is rendered as notation by a small [VexFlow](https://www.vexflow.com/) page (`src/ui/score_viewer.html`) inside hosts that support MCP Apps. Hosts without that support only get a one-line text summary, so use `get_score` there.

- Rendering was verified in a regular browser against the mock plugin. It has not been verified inside Claude or Claude Desktop.
- The page loads VexFlow and the MCP Apps SDK from `unpkg.com`, so the host needs internet access (the server declares that domain in the app's CSP).
- Not drawn: tuplet brackets and ties. Tuplet notes use their written value.
- Long scores: pass `first_measure` and `last_measure` to show a section.

## Version requirements

MuseScore 4.7 is the minimum version; MuseScore 3 is not supported. CI runs the full test suite on MuseScore 4.7.0 and on the latest release.

On MuseScore 4.6, most tools work, but some do not: `clear_highlights` and `remove_annotations` (for voltas) find nothing to remove, and `make_part_score(in_place=True)` needs plugin functions added in 4.7.

| Feature | MuseScore |
|---|---|
| All tools | 4.7+ |
| `add_volta` | Works on 4.7.6; if no volta appears on another version, undo and use the palette: the bars are left selected |

## Examples

These show the tool calls Claude makes; in practice you just describe what you want.

### Creating a Simple Melody

```python
await go_to_beginning_of_score()

# Add notes (MIDI pitch: 60=C, 62=D, 64=E, etc.)
await add_note(60, {"numerator": 1, "denominator": 4}, True)  # Quarter note C
await add_note(64, {"numerator": 1, "denominator": 4}, True)  # Quarter note E
await add_note(67, {"numerator": 1, "denominator": 4}, True)  # Quarter note G
await add_note(72, {"numerator": 1, "denominator": 2}, True)  # Half note C

# Add lyrics to those four notes
await go_to_beginning_of_score()
await add_lyrics(["Do", "Mi", "Sol", "Do"])
```

### Batch Operations

```python
# Use sequence processing for complex operations
sequence = [
    {"action": "goToBeginningOfScore", "params": {}},
    {"action": "addNote", "params": {"pitch": 60, "duration": {"numerator": 1, "denominator": 4}, "advanceCursorAfterAction": True}},
    {"action": "addNote", "params": {"pitch": 64, "duration": {"numerator": 1, "denominator": 4}, "advanceCursorAfterAction": True}},
    {"action": "addRest", "params": {"duration": {"numerator": 1, "denominator": 4}, "advanceCursorAfterAction": True}}
]
await processSequence(sequence)
```

### Marking Up a Score

```python
await highlight_notes(start_measure=1, end_measure=94, drums=["crash"])     # every crash hit
await highlight_symbols(kinds=["repeat_barlines", "time_signatures"])       # pastel light blue
await highlight_markings(types=["Dynamic"])                                 # f, mf, ff
await color_range(start_measure=13, first_staff=19, last_staff=19,
                  start_beat=3, end_beat=4, color="#2ca02c")               # a fill on beats 3-4
await add_label(measure=6, text="Groove x7")
await clear_highlights()                                                    # remove them all again
```

## MIDI Pitch Reference

Common MIDI pitch values for reference:
- **Middle C**: 60
- **C Major Scale**: 60, 62, 64, 65, 67, 69, 71, 72
- **Chromatic**: C=60, C#=61, D=62, D#=63, E=64, F=65, F#=66, G=67, G#=68, A=69, A#=70, B=71
- **Drums (General MIDI)**: kick 36, snare 38, closed hi-hat 42, open hi-hat 46, crash 49/57, ride 51, toms 41-50

## Duration Reference

Duration format: `{"numerator": int, "denominator": int}`
- **Whole note**: `{"numerator": 1, "denominator": 1}`
- **Half note**: `{"numerator": 1, "denominator": 2}`
- **Quarter note**: `{"numerator": 1, "denominator": 4}`
- **Eighth note**: `{"numerator": 1, "denominator": 8}`
- **Dotted quarter**: `{"numerator": 3, "denominator": 8}`
