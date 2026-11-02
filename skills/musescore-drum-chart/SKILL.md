---
name: musescore-drum-chart
description: Turn a full score open in MuseScore into a compact, colour-coded drum chart through the MuseScore plugin tools (sections, grooves and 2/4-bar phrases collapsed with play counts, fills/stops kept and coloured, hi-hat openings and kicks preserved, half-open hi-hat symbols, ghost notes on request, cymbal rolls simplified, crashes/dynamics/time signatures highlighted, bar numbers counted as played), or finish a chart started earlier. Use this whenever the user asks for a drum chart, drum part, drummer's chart or road map from a MuseScore score, wants to compress/condense/simplify a drum part, or mentions repeated bars, grooves, fills or play counts in MuseScore, even if they don't say "chart".
---

# MuseScore drum chart

Goal: a short drum chart that reads like a road map. Each groove or phrase is written once with a play count, fills and stops are written out and colour-coded, nothing the drummer plays differently is lost, and bar numbers still match the song as played.

## The user's rules

These come from the user's feedback on earlier charts. Follow them unless the user says otherwise for a chart.

- **Never drop what the drummer plays differently.** Bars may only be collapsed together when they are the same in kicks, snares, toms, hi-hat openings (open / half-open) and articulations. The only differences allowed are:
  - the cymbal on beat 1 (crash instead of closed hi-hat), shown with `*` / `**` marks;
  - ghost notes, if the user agrees to drop them (see below).
