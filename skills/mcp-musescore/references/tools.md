# Public MCP tool reference

This reference describes the tools currently registered by `server.py` and the JSON actions sent to the MuseScore QML plugin. Use the Python function names when calling MCP. Use the camelCase action names only inside `processSequence`.

The server currently registers 73 public tools.

Bars are named as printed in the score, the way the user names them: pass the number the user says, as an int or a string. A pickup bar is bar 0. A number printed on two bars (a split bar, or a section that counts from 1 again) is `"12a"` and `"12b"`; a bare `12` is then refused with a question to ask the user. A bar that isn't printed (e.g. 10 after `number_bars_as_played` jumps from 8 to 17) is refused with the score's numbering. Replies, errors and suggested tool calls use printed bars too. The `int` measure parameters below take such a bar.

## Connection and score inspection

| MCP tool | Parameters | What it does |
|---|---|---|
| `connect_to_musescore` | none | Opens the WebSocket client connection to `ws://localhost:8765`. Returns `{success: bool}`. |
| `ping_musescore` | none | Sends the `ping` action. A healthy plugin returns `pong`. |
| `get_score` | `start_measure` (default: the first bar), `end_measure: int \| None = None`, `staves: list[int] \| None = None`, `format: "lilypond" \| "json" = "lilypond"` | Reads a window of the score (16 bars by default) as LilyPond with a `% bar N` comment (the bar as printed) at every barline, or as the raw JSON analysis. The header lists the score's bars, e.g. `Bars: 0-64`; page through long scores with `start_measure`, and read only some staves of large scores with `staves`. |
| `render` | `page: int \| None = None`, `measures: str \| None = None` (e.g. `"49-62"`, as printed) | The score as MuseScore engraves it, as a PNG image: what `get_score` cannot show, such as overlapping chord symbols, marker placement, breaks and spacing. `page` gives a whole page; `measures` crops those bars from their page at higher detail, with everything attached to them, as they stand on their systems (the other bars of those systems are left blank). Bars inside a multi-measure rest are refused. Render again after a change to check it. |

`get_score` lists each measure's markers (Segno, Coda, Fine), jumps (D.S. al Coda) and line, page and section breaks under `[Markings]`, with the dynamics and other markings.

Call `ping_musescore` before a mutation. Call `get_score` before and after a complex edit.

## Navigation and selection

| MCP tool | Parameters | What it does |
|---|---|---|
| `get_cursor_info` | none | Reads the current cursor/selection state and the related score context. |
| `go_to_measure` | `measure: int` | Moves the cursor to the start of a bar, as printed. |
| `go_to_final_measure` | none | Moves to the final measure. |
| `go_to_beginning_of_score` | none | Resets the plugin cursor/selection to the beginning of the score. |
| `next_element` | none | Moves the cursor to the next score element. |
| `prev_element` | none | Moves the cursor to the previous score element. |
| `next_staff` | none | Moves the cursor to the next staff. |
| `prev_staff` | none | Moves the cursor to the previous staff. |
| `select_current_measure` | none | Selects the current measure. |
| `select_custom_range` | `start_tick: int`, `end_tick: int`, `start_staff: int`, `end_staff: int` | Selects a precise tick range across one or more zero-based staves. MuseScore uses 480 ticks per quarter note in this project. |

Navigation tools return the selection as LilyPond with measure/beat/staff metadata. On a plugin error they return the raw response envelope instead; read it rather than assuming a move succeeded.

## Notes, rests, lyrics, and measures

Duration values are JSON objects such as `{"numerator": 1, "denominator": 4}` for a quarter note. MIDI pitch 60 is middle C (C4); valid MIDI pitch values are 0–127.

