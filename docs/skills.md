# Agent skills

[Overview](../README.md) · [Setup](setup.md) · [Tools](tools.md) · [Repeats & drum charts](drum-charts.md) · [Skills](skills.md) · [Development](development.md) · [Troubleshooting](troubleshooting.md)


The `skills/` folder holds skills: instructions that teach Claude (or another agent) how to use this server well.

- **`skills/mcp-musescore/`**: general use of the tools, with a per-tool reference (`references/tools.md`), client configuration and helper scripts.
- **`skills/musescore-drum-chart/`**: turns a full score into a compact, colour-coded drum chart following a drummer's rules: never drop kicks, snares or hi-hat openings, collapse 2- or 4-bar phrases where grooves alternate, ask before merging near copies or removing ghost notes, add half-open hi-hat symbols where you say, and write cymbal rolls as one tied note with a roll. It:
  1. works on a drums-only copy, so the original score is never touched;
  2. maps the sections and waits for your OK;
  3. collapses each groove or phrase into "× N", keeping fills, stops and odd bars written out, then cleans up the notation (ghost notes on request, half-open hi-hats, cymbal rolls);
  4. marks crash patterns the collapsed bar can't show (`*` first time only, `**` every other bar or every n bars) with a legend under the tempo;
  5. colours fills (green) and stops (red), and highlights crashes, dynamics and time signatures;
  6. numbers the bars as played, tidies the title, and prints the changes from the original at the end.

  It also lists how to undo each step, so you can ask for changes and it redoes only that part.

## Installing a skill in Claude Desktop (or claude.ai)

1. **Package the skill** with `make skill`, which writes `artifacts/musescore-drum-chart.zip`. The ZIP's top level is the skill folder, as Claude expects (`musescore-drum-chart/SKILL.md` inside the archive; a `SKILL.md` at the root of the ZIP is not recognized). Without `make`: `cd skills && zip -r ../artifacts/musescore-drum-chart.zip musescore-drum-chart`.

2. **Enable code execution**: in Claude Desktop, open **Settings → Capabilities** and make sure file creation / code execution ("Create and edit files") is on. Skills need it.
3. **Upload the skill**: open **Customize → Skills**, click **+**, choose **Create skill → Upload a skill**, and select `artifacts/musescore-drum-chart.zip`. Make sure the skill is switched on in the list.
4. **Use it**: with MuseScore open and the plugin running, ask for example "make a drum chart from the open score". Claude picks the skill from its description.

**Updating a skill**: after editing `SKILL.md` (or pulling a new version), package it again and upload the new ZIP; if Claude Desktop keeps the old version, delete it under Customize → Skills first. Claude Desktop uses its own uploaded copy, so edits in the repository have no effect until you upload again.

Custom skills belong to your account and are not shared with other users (on Enterprise plans an owner can provide them organization-wide).

## Using a skill in Claude Code

Copy or link the folder into `.claude/skills/` (this project) or `~/.claude/skills/` (all projects), e.g.:

```bash
mkdir -p ~/.claude/skills
ln -sfn "$PWD/skills/musescore-drum-chart" ~/.claude/skills/musescore-drum-chart
```

With a link, edits in the repository apply directly.