- **Use phrases, not just bars.** When a groove alternates (e.g. an open hi-hat on the last eighth of every second bar, or an extra kick every other bar), collapse a 2-bar (or 4-bar) phrase × N instead of one bar × N. `find_groove_sections` computes these runs.
- **Follow the song's phrasing.** A repeated 2- or 4-bar phrase starts where a phrase starts: a crash bar, a section start, or the bar after a fill. "4 + 2 bars" reads better than "1 + 2-bar phrase ×2 + 1", even if it costs a bar or two on the page. `find_groove_sections` only proposes runs on that grid; don't build off-grid runs by hand.
- **Compact as much as these rules allow**, then offer near copies (bars that differ by a kick or similar) as a choice: merge them only if the user approves, and say what would be lost. An approved merge is `collapse_to_repeat(..., force=True)`; list the dropped hits in the end notes.
- **Keep fills, stops and builds written out.** Bars in another meter (e.g. a 3/4 bar in a 4/4 song) are written out too, unless the same bar repeats: identical odd-meter bars collapse like any others ("pedal hi-hat bar ×2").
- **End the chart on the last hit.** Empty bars after it (rests of a fade or a segue into the next track, a zero-length bar left by an import) are removed with `delete_measures`, together with the section label on them. Don't put a cue text in their place unless the user asks.
- **Ghost notes: ask per chart.** List them with `ghost_notes` and ask whether to remove them (all, or some bars).
- **Half-open hi-hats:** imports usually don't mark them. Ask the user which sections or bars have a half-open hi-hat and add the symbol there.
- **Cymbal rolls** (a run of repeated or tied crash/ride notes, often with tremolo slashes): write them as one long note per bar, tied, with a roll (`simplify_roll`). A roll is one continuous roll from the first cymbal hit that rings (is tied) into it, not a held crash followed by a roll.
- **Beam across rests.** Write eighths as one beamed group per beat, with any rest inside the group under the beam (like the 2nd bar of a groove), never separate flags broken at each rest (`beam_over_rests`).
- **Song structure page.** Every chart ends with a structure page: song and artist, then section, bar count, groove, fills (`set_song_structure`). No notes column.
- **Bar counts in fours, in the section labels.** Each section label gets its length as drummers count it, in parentheses: "Chorus 4 (4+2)", black, in the label's own box (`label_section_counts`, which also sets the labels to 12 pt with 1 staff space around them, the look the user settled on). 6 bars → "4+2", 8 → "2x4", 10 → "2x4+2", 12 → "3x4", 7 → "4+3". A lead-in of 2 or more bars before the section's first groove bar is counted on its own (the intro's rest bar and pickup fill: "2+4+2"); a single bar is not ("2x4+2", not "1+2x4+1"). Bars in another time signature are counted on their own ("4+2+2": 4 bars, 2 bars of 3/4, 2 bars). A count-in bar excluded from the bar numbers is not counted. A count already written in a label is the user's: keep it (the tools do while it still adds up). The structure page shows the same counts in its Bars column, never plain numbers.
- **No red counts beside the labels** and no extra system spacing to make room for counts: MuseScore doesn't leave room between systems for text placed by hand, so they run into the dynamics of the system above. Only if the user explicitly asks for them (`placement="beside"`).
- **Header:** title = song name, subtitle = artist, no composer (nothing top right), part name "Drums" top left.
- **Bar numbers the user mentions are the numbers shown on the chart** (as played). Convert them to positions before calling tools: `get_score` shows each bar as `% m.N (bar M)`, where N is the position.

## Setup

- Connect (`connect_to_musescore`). If it fails or later reports "Not connected", ask the user to restart the plugin in MuseScore. Don't guess at what's open: check with `get_score` (bar count, staff names).
- Never save the full score, and don't ask the user to. Guitar Pro imports often have a damaged bar in another instrument; saving writes it to disk, and MuseScore then calls the file corrupted. If MuseScore showed a "corrupted" message when the score was opened, carry on: the damage usually goes away with the other instruments.
- First read what you need from the other staves (bass for the chords, vocal entries for cues): they are removed next.
- Then, as the first change, work on the drum part only in the open score: `make_part_score(staves=[<drum staff>], in_place=True)`. It saves nothing. It backs up the full score automatically (a MusicXML `.mxl` export, plus a copy of its `.mscz` when the file is known) and removes the other instruments from the open score (tempo, rehearsal marks, repeats and the title stay). No other file is opened, so the plugin stays connected. Tell the user where the backups are. If it reports `incomplete_bars`, those are bars that would still make MuseScore call the file corrupted: list them in the step 1 message. Check with `get_score` that only the drum staff is left. Don't use the copy mode (without `in_place`) unless the user asks for a separate file.
- If the open tab is a part of the full score (e.g. the drum part, not the full score), keep working there. The first file edit then saves that part automatically as its own score, "<song> - Drums.mscz", and opens it in place of the full score (the full score file is backed up and left as it is). Never ask the user to save or to switch tabs for this.
- The first file edit (step 3/5) saves the chart. If the score was imported (e.g. a `.gp` file), MuseScore asks once where to save it: tell the user beforehand, suggesting a name like "<song> - drums.mscz".
- Keep going on your own. The only planned stop is the approval round in step 1. If a tool fails, read its message and fix the cause (e.g. reconnect, retry once, use the fallback it names) instead of stopping with a menu of options. Ask the user only when no tool can do the step, and then ask one direct question. If `make_part_score` fails (e.g. a MuseScore older than 4.7), ask the user to delete the other instruments in the Instruments panel, then continue.
- Don't pass `score_path` to file-edit tools (`simplify_roll`, `set_score_header`, `set_end_notes`, `set_song_structure`, `apply_measure_repeats`, `restore_backup`): they find the open score's own file by its score ID. If one refuses ("is not the file of the score open", "Could not find the saved file"), stop and tell the user; never point it at another file.
- Never run test edits on the user's chart. `delete_measures` works with multi-measure rests on and reports an error if MuseScore deleted fewer bars than asked; then ask the user to select the bars and press Ctrl+Del.
- Collapsing, repeat barlines and play-count numbering need MuseScore 4.6+.

## Finishing a chart made earlier

If the open score is already a chart (only a drum staff, repeat barlines with play counts, section labels, bar numbers as played), finish it rather than start over, and don't ask whether to:

- Run `find_groove_sections` and `song_structure` to see what's left: runs not collapsed yet, near copies, identical odd-meter bars, empty bars at the end.
- Ask in one message which of these to apply (with what each merge would drop), then apply them from the end backwards (`collapse_to_repeat`, `delete_measures`), re-number with `number_bars_as_played`, and redo what the changes affect: beaming, counts in the labels, highlights, end notes, structure page.
- Keep what the earlier session did: the counts in the labels, the "*" marks and legend, the colours. Add to the end notes with `set_end_notes(..., append=True)` so the earlier lines stay (the report's `previous` shows what was there).

## 1. Section map and questions (wait for OK)

- Read the drums with `get_score` (and the bass for the chords, before removing it in Setup). Ignore the vocal staff for bar positions: transcriptions are often out of sync.
- Run `find_groove_sections` on the drum staff before changing anything. Per section it gives the groove bar, exact and near copies (with the hits that differ), fills, and `runs`: the collapse plan that leaves the fewest bars without dropping anything that matters. Each run has `start`, `end`, `phrase_bars`, `play_count`, `keep`, `crash_on_1` (pattern, `mark`, `legend` or `description`) and `dropped` (hits that collapsing removes, e.g. ghost notes). Keep these results: the crash patterns can't be read back after collapsing.
- `ghost_notes()` lists the ghost notes per bar.
- Look for cymbal rolls: chords with `tremolo` in `get_score`, or runs of tied/repeated crash notes.
- Keep any rehearsal marks the user already added in the full score. Otherwise propose labels.
- Propose a table before changing anything: section (Intro, Verse, Chorus/Refrain, Bridge, Solo, Turnaround, Lead-in, Outro…), bar range, and layout (e.g. "28–35: phrase 28–29 ×4", "36: written out", "37: fill"). Sections are usually 4/8/12/16 bars, often n−1 groove bars + 1 fill, but keep the song's real lengths when they differ.
- Then ask, in one message:
  - near copies that could be merged, with what would be lost (e.g. "bar 24 like 26: drops the kick on 5.5");
  - whether to remove the ghost notes (list the bars);
  - where the hi-hat is half-open;
  - the rolls you plan to simplify.
- If a section starts with a one-off transition bar (e.g. a crash bar that otherwise differs from the groove), you may propose dropping it and adding 1 to the play count, but only with the user's OK.
- Wait for the user's OK.

## 2. Compress

- Ghost notes first, if the user agreed: `ghost_notes(start_measure, end_measure, mode="remove")` on the agreed bars, so the bars that stay are clean.
- Work from the end of the score backwards so bar positions stay valid.
- Collapse each run with `collapse_to_repeat(start, end, phrase_bars)`, using the run's `phrase_bars`. It refuses when copies differ in more than the cymbal on 1 and ghost notes; use `force=True` only for a near-copy merge the user approved.
- If you delete a bar that carried a rehearsal mark, re-add the mark on the new first bar of that section (`add_rehearsal_mark`). Not for empty bars removed at the end of the song: their label goes with them.
- Turn on multi-measure rests: `processSequence` → `setStyle createMultiMeasureRests true`.
- Play counts 16 pt bold: `setStyle repeatPlayCountFontSize 16` and `repeatPlayCountFontStyle 1`.
- Crash marks, from each run's `crash_on_1` (from step 1):
  - `first_only` → "*", meaning "crash on 1st time only".
  - `every_n` → "**", meaning "crash every other bar/time" (n = 2) or "every n bars/times" (equispaced). Use the `legend` text the analysis gives ("time" for phrases longer than a bar).
  - `every_bar` → no mark: the collapsed bar already plays the crash every time.
  - `irregular` → no standard mark; tell the user (`description`, e.g. "crash on 2nd time only") and ask how to show it, or keep the run written out.
  - Put the mark above the first kept bar with `add_text` (`text="*"` or `"**"`, `size=10`, `italic=false`, `color="#000000"`). No long text on the bars.
- Legend: one `add_text` on bar 1 with `placement="above"` (it then sits right under the tempo marking), `size=8`, `italic=true`, `color="#000000"`, with only the marks used, e.g. `* crash on 1st time only   ** crash every other bar`. If "**" stands for different intervals in different sections, say which, e.g. `** crash every other bar (verses), every 4 bars (choruses)`.
- Bar numbers as played: `number_bars_as_played(exclude_from_count=[1])` when bar 1 is a silent intro bar (the user's convention). Re-run it after any change to repeats.

## 3. Notation

Positions changed while collapsing: read them again with `get_score` (`% m.N (bar M)`).

- Half-open hi-hats where the user said: `add_articulation(start_measure, end_measure, drums=["hi-hat"], symbol="half_open")`. Open hi-hats (pitch 46, circled x) already show as open; don't add symbols to them.
- Cymbal rolls: `simplify_roll(staff, start_measure, end_measure, start_beat, end_beat, drums=["crash"])`. The roll starts on `start_beat` of `start_measure` (default 1); hits before it in that bar stay as written. If the cymbals there are tied from earlier hits (a Guitar Pro import writes a crash on beat 1 left ringing into a tremolo from beat 7), the tool moves the start back to the first of those hits by itself and reports `start_moved_back`: the user wants one continuous roll from that hit. Other notes of the first chord (a kick under the crash) stay, in voice 2. `start_beat` and `end_beat` count the time signature's beats: in 12/8 an eighth, so a roll from the 4th dotted quarter of bar 93 to the end of the second dotted quarter of bar 94 is `start_measure=93, start_beat=7, end_measure=94, end_beat=6`. Lengths that don't fit one note value become tied notes. It edits the file and reloads the score. Don't ask the user to choose between workarounds: roll exactly the span they described.

- Beaming: `beam_over_rests()` over the whole drum staff, once the notes are final (after collapsing, rolls and ghost-note removal).

## 4. Colour and highlight

- Fills: green `#2ca02c` with `color_range`, only from the beat where the fill actually starts, i.e. where the hi-hat/ride time stops and toms, snare runs or accents begin (`start_beat`, fractions allowed, e.g. 2.5). Leave the groove part of the bar black. Colour the whole bar only if beat 1 already departs from the groove.
- Stops and hits before a break: red `#d62728`.
- Flams (small grace notes before a snare or tom) take the colour of the note they lead into: start a coloured range on the flammed note, and the flam is coloured with it.
- Crash hits: `highlight_notes(drums=["crash"])`, a full-height box around each crash hit only. Use it rather than `highlight_bars`, which covers whole bars.
- Dynamics: `highlight_markings` (types Dynamic) in light blue `#a7d8f0`.
- Time signatures: `highlight_symbols(kinds=["time_signatures"])`, light blue.
- Section labels stay black. Their bar counts: `label_section_counts()` writes them into the labels, "Verse 1 (2x4+2)", from the song structure (counts already in the labels are kept; pass `counts` only to correct one), and sets the label size and clearance. Re-running replaces them; re-run it after collapsing or removing bars. Don't use `placement="beside"` unless the user asks for counts outside the labels.
- Highlight boxes are sized for the current layout: draw them after the file edits of step 3, and redo them after big layout changes (`clear_highlights` with only the kinds to redo, e.g. `["highlights", "markings"]`). The "*" marks and the legend are plain text and are not affected.

## 5. Tidy and report

- Tidy the title frame with `set_score_header`: title = song name, subtitle = artist, `composer=""` (no name top right), `part_name="Drums"` (the part score's long instrument name, like "Player | Kit | Drums", runs into the title).
- A short list: what was collapsed (with phrase lengths and counts), which differences were dropped (from the runs' `dropped`, approved near-copy merges, removed ghost notes), what was left written out and why, and the notation changes (half-open hi-hats, simplified rolls). Print the same list at the end of the chart with `set_end_notes` (heading "Changes from the original", one line per item, short lines), so it ends up in the PDF. When the chart already had end notes (an earlier session), pass `append=True` so their lines stay.
- Song structure page: `song_structure()` gives each section (from the rehearsal marks) with its bars as played, its `count` in fours, its grooves (Groove A, B… with the drums used; hi-hat openings and crashes don't make a new groove) and its fills, plus `suggested_rows`. Give the grooves and fills short musical names (e.g. "Main shuffle (A)", "Verse shuffle (B)", "Tom fill into chorus"), keep `bars` and `count` as they are (section names come without the "(count)" of the labels; `count` is the label's count where it still adds up), then `set_song_structure(rows)`. The Bars column shows the count labels, the total adds up the bars, and rows are spaced for sight reading. It goes on its own page after the end notes, with the song and artist from the title frame (title and subtitle; set the header first, or pass `song` and `artist`). Use the same section names as the rehearsal marks.
- All three edit the file and reload the score (undo with `restore_backup`), so do them last.
- If something can't be done with the plugin, say so and give the quickest manual way in MuseScore.
- Don't add lyrics or lyric cues (copyrighted). Offer non-lyric cues instead ("vocals in", "guitar solo", "stop", with `add_text`) or let the user type their own.

## Iterating: undoing a step

When the user wants to change part of the result, remove only what that step added, then redo it. Limit removals to the bars and staves concerned, and never remove the user's own texts or marks: ask before clearing a whole score.

| Undo | With |
|---|---|
| Fill/stop colours | `clear_color` (same bars, `start_beat`/`end_beat`) |
| Crash, symbol and bar boxes | `clear_highlights(kinds=["highlights"])` |
| Dynamics boxes | `clear_highlights(kinds=["markings"])` |
| Recoloured time signatures / repeat signs | `highlight_symbols(mode="color", clear=True)` |
| Half-open / open / closed hi-hat symbols | `remove_articulations(start_measure, end_measure, drums=["hi-hat"])` |
| "*" marks | `remove_annotations(contains="*", exact=True)` |
| "**" marks | `remove_annotations(contains="**", exact=True)` |
| Legend | `remove_annotations(start_measure=1, end_measure=1, contains="crash")` |
| Cues and other `add_text` texts | `remove_annotations(kinds=["texts"], contains=...)` |
| Boxed labels, rehearsal marks, voltas | `remove_annotations(kinds=["labels"])`, `["rehearsal_marks"]`, `["voltas"]` |
| Bar numbers as played | `number_bars_as_played(reset=True)` (then exclusions must be set again) |
| Style changes | `setStyle` back to the defaults: `createMultiMeasureRests false`, `repeatPlayCountFontSize 10`, `repeatPlayCountFontStyle 0`, `rehearsalMarkFontSize 14`, `rehearsalMarkMinDistance 0.5` |
| Repeat barlines / play count | `set_repeat_barlines(start, end, clear=True)` |
| Title frame | `set_score_header` with the old values (`""` removes a text) |
| End notes | `set_end_notes(lines=[], heading="")` |
| Structure page | `set_song_structure(rows=[])` |
| Section bar counts | `label_section_counts(clear=True)` |
| Beaming over rests | `beam_over_rests(clear=True)` |
| Simplified rolls, measure-repeat signs, or any file edit | `restore_backup` |

Collapsing deletes bars and removing ghost notes deletes notes; only Ctrl+Z brings them back, until a file edit (`simplify_roll`, `set_score_header`, `set_end_notes`, `set_song_structure`, `apply_measure_repeats`) reloads the score and clears MuseScore's undo history. After that, `restore_backup` returns to the version before the file edit. To collapse differently, start again from the full score (open the `.mxl` backup or the original `.gp` with File > Open, then `make_part_score(..., in_place=True)`) rather than patching the old chart. That is why the file edits come late.

## Drum pitches seen in Guitar Pro / Songsterr imports

Kick 35/36 (b,, / c,), snare 38 (d,), floor tom 41 (f,), toms 43/45/47/48, closed hi-hat 42 (fis,), pedal hi-hat 44 (gis,), open hi-hat 46 (ais,, circled-x notehead), ride 51 (es), crash 49/57 (cis' / a). Ghost notes are hi-hat or snare notes in parentheses.