| MCP tool | Parameters | What it does |
|---|---|---|
| `add_note` | `pitch: int = 64`, `duration: dict = {numerator: 1, denominator: 4}`, `advance_cursor_after_action: bool = true` | Adds a note at the current cursor position. |
| `add_tie` | `pitches: list[int] \| None = None` | Ties notes of the chord at the cursor to the same pitches in the next chord (default: every pitch in both chords) and moves the cursor to the second chord. After `add_note` the cursor is on the next position, so move back first. Write both chords completely before tying: a pitch added later with `add_to_chord` is also added, tied, to the first chord. Fails without changing the score when no pitch can be tied. |
| `add_tied_note` | `duration: dict`, `pitches: list[int] \| None = None`, `extra_pitches: list[int] \| None = None`, `advance_cursor_after_action: bool = true` | Writes the next note or chord tied to the chord before the cursor, like `+` in note input. Default: every pitch of the chord before; `extra_pitches` are added untied (C-E-G into C-E-A: `pitches=[60, 64], extra_pitches=[69]`). Notes longer than the rest of the bar are split into tied notes. Fails without changing the score when there is no note before the cursor or a pitch is not in it. |
| `add_rest` | `duration: dict = {numerator: 1, denominator: 4}`, `advance_cursor_after_action: bool = true` | Adds a rest at the current cursor position. |
| `add_tuplet` | `duration: dict = {numerator: 1, denominator: 4}`, `ratio: dict = {numerator: 3, denominator: 2}`, `advance_cursor_after_action: bool = true` | Adds a tuplet; the default ratio represents a triplet. |
| `add_lyrics` | `lyrics: list[str]`, `verse: int = 0` | Adds syllables to consecutive notes from the current cursor, one entry per note (rests skipped). `"Hel-"` hyphenates to the next syllable; `"_"` holds the previous syllable over that note with an extender line (no lyric is placed there). Verse is zero-based. |
| `insert_measure` | none | Inserts a measure at the current position. |
| `append_measure` | `count: int = 1` | Appends one or more measures to the end of the score. |
| `delete_selection` | `measure: int | null = null` | Deletes the current selection, or a specified measure when provided. Treat as destructive and verify immediately. |
| `delete_measures` | `start_measure: int`, `end_measure: int \| None = None` | Removes whole measures on every staff (MuseScore's Remove selected range), with multi-measure rests switched off meanwhile; errors if MuseScore deleted fewer measures than asked. Later measures are renumbered, so remove ranges from the last one backwards. |
| `undo` | none | Undoes the last MuseScore operation. |

## Staff, instruments, time, and style

| MCP tool | Parameters | What it does |
|---|---|---|
| `add_instrument` | `instrument_id: str` | Adds a staff/instrument using the MuseScore instrument identifier. |
| `set_staff_mute` | `staff: int`, `mute: bool` | Mutes or unmutes a zero-based staff. |
| `set_instrument_sound` | `staff: int`, `instrument_id: str` | Changes the sound/instrument identifier for a zero-based staff. |
| `set_time_signature` | `numerator: int = 4`, `denominator: int = 4` | Sets the time signature at the current score context. |
| `set_tempo` | `bpm: float`, `measure: int \| None = None` | Adds a tempo marking (quarter-note BPM) at the cursor, or at the start of `measure`. |
| `get_style` | `keys: list[str]` | Reads score style settings (Format → Style) by MuseScore's internal key, e.g. `createMultiMeasureRests`. Returns `styles`, and lists under `unknown` the keys MuseScore does not have. |
| `set_style` | `styles: dict` | Changes style settings, given as `{key: value}`. An unknown key is refused, and the settings before it stay applied. Returns each value as MuseScore reads it back. |

## Repeat structure and coloring

Bar ranges are as printed and inclusive. Staff ranges in these tools are 0-based and inclusive (`first_staff`, `last_staff`).

| MCP tool | Parameters | What it does |
|---|---|---|
| `find_repeated_measures` | `start_measure: int = 1`, `end_measure: int \| None = None`, `staves: list[int] \| None = None`, `highlight: bool = false` | Reads the score in 16-measure chunks and returns `passages` (whole-score repeats and repeats with 1st/2nd endings, each with `duplicate_measures`, `saves_measures` and the `apply` tool calls) and `measure_repeats` (per-staff 1/2/4-bar repeats, grouped by staves). `highlight` colors duplicates in the score and returns a legend. |
| `set_repeat_barlines` | `start_measure: int`, `end_measure: int`, `play_count: int = 2`, `clear: bool = false` | Sets start/end repeat barlines. Needs MuseScore 4.6+; on older versions it selects the bars and returns `fallback: "manual"` with palette instructions. |
| `add_volta` | `start_measure: int`, `end_measure: int \| None = None`, `endings: list[int] = [1]`, `text: str \| None = None` | Experimental volta (ending bracket). Check the score afterwards; if it fails or nothing appears, the bars are selected for the palette. |
| `prepare_measure_repeat` | `start_measure: int`, `end_measure: int \| None = None`, `bars: 1 \| 2 \| 4 = 1`, `first_staff: int = 0`, `last_staff: int \| None = None` | Selects the bars to replace with a measure-repeat sign and returns the palette step. The plugin API cannot place these signs itself. |
| `color_range` | `start_measure: int`, `end_measure: int \| None = None`, `first_staff: int = 0`, `last_staff: int \| None = None`, `color: str = "#d62728"`, `voices: list[int] \| None = None`, `start_beat: float \| None = None`, `end_beat: float \| None = None` | Colors notes and rests (stems, beams, accidentals, dots, ties) in a range. `start_beat` (in `start_measure`, fractions allowed, 3.5 = "and" of 3) and `end_beat` (in `end_measure`, inclusive) color only part of a bar; a beat is the time signature's denominator. Only notes/rests that start inside the span are colored. |
| `clear_color` | `start_measure: int`, `end_measure: int \| None = None`, `first_staff: int = 0`, `last_staff: int \| None = None`, `start_beat`, `end_beat` | Resets a range (optionally part of a bar) to black. |
| `highlight_bars` | `start_measure: int`, `end_measure: int \| None = None`, `first_staff: int = 0`, `last_staff: int \| None = None` (defaults to `first_staff`), `color: str = "#ffe600"`, `opacity: float = 0.35`, `start_beat`, `end_beat` | Highlighter band behind the bars of each staff: a thick, semi-transparent text line drawn behind the notes. Experimental; check the score. |
| `highlight_notes` | `start_measure: int`, `end_measure: int \| None = None`, `first_staff: int = 0`, `last_staff: int \| None = None` (defaults to `first_staff`), `drums: list[str] \| None` (e.g. `["crash"]`, `["kick", "snare"]`, `["hi-hat"]`, `["ride"]`, `["tom"]`), `pitches: list[int] \| None`, `start_beat`, `end_beat`, `color: str = "#ffd600"`, `opacity: float = 0.45` | Full-staff-height translucent box around each matching hit (as wide as the note, taller if the note is above/below the staff); hits whose boxes would touch share one box. Use `drums`/`pitches` to pick one note of a chord, e.g. the crash. Boxes are sized to the current layout; after big layout changes, clear and re-run. |
| `highlight_symbols` | `start_measure: int = 1`, `end_measure: int \| None = None` (end of score), `first_staff: int = 0`, `last_staff: int \| None = None`, `kinds: ["time_signatures", "repeat_barlines", "measure_repeats"]`, `mode: "highlight" \| "color" = "highlight"`, `color: str = "#a7d8f0"` (pastel light blue), `opacity: float = 0.6`, `clear: bool = false` | Highlight mode: full-staff-height box around each symbol (repeat barlines include their dots). Color mode: recolors the symbol; `clear=True` resets it to black. |
| `highlight_markings` | `start_measure: int = 1`, `end_measure: int \| None = None` (end of score), `first_staff: int = 0`, `last_staff: int \| None = None`, `types: ["Dynamic"]` (also `StaffText`, `SystemText`, `Tempo`, `Expression`), `color`, `opacity: float = 0.55` | Translucent box behind each marking, set on the marking itself (not a style change). `get_score` lists markings under `[Markings]` (JSON: `measures[].markings`). |
| `add_text` | `measure: int`, `text: str`, `staff: int = 0`, `beat: float \| None`, `size: float = 8`, `italic: bool = true`, `bold: bool = false`, `color: str = "#9e9e9e"`, `placement: "above" \| "below" = "above"`, `kind: "staff" \| "expression" = "staff"` | Free text with its own size, style and color. The defaults make a small italic light-grey cue (e.g. a section's first words, supplied by the user). |
| `remove_annotations` | `start_measure: int = 1`, `end_measure: int \| None = None` (end of score), `first_staff: int = 0`, `last_staff: int \| None = None`, `kinds: ["texts"]` (also `labels`, `rehearsal_marks`, `tempo`, `voltas`, `markers`, `jumps`, `chord_symbols`, `breaks`), `contains: str \| None`, `exact: bool = false` | Removes texts and marks: `texts` = unboxed staff/expression text (`add_text`), `labels` = boxed staff text (`add_label`). `markers` = Segno, Coda, To Coda, Fine and `jumps` = D.C./D.S. jumps, on every staff (they belong to the bar); `chord_symbols` with `contains` and `exact` removes one chord by name; `breaks` removes system, page and section breaks. `contains` filters by text; `exact` requires the whole text to match (e.g. `"*"` but not `"**"`). |
| `add_label` | `measure: int`, `text: str`, `staff: int = 0`, `background: str = "#fff2a8"`, `border: str = "#000000"` | Boxed staff text with a colored background at the start of a measure. |
| `clear_highlights` | `start_measure: int = 1`, `end_measure: int \| None = None` (end of score), `first_staff: int = 0`, `last_staff: int \| None = None`, `kinds: ["highlights", "notes", "markings", "labels"]` | `highlights` removes boxes from `highlight_bars`/`highlight_notes`/`highlight_symbols`; `markings` the boxes behind dynamics; `labels` boxed labels; `notes` small notehead boxes from older versions. |

Which highlight to use: one note or one drum (crash hits) → `highlight_notes`; time signatures, repeat signs, measure repeats → `highlight_symbols`; dynamics or other markings → `highlight_markings`; a whole passage on a staff → `highlight_bars`; recolor the notation itself → `color_range` / `highlight_symbols(mode="color")`. All highlight boxes span the full staff height. Never change score style to highlight individual markings.

Coloring notes (`color_range`) changes the notation itself, and includes each chord's grace notes (flams); highlights and labels are separate score elements, so `clear_highlights` removes them without touching note colors.

To compress a score: call `find_repeated_measures`, then run each passage's `apply` steps, starting from the last passage. Re-run the analysis after deleting measures, because measure numbers change.

## Drum charts and measure-repeat signs

| MCP tool | Parameters | What it does |
|---|---|---|
| `label_section_counts` | `counts: list[{measure, text}] \| None` (default: from `song_structure`), `staff`, `placement: "label" \| "beside" = "label"`, `color: str = "#d62728"`, `size: float = 12`, `label_size: float \| None = 12`, `label_clearance: float \| None = 1`, `clear: bool = False` | Each section's bar count (e.g. "2x4+2"; brackets in the given text are dropped): in parentheses in its rehearsal mark ("Chorus 1 (2x4)"), with the labels set to `label_size` pt and `label_clearance` spaces of minimum distance; or with `placement="beside"` as bold text right of the mark at its height, placed from the layout (autoplace off, so MuseScore doesn't keep the system above clear of it; moves right past texts such as the tempo, or up over notes/symbols). Re-running replaces the counts in either form; with computed counts or the label placement, count texts left beside labels anywhere in the score are removed too. |
| `song_structure` | `staff: int \| None` (first drum staff), `tolerance: float = 0.8` | Sections from the rehearsal marks with `bars_played` (repeats counted, bars excluded from the bar count left out), `count` (in fours, e.g. "2x4+2": the count written in the label when it still adds up (`count_source: "label"`, `computed_count` if different; `label_count_outdated` when it doesn't), else computed: a lead-in of 2+ bars before the first groove bar counted on its own ("2+4+2"), runs in another time signature too ("4+2+2")), `lead_in_bars`, `bars_on_page`, `grooves` (Groove A, B…: bars played at least twice in a row; hi-hat openings, crashes and ghost notes don't make a new groove), `fills` (bar, drums) and `rest_bars`; a `grooves` legend, `total_bars_played`, and `suggested_rows` for `set_song_structure`. |
| `find_groove_sections` | `staves: list[int] \| None = None`, `start_measure: int = 1`, `end_measure: int \| None = None`, `tolerance: float = 0.85` | Per staff (drum staves by default): a `road_map`, `sections` (groove bar, `exact` copies, `near` copies with `extra`/`missing` hits, `fills`, `proposed_repeat_signs`, and `runs`: the collapse plan for the whole staff that leaves the fewest bars, with 2- and 4-bar phrases starting on the phrase grid (section starts, bars after a fill, crash bars). A run is a 1-, 2- or 4-bar phrase repeated back to back whose copies differ only in the cymbal on beat 1 (crash or closed hi-hat) and ghost notes; it has `start`, `end`, `phrase_bars`, `play_count`, `keep`, `crash_on_1` (`first_only` / `every_n` (`every`, `from_bar`) / `every_bar` / `irregular` with `description` / `none`, plus a suggested `mark` `*`/`**` and `legend`) and `dropped` (hits collapsing removes)), and `apply_exact_copies` ready for `apply_measure_repeats`. Bars that already hold repeat signs count as copies. |
| `apply_measure_repeats` | `staff: int`, `groups: list[{start, end?, bars: 1\|2\|4}]`, `score_path: str \| None = None` | Writes measure-repeat signs into the score file and reloads the score. Returns `applied`, `unchanged`, `skipped` (with reasons, e.g. a tie crossing the barline), `dropped` content, `backup`, `reopened`. |
| `set_score_header` | `title`, `subtitle`, `composer`, `lyricist`, `part_name` (each `str \| None`; `None` keeps, `""` removes), `score_path: str \| None` | Edits the title frame texts in the file and reloads the score. `part_name` is the part score's top-left name (a long one overlaps the title). |
| `set_end_notes` | `lines: list[str]`, `heading: str = "Changes from the original"`, `append: bool = False`, `score_path: str \| None` | Text frame after the last bar with a bold heading and one line per item (e.g. how a chart differs from the original). Replaces earlier end notes (a structure page stays after them; `previous` in the report lists their lines); `append=True` keeps their lines and adds the new ones; no heading and no lines removes them. File edit + reload. |
| `set_song_structure` | `rows: list[dict]` (`section`, `bars`, `count`, `groove`, `fill`), `heading: str = "Song structure"`, `song`/`artist: str \| None` (default: title of the title frame, and its composer or else its subtitle), `score_path` | Song structure table on a new page at the end (after the end notes): heading, song and artist, then the table in a monospaced font with wrapped columns, half a line between rows, and a total. The Bars column shows `count` (or `bars` in fours); the total adds up `bars` (or the count labels). Replaces an earlier one; no rows removes it. File edit + reload. |
| `restore_backup` | `backup: str \| None = None`, `score_path: str \| None = None` | Restores the newest (or given) backup of the open score and reloads it; the current version is backed up first. |
| `collapse_to_repeat` | `start: int`, `end: int`, `phrase_bars: int = 1`, `force: bool = false` | Keeps the first `phrase_bars` bars of `start..end` between repeat barlines with play count `(end - start + 1) / phrase_bars`, deletes the rest. Affects every staff; refuses when copies differ in more than the cymbal on beat 1 and ghost notes unless `force`. Reports `differences_dropped` and `ghost_or_crash_differences_dropped`. Use in a part-only score. |
| `simplify_roll` | `staff: int`, `start_measure: int`, `end_measure: int`, `end_beat: float \| None`, `drums: list[str] = ["crash"]`, `pitches: list[int] \| None`, `slashes: int = 3`, `start_beat: float = 1`, `score_path` | Rewrites a cymbal roll (repeated/tied notes from `start_beat` of `start_measure` to `end_beat` of `end_measure`; beats in the time signature's unit, e.g. eighths in 12/8; earlier hits in the first bar stay) as one long note per bar, tied, with a tremolo (lengths no single value can hold become tied notes); other notes of the first chord (e.g. a kick) move to voice 2. If the cymbals at the start are tied from earlier hits, the start moves back to the first of them (`start_moved_back`), so the roll is continuous. Refuses if other notes or rests are inside. File edit + reload. |
| `add_articulation` | `start_measure`, `end_measure`, `symbol` (`half_open`, `open`, `closed`, `accent`, `marcato`, `staccato`, `tenuto`), `drums`/`pitches`, staves, `start_beat`/`end_beat` | Adds the symbol to every chord in the range containing the drums (e.g. half-open hi-hats). Idempotent. |
| `remove_articulations` | range, `symbols = ["half_open", "open", "closed"]`, `drums`/`pitches` | Removes those articulations. |
| `beam_over_rests` | range, `clear: bool = False` | Beams eighths and shorter across rests inside a beat group (dotted quarter in 6/8, 9/8, 12/8; a beat otherwise) when beamable notes come before and after the rest; `clear` puts rests back on automatic beaming. |
| `ghost_notes` | range, `mode: "list" \| "remove"`, `drums`/`pitches` | Lists ghost notes per bar, or removes them (a chord of only ghost notes becomes a rest). Ask the user before removing. |
| `make_part_score` | `staves: list[int]`, `output_path: str \| None = None`, `score_path: str \| None = None`, `in_place: bool = False` | Saves the open score and writes a copy of its file with only the parts that own `staves` (and a new score ID); system texts (tempo, rehearsal marks, system text, voltas) and bar settings stored on the old first staff move onto the first kept staff. Closes the original and opens the copy in its place, then checks the plugin is attached to it. If MuseScore can't open the copy, the original is reopened and the tool raises an error. Damaged bars in removed parts don't matter. Returns `kept_parts`, `staves_now`, `system_texts_moved`. `in_place=True`: saves nothing; backs up the full score (plugin `exportScore` to `~/.mcp-musescore/backups/<name>.<stamp>.full-score.mxl`, plus a copy of the `.mscz` when it can be identified by its score ID), removes the other parts from the open score with the plugin's `removeParts` (MuseScore 4.7+; it keeps tempo, rehearsal marks, repeats and the title) and checks the remaining bars add up; returns `full_score_backups`, `incomplete_bars`, `warnings`. Staff indices restart from 0 in the new score. |
| `add_rehearsal_mark` | `measure: int`, `text: str` | Rehearsal mark at a measure start (experimental). |
| `set_chord_symbol` | `measure`, `chord: str`, `beat: float = 1`, `staff: int = 0` | Adds a chord symbol on the beat, or changes the one there (`replaced` gives the old name). MuseScore parses the name as typed. On a beat no note or rest starts on, one already there can be changed but a new one can't be added (refused, with the beats that have one; the user can add it by hand). |
| `move_chord_symbol` | `measure`, `to_measure`, `beat: float = 1`, `to_beat: float = 1`, `staff: int = 0` | Moves a chord symbol, keeping its name (deleted and added again: hand-set position and font are lost). Refused for an imported chord symbol whose name isn't readable (ask the user, then `set_chord_symbol`), and for a target beat that already has one. |
| `add_break` | `measure`, `kind: "line" \| "page" \| "section" = "line"` | Ends a system, page or section after the bar. Returns `added` (`System break`, `Page break`, `Section break`). A break of that kind the bar already has is refused. |
| `set_measures_per_system` | `per_system: int`, `start_measure = None` (first bar), `end_measure = None` (last bar), `method: "locks" \| "breaks" = "locks"` | N bars on every system. `locks` = system locks as Format → Measures per system makes them; `breaks` = a system break after every N bars. Removes the range's system breaks and locks first; `per_system=0` only removes them. Returns `removed_breaks` and `systems` (`firstMeasure`/`lastMeasure` of each system as laid out afterwards). |
| `find_elements` | `kinds: list["chord_symbols" \| "markers" \| "jumps" \| "texts" \| "labels" \| "rehearsal_marks" \| "tempo"] \| None` (all), `start_measure`, `end_measure` (end of score), `first_staff`, `last_staff`, `beat: float \| None`, `contains: str \| None`, `exact: bool = false` | Read-only. Lists the elements with `measure`, `beat` (none for markers and jumps), `staff`, `kind`, `text`, `placement`, `align`, `fontSize`, `offset` (`[x, y]` staff spaces, y down). Check here what `set_properties` will change. |
| `set_properties` | the `find_elements` selection, plus `placement: "above" \| "below"`, `align: "left" \| "center" \| "right"`, `font_size: float`, `offset: [x, y]`, `move_by: [dx, dy]`, `reset: list[...]` | Changes every matching element; `offset` replaces, `move_by` adds, `reset` restores the style's value. A placement change also takes the style's offset for that side, before `move_by`. Refused when nothing matches or nothing is given to change. Returns the elements afterwards. |
| `set_measure_stretch` | `stretch: float` (1 = MuseScore's width), `start_measure`, `end_measure = None` (= start) | Bar stretch as Format → Stretch. Returns `measures` with the stretch read back. |
| `add_marker` | `measure`, `marker: "segno" \| "coda" \| "to_coda" \| "fine" \| "dc" \| "dc_al_fine" \| "dc_al_coda" \| "ds" \| "ds_al_fine" \| "ds_al_coda"` | Repeat marker or jump, as from the Repeats & jumps palette. Segno and Coda go on the bar they start; To Coda, Fine and the jumps on the bar they end. Returns `added` (MuseScore's name, e.g. `Da Capo al Fine` for `dc_al_fine`); a jump also returns `missing`, the markers it needs that the score lacks, with a `warning`: add them or ask the user where they go. A marker the bar already has is refused. Remove with `remove_annotations(kinds=["markers"])` or `["jumps"]`. |
| `number_bars_as_played` | `exclude_from_count: list[int] \| None = None`, `reset: bool = false` (plain 1..N numbering) | Sets every bar's "Add to measure number" so displayed numbers count repeats as played (after a passage between repeat barlines played N times, the next bar jumps by (N-1) x its length). Recomputes all bars, so it is safe to re-run. Voltas are not taken into account. MuseScore 4.6+. |
| `set_measure_number` | `measure: int`, `add_to_number: int \| None`, `exclude_from_count: bool \| None` | One bar's "Add to measure number" / "Exclude from measure count". |

Printed bar numbers: `number_bars_as_played` and `set_measure_number` change the numbers printed in the score, and so the names the tools take afterwards. `get_score` shows repeat barlines as `|:` and `:|xN`.

File edits (`apply_measure_repeats`, `restore_backup`, `set_score_header`, `set_end_notes`, `set_song_structure`, `simplify_roll`) save the open score and only touch a file that carries its score ID (`mcpScoreId` meta tag) and has its number of staves and bars; otherwise they refuse and change nothing. Leave `score_path` out unless the user gives it. MuseScore 4 opens other scores in a new window out of the plugin's reach, so tools that switch scores close the current one first.

Workflow for a chart: `find_groove_sections` → show the road map and near copies to the user → `apply_measure_repeats` with the approved groups (one call per staff). For "groove bar x N": `make_part_score` → `collapse_to_repeat` per section, from the last section backwards.

`apply_measure_repeats` reloads the score, which resets MuseScore's undo history; undo with `restore_backup`, not Ctrl+Z.

File edits find the open score's file by its score ID. If the open tab is a part of a score (the ID was saved into `Excerpts/…`), the part is first written as its own file, `<score> - <part>.mscz` (the full score's file is backed up, not changed), and opened in place of the full score; the edit then goes to that file.

## Batch execution

| MCP tool | Parameters | What it does |
|---|---|---|
| `processSequence` | `sequence: list[object]` | Sends a list of camelCase actions to the plugin in order. Use only when the complete sequence is known and safe. A failing step stops the sequence and is reported as an error naming the step; the steps before it stay applied. |

The currently accepted inner actions are:

```text
getScore, addNote, addTie, addTiedNote, addRest, addTuplet, appendMeasure, deleteSelection,
getCursorInfo, goToMeasure, nextElement, prevElement, nextStaff, prevStaff,
selectCurrentMeasure, processSequence, insertMeasure, goToFinalMeasure,
goToBeginningOfScore, setTimeSignature, addLyrics, addInstrument,
setStaffMute, setInstrumentSound, setTempo, selectMeasures, deleteMeasures,
setRepeatBarlines, addVolta, colorRange, setStyle, addRehearsalMark, removeParts,
addHighlight, addLabel, clearHighlights, highlightNotes, highlightMarkings, highlightSymbols,
setMeasureNumbering, numberAsPlayed, addText, removeAnnotations, addArticulation,
removeArticulations, ghostNotes
```

The range actions take `measure` and `startMeasure`/`endMeasure` as printed in the score before the sequence (inclusive) and `startStaff`/`endStaff` (0-based, `endStaff` exclusive).

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

`syncStateToSelection` is an internal QML action, not a public MCP tool.

## Names not currently exposed

The upstream README mentions `add_lyrics_to_current_note` and `set_title`, but the current `src/tools/` registration does not expose those tools. Do not call them as if they existed. They require a future repository change before they can be used through MCP.
