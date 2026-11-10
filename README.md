# MuseScore MCP Server

A Model Context Protocol (MCP) server that provides programmatic control over MuseScore, via a WebSocket-based plugin system. This allows AI assistants like Claude to compose music, add lyrics, navigate and analyse scores, restructure them with repeats, and mark them up with colors and highlights, directly in MuseScore.

![Demo GIF](./assets/mcp-muse.gif)

## What you can do

Ask Claude in plain language; it picks the tools. For example:

- **Compose and edit**: "Write a C major arpeggio in bar 3", "Add the lyrics 'Twin-kle twin-kle' from bar 1", "Set the tempo to 90 at bar 17".
- **Read large scores**: the score is read 16 bars at a time as compact LilyPond, optionally only some staves, so even a 20-staff score fits.
- **Compress a score with repeats**: "Find the repeated passages and put them between repeat barlines". The server finds bars and passages that repeat, adds repeat barlines, 1st/2nd endings and play counts, and removes the duplicate bars.
- **Build drum charts**: "Map the sections of the drum part" gives a road map (groove bar, exact and near copies, fills, and where the crashes fall). "Turn the copies into repeat signs" writes 1-, 2- or 4-bar measure-repeat signs automatically. "Make a drums-only chart with the groove written once and a 7x count" copies the score, keeps only the drums and collapses each run of identical bars. With the [drum-chart skill](docs/skills.md), "make a drum chart from the open score" runs the whole workflow (see the [example use case](#example-use-case-a-drum-chart-from-a-songsterr-tab)).
- **Keep the song's bar numbers**: "Number the bars as played" makes the displayed numbers count repeated bars, so a compact chart still matches the original song.
- **Highlight and color**: "Highlight the crash hits", "Box the dynamics", "Highlight the repeat signs and time signatures in light blue", "Color the fill on beats 3-4 of bar 13 green", "Label bar 6 'Groove x7'", "Add these cues in small grey italics at the start of each section: ...".
- **Finish the page**: "Tidy the title and call it a drum chart" cleans up the title frame; "Print what changed at the end" adds a summary of the differences from the original after the last bar, so it ends up in the PDF.
- **Iterate**: everything the tools add can be removed again ("remove the ** marks", "clear the crash highlights", "reset the bar numbers"), so you can refine the result step by step.

## Requirements

- **MuseScore 4.7 or newer.** See [Version requirements](docs/tools.md#version-requirements).
- **[uv](https://docs.astral.sh/uv/)**, which installs Python 3.13 or newer for you. Without uv you need Python 3.13+ and pip; see [Setup and running](docs/setup.md).
- **An MCP client**, such as Claude Desktop or Claude Code.

## Quick start

1. **Get the code and its dependencies** (uv also installs a matching Python if needed):

   ```bash
   git clone https://github.com/ghchen99/mcp-musescore.git
   cd mcp-musescore
   uv sync
   ```

2. **Install the MuseScore plugin:** copy `musescore-mcp-websocket.qml` into your MuseScore plugins folder (usually `~/Documents/MuseScore4/Plugins`), then enable **MuseScore API Server** under **Plugins → Plugin Manager**.

3. **Register the server with Claude Desktop** (run this in the repository folder):

   ```bash
   uv run fastmcp install claude-desktop server.py --name musescore --project .
   ```

4. **Start it:** open a score in MuseScore and run **Plugins → MuseScore API Server**. Then restart Claude Desktop and ask it to work on your score. The plugin has to be running whenever Claude uses the tools.

Other MCP clients, a manual configuration, platform notes and the setup without uv are in [Setup and running](docs/setup.md).

## Example use case: a drum chart from a Songsterr tab

How the [drum-chart skill](docs/skills.md) is used day to day, from a song on [Songsterr](https://www.songsterr.com/) to a printable drum chart.

**Once:** set up the plugin and the server ([Setup](docs/setup.md)), then install the skill in Claude Desktop ([Installing a skill](docs/skills.md#installing-a-skill-in-claude-desktop-or-claudeai)).

**For each song:**

1. **Songsterr → Guitar Pro.** Open the song on Songsterr and export it as a Guitar Pro file (`.gp`, `.gp5`…).
2. **Import it in MuseScore** with File → Open. Don't save it: the skill never saves the full score. If MuseScore says the file is corrupted, carry on: the damage is usually in another instrument, which the skill removes.
3. **Focus on the drum part.** Open the drum part in its own tab (Parts, then the drum kit), or stay on the full score. Either way the skill keeps only the drum staff, after backing up the full score to `~/.mcp-musescore/backups`.
4. **Start the plugin:** Plugins → MuseScore API Server.
5. **Call the skill.** In Claude Desktop, ask "make a drum chart from the open score".
6. **Answer when prompted.** Claude proposes a section map (sections, bar ranges, which grooves and phrases collapse into "× N") and asks, in one message:
   - which near copies to merge, and what each merge would drop (e.g. "bar 24 like 26: drops the kick on 5.5");
   - whether to remove the ghost notes;
   - where the hi-hat is half-open;
   - which cymbal rolls to simplify.

   After your OK it works on its own. The first time it saves the chart, MuseScore asks where (an imported score has no file yet): pick a name like `<song> - drums.mscz`.
7. **The chart, in the same MuseScore tab:**
   - each groove or phrase written once between repeat barlines, with its play count;
   - section labels with their bar counts, e.g. "Chorus 1 (2x4)";
   - fills in green, stops in red, crashes, dynamics and time signatures highlighted;
   - bar numbers that still match the song;
   - a tidy title: song, artist, "Drums";
   - the changes from the original after the last bar, and the song structure on its own page.

   To change something, ask in the same chat (e.g. "don't merge bar 24", "the hi-hat is half-open in the bridge too"): Claude redoes only that part.
8. **Export to PDF:** save (Ctrl+S), then File → Export → PDF.

## Documentation

| Page | What's in it |
|---|---|
| [Setup and running](docs/setup.md) | Prerequisites, installing the plugin, registering the server with Claude Desktop (with `uv` or a virtual environment), Ubuntu notes, starting order, updating, sample scores |
| [Tool reference](docs/tools.md) | Reading and navigating the score, notes, measures, tempo, instruments, highlighting and coloring, batch operations, the score viewer, version requirements, examples |
| [Repeats and drum charts](docs/drum-charts.md) | Compressing a score with repeats, drum-chart tools, measure-repeat signs and how they are written, drum notation, chart examples |
| [Agent skills](docs/skills.md) | The bundled skills and how to install them in Claude Desktop or Claude Code |
| [Development and testing](docs/development.md) | Tests, the mock plugin, running the real plugin headless, console output, file structure |
| [Troubleshooting](docs/troubleshooting.md) | Connection, plugin, server, score-file and skill problems, API limitations |

## Contributing

Contributions are welcome: fork the repository, work on a branch, and open a pull request against `main`. To set up and check your changes:

```bash
uv sync         # install the dependencies, including the test tools
uv run pytest   # run the tests
```

- **Without MuseScore**, the tests use a mock plugin, and the tests that need MuseScore skip themselves. CI runs the tests this way, so it cannot check changes to the plugin itself.
- **When you change the plugin** (`musescore-mcp-websocket.qml`), run the tests locally with MuseScore installed, so the MuseScore tests run too.
- **When you change dependencies**, use `uv add` and commit `uv.lock`, then regenerate `requirements.txt`. CI checks that the two match.

[Development and testing](docs/development.md) has the details: the mock plugin, running the real plugin headless, and managing dependencies.

## Star History

<a href="https://www.star-history.com/?repos=ghchen99%2Fmcp-musescore&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=ghchen99/mcp-musescore&type=date&theme=dark&legend=top-left&sealed_token=odyuE8YGdrYwqllb44_ZA_4jszOPlz9weSOVIc87yiR8SUSbUGaQoLxlylc2J4ZujJBLXPSCBh9dxSpTn9rD1wNfri9JkxySZuf93zfduRtC2cFbRbi0d3REHTcU3W6U0tKKmxu13NwAIo2teYBM3WjkiqauMf04gdfk8t5LM6MQ1oZFcJoY2ZVydzEg" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=ghchen99/mcp-musescore&type=date&legend=top-left&sealed_token=odyuE8YGdrYwqllb44_ZA_4jszOPlz9weSOVIc87yiR8SUSbUGaQoLxlylc2J4ZujJBLXPSCBh9dxSpTn9rD1wNfri9JkxySZuf93zfduRtC2cFbRbi0d3REHTcU3W6U0tKKmxu13NwAIo2teYBM3WjkiqauMf04gdfk8t5LM6MQ1oZFcJoY2ZVydzEg" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=ghchen99/mcp-musescore&type=date&legend=top-left&sealed_token=odyuE8YGdrYwqllb44_ZA_4jszOPlz9weSOVIc87yiR8SUSbUGaQoLxlylc2J4ZujJBLXPSCBh9dxSpTn9rD1wNfri9JkxySZuf93zfduRtC2cFbRbi0d3REHTcU3W6U0tKKmxu13NwAIo2teYBM3WjkiqauMf04gdfk8t5LM6MQ1oZFcJoY2ZVydzEg" />
 </picture>
</a>
