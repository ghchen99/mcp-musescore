# Repeats and drum charts

[Overview](../README.md) · [Setup](setup.md) · [Tools](tools.md) · [Repeats & drum charts](drum-charts.md) · [Skills](skills.md) · [Development](development.md) · [Troubleshooting](troubleshooting.md)

The [drum-chart skill](skills.md) runs these tools as a whole workflow; the [README](../README.md#example-use-case-a-drum-chart-from-a-songsterr-tab) shows it from a Songsterr tab to a PDF.

## Repeat Structure: Compressing a Score
- `find_repeated_measures(start_measure, end_measure, staves, highlight)` - Find bars that repeat on each staff (measure-repeat candidates) and passages that repeat on all staves (repeat barline and 1st/2nd ending candidates). Each passage comes with the exact tool calls that apply it. Bars that already show a repeat sign count as copies of the bar they repeat. `highlight=True` colors the duplicates
- `set_repeat_barlines(start_measure, end_measure, play_count, clear)` - Start/end repeat barlines with a play count
- `add_volta(start_measure, end_measure, endings, text)` - 1st/2nd ending bracket (experimental)
- `add_rehearsal_mark(measure, text)` - Section label at a measure, e.g. "Verse 1"
- `number_bars_as_played(exclude_from_count, reset)` - Make the displayed bar numbers count repeats, as the music is played: after a bar or passage played 7 times, the numbering jumps ahead accordingly, so the chart's numbers match the original song. `exclude_from_count=[1]` leaves out e.g. a silent first bar. Safe to run again after changing repeats; `reset=True` goes back to plain 1..N numbering
- `set_measure_number(measure, add_to_number, exclude_from_count)` - Set one bar's "Add to measure number" or "Exclude from measure count" by hand

To shorten a score, ask for its repeated passages to be applied: Claude runs `find_repeated_measures`, then each passage's steps (delete the duplicate measures, add repeat barlines and voltas), starting from the last passage so earlier bar numbers stay valid.

## Drum Charts & Measure-Repeat Signs
- `song_structure(staff, tolerance)` - Outline of the song for a structure page: per section (from the rehearsal marks) the bars as played, the count in fours (e.g. "2x4+2"), the grooves (named Groove A, B…) and the fills
- `label_section_counts(counts, staff, placement, color, size, clear)` - Write each section's bar count in its section label, e.g. "Chorus 1 (2x4)", or in bold red beside it (`placement="beside"`)
- `find_groove_sections(staves, start_measure, end_measure, tolerance)` - Road map of a groove part (the drum staves by default): for each section the groove bar, its exact copies, near copies with the hits that differ (e.g. "kick on beat 2.5"), fills, and a collapse plan (`runs`). The plan uses 1-, 2- or 4-bar phrases repeated back to back, so a groove whose open hi-hat or extra kick comes every second bar becomes a 2-bar phrase ×N; copies may only differ in the cymbal on beat 1 (marked `*` first time only / `**` every other bar or every n bars) and ghost notes, and the plan leaves the fewest bars possible while following the song's phrasing (a 2- or 4-bar phrase starts on a section start, after a fill or on a crash bar, so an intro reads 4 + 2 bars rather than 1 + 2×2 + 1). Near copies are listed for you to approve, because merging them deletes their differences
- `apply_measure_repeats(staff, groups, score_path)` - Turn bars of one staff into 1-, 2- or 4-bar measure-repeat signs, e.g. `groups=[{"start": 7, "end": 12, "bars": 1}]`. Bars with ties or slurs crossing their barlines are skipped and reported
- `restore_backup(backup, score_path)` - Bring back the version before an `apply_measure_repeats`, `set_score_header`, `set_end_notes`, `set_song_structure` or `simplify_roll` edit
- `make_part_score(staves, output_path, score_path)` - Save a copy of the score with only some parts (e.g. the drum kit). The other parts are removed in the file, so a damaged bar in another instrument (common in Guitar Pro imports) doesn't stop the copy from opening; tempo marks, rehearsal marks and other system texts move onto the kept staff. The original is saved and closed, unchanged, and the copy opens in its place, because the plugin can only work in its own window. If MuseScore can't open the copy, the original is reopened. With `in_place=True` it instead removes the other instruments from the open score itself (MuseScore 4.7+) without saving anything first, after backing up the full score as a MusicXML export (plus a copy of its `.mscz` when the file is known), and reports bars that would make MuseScore call the file corrupted: no other file is opened and the damaged full score is never written again, so this is what the drum-chart skill uses
- `collapse_to_repeat(start, end, phrase_bars, force)` - Keep one groove bar (or a `phrase_bars`-bar phrase) between repeat barlines with a play count (shown as "7x") and delete the bars it replaces. It changes every staff, so use it in a part-only score; it refuses when the copies differ in more than the cymbal on beat 1 and ghost notes unless `force=True`
- `simplify_roll(staff, start_measure, end_measure, end_beat, drums, pitches, slashes, start_beat)` - Rewrite a cymbal roll (repeated or tied crash/ride notes) as one long note per bar, tied, with a tremolo. It can start on any beat (earlier hits in that bar stay as written; a crash tied into the roll moves the start back to that crash), and lengths that no single note value can hold become tied notes; a kick on the roll's first note moves to its own voice. Edits the file and reloads the score
- `prepare_measure_repeat(start_measure, end_measure, bars, first_staff, last_staff)` - Manual alternative: select the bars and click the measure-repeat sign in the palette yourself

### How measure-repeat signs are applied

MuseScore's plugin API cannot place measure-repeat signs, so `apply_measure_repeats` edits the score file the way MuseScore itself stores them:

1. The plugin saves the score.
2. The server finds the file and backs it up to `~/.mcp-musescore/backups` (or `MCP_MUSESCORE_BACKUP_DIR`). The plugin API doesn't expose a score's path, so the plugin stores a score ID in the score's metadata (`mcpScoreId`, visible in File → Project properties), and the server only edits a file that carries that ID and has the open score's number of staves and bars. It never guesses: if no such file is found, nothing is changed.
3. The server writes the signs into the file, and the plugin closes and reopens the score in the same tab.

You see the result right away, but MuseScore's undo history starts over: use `restore_backup` instead of Ctrl+Z. The written signs were checked by having MuseScore 4.7.6 load and re-save edited files.

### Groove bar × N charts

For a chart where each groove is written once with a count: `make_part_score` to get a drums-only copy, `find_groove_sections` for the sections, then `collapse_to_repeat` on each section from the last one backwards, `number_bars_as_played` so the bar numbers still match the song, and finally `set_score_header`, `set_end_notes` and `set_song_structure` (with the outline from `song_structure`) for a tidy title, a printed summary of what changed and a structure page.

`set_score_header` and `set_end_notes` also edit the file, because frames (the boxes above and after the music) are out of the plugin API's reach, so they reload the score the same way.

## Drum Notation
- `add_articulation(start_measure, end_measure, symbol, drums, pitches, ...)` - Add a half-open, open or closed hi-hat symbol (or an accent, marcato, staccato, tenuto) to the chords containing the chosen drums, e.g. `drums=["hi-hat"], symbol="half_open"`
- `remove_articulations(start_measure, end_measure, symbols, drums, pitches, ...)` - Take those symbols off again
- `beam_over_rests(start_measure, end_measure, first_staff, last_staff, clear)` - Beam eighths across rests inside a beat group (one beamed group per dotted quarter in 12/8) instead of separate flags
- `ghost_notes(start_measure, end_measure, mode, drums, pitches, ...)` - List ghost notes per bar, or remove them (`mode="remove"`); a chord of only ghost notes becomes a rest

## Examples

These show the tool calls Claude makes; in practice you just describe what you want.

### Turning a Drum Part into a Chart

```python
# Road map of the drum staff: groove bars, exact/near copies, fills
sections = await find_groove_sections()

# Replace the exact copies with 1-bar repeat signs (saves, backs up and reloads the score)
await apply_measure_repeats(staff=19, groups=[{"start": 7, "end": 12, "bars": 1}])

# Or: a drums-only copy where each groove is written once with a count
await make_part_score(staves=[19])
await collapse_to_repeat(start=6, end=12)   # bar 6 played 7 times, bars 7-12 removed
await number_bars_as_played(exclude_from_count=[1])   # bar numbers count the repeats again

# Mark the crash pattern the collapsed bar no longer shows, with a legend under the tempo
await add_text(measure=6, text="**", size=10, italic=False, color="#000000")
await add_text(measure=1, text="** crash every other bar", color="#000000")

# Finish the page: a tidy title and a printed summary of the changes
await set_score_header(title="Hold The Line", subtitle="Drum chart", composer="Toto", part_name="Drums")
await set_end_notes(lines=["95 bars -> 31; bar numbers count as played",
                           "Collapsed: verses x9, choruses x7",
                           "Dropped: open-hat endings in the verses"])
```

### Iterating on a Chart

```python
await remove_annotations(contains="**", exact=True)       # take off the ** marks
await clear_highlights(kinds=["highlights"])               # crash and symbol boxes
await clear_color(start_measure=13, first_staff=0, last_staff=0)
await number_bars_as_played(reset=True)                    # plain 1..N bar numbers
await set_end_notes(lines=[], heading="")                  # remove the printed summary
await restore_backup()                                     # undo the last file edit (header, notes, repeat signs)
```
