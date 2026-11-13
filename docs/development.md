# Development and testing

[Overview](../README.md) · [Setup](setup.md) · [Tools](tools.md) · [Repeats & drum charts](drum-charts.md) · [Skills](skills.md) · [Development](development.md) · [Troubleshooting](troubleshooting.md)


The project is managed with [uv](https://docs.astral.sh/uv/). Run these commands in the repository folder:

```bash
# Install the dependencies, including the development tools (creates .venv from uv.lock)
uv sync

# Launch the MCP Inspector against your server
uv run fastmcp dev inspector server.py

# List the registered tools
uv run fastmcp inspect server.py

# Run the tests (no MuseScore needed; the MuseScore-based tests are skipped without it)
uv run pytest
```

## Dependencies

`pyproject.toml` lists the dependencies and `uv.lock` pins the exact versions that everyone, and CI, uses. Commit both.

```bash
uv add <package>          # a dependency of the server
uv add --dev <package>    # a development tool, such as a test plugin
uv lock --upgrade         # move to the newest versions the ranges allow
```

`requirements.txt` is generated from `uv.lock`, for setups without uv. Don't edit it by hand: when a commit changes `uv.lock` or `pyproject.toml`, the commit hook regenerates it (see below), and CI fails when it is out of date.

## Checks before committing (prek)

[prek](https://github.com/j178/prek) runs the checks in `prek.toml` (prek's own configuration format) before every commit. Install the hooks once per clone:

```bash
uv run prek install
```

The hooks:

- **generate requirements.txt from uv.lock**: runs `uv export --no-dev --no-hashes -o requirements.txt` when a commit changes `uv.lock` or `pyproject.toml`. If the file changes, the commit stops; stage the updated `requirements.txt` and commit again.
- **deptry**: every package the code imports is declared in `pyproject.toml`, and every declared package is used.
- **ty type check**: [ty](https://github.com/astral-sh/ty) checks the types in `src/`, `server.py`, `dev/` and `tests/` (set in `[tool.ty.src]` in `pyproject.toml`), with ty's default rules: errors stop the commit, warnings are only shown. It runs when a commit changes a Python file, and always checks the whole project, since a change in one module can break the types in another. To run it yourself: `uv run ty check`.
- **QML plugin syntax check**: `node syntax_check.js` parses the plugin's JavaScript. It only runs when a commit changes a `.qml` file, so you need [Node.js](https://nodejs.org/) only to work on the plugin.

If a hook fails, the commit is stopped; fix the problem and commit again. Plain `uv run prek` checks only what is staged, setting unstaged changes aside meanwhile; to check the whole working tree, as CI does:

```bash
uv run prek run --all-files
```

## Tests with coverage

The tests are not a commit hook: they run separately, locally and as their own step in CI.

```bash
uv run pytest --no-musescore --cov
```

- **`--no-musescore`** skips the tests that need MuseScore, even when it is installed, so the run takes a few seconds and gives the same result on every machine, whatever MuseScore is installed. CI runs the MuseScore tests in its `musescore-tests` job. When you change the plugin, run them yourself with plain `uv run pytest` (see [Running the real plugin headless](#running-the-real-plugin-headless)).
- **`--cov`** measures branch coverage of `src/`, with the settings in `[tool.coverage]` in `pyproject.toml`. The run fails when coverage drops below 86%, the level measured without MuseScore, so coverage cannot go down unnoticed. Only raise `fail_under`, as tests are added, never lower it, so the coverage can only improve.

## Makefile

The Makefile gives the common commands short names; each one runs the `uv` command shown.

| Command | Runs |
|---|---|
| `make install` | `uv sync`, then `uv run prek install` |
| `make check` | `uv run prek run --all-files` |
| `make test` | `uv run pytest --no-musescore --cov` |
| `make test-musescore` | `uv run pytest`: also the MuseScore tests, when MuseScore is found |

CI's `test` job runs `make check` and `make test`. On Windows, where `make` is usually not installed, run the `uv` commands directly.

## Mock MuseScore plugin

`tests/mock_musescore.py` is an in-memory stand-in for the QML plugin. It speaks the same WebSocket protocol on port 8765, so you can run the MCP server and the Inspector without MuseScore:

```bash
# Terminal 1: fake plugin (do not run alongside the real plugin, same port)
# --demo preloads a two-staff Twinkle Twinkle score
uv run python tests/mock_musescore.py --demo

# Terminal 2: MCP Inspector against the server
uv run fastmcp dev inspector server.py
```

The mock implements a subset of the plugin's actions over a simplified 4/4 score. `tests/test_integration.py` uses it to exercise the real tools and WebSocket client.

## Running the real plugin headless

For changes to the plugin itself, `dev/plugin_harness.py` runs the real plugin in a local MuseScore, without the GUI, on a copy of a score. It prints each command's result and can save or render the edited score. MuseScore runs from a throwaway profile, so your own settings and plugins are not touched:

```bash
uv run python dev/plugin_harness.py '[{"action": "highlightNotes", "params": {"startMeasure": 1, "endMeasure": 2}}]' \
    "examples/jazz piano/Jazz Piano.mscz" --out /tmp/edited.mscz --png /tmp/preview.png
```

MuseScore is found through `MUSESCORE_BIN`, an AppImage in `~/.local/bin`, or `mscore` on the `PATH`. `tests/test_plugin_headless.py` and the file round-trip test in `tests/test_mscz.py` use the same detection and are skipped when MuseScore is not installed. `MUSESCORE_BIN=none`, or `uv run pytest --no-musescore`, skips them even when MuseScore is installed. With a MuseScore installed as a Flatpak, the tests may find a launcher that returns before MuseScore is done, and the MuseScore tests fail; point `MUSESCORE_BIN` at a MuseScore AppImage instead.

CI runs these tests too, in the `musescore-tests` job: on MuseScore 4.7.0, the oldest supported version, and on the latest release. It unpacks the official AppImage (the runner has no FUSE), points `MUSESCORE_BIN` at it, and runs the tests under `xvfb-run`, because MuseScore uses X11 on Linux even when asked to run offscreen.

## Viewing Console Output

To see MuseScore plugin console output, run MuseScore from terminal:

**macOS**:
```bash
/Applications/MuseScore\ 4.app/Contents/MacOS/mscore
```

**Windows**:
```cmd
cd "C:\Program Files\MuseScore 4\bin"
MuseScore.exe
```

**Linux** (distribution package):
```bash
musescore4
```

**Linux** (AppImage, e.g. on Ubuntu):
```bash
~/.local/bin/MuseScore-Studio-*.AppImage
```
Logs are also written to `~/.local/share/MuseScore/MuseScore4/logs/`.

## File Structure

```
mcp-musescore/
├── server.py                           # Python MCP server entry point
├── musescore-mcp-websocket.qml         # MuseScore plugin (the WebSocket server)
├── pyproject.toml                      # Project metadata and dependencies (uv)
├── uv.lock                             # Exact dependency versions (generated by uv)
├── requirements.txt                    # Generated from uv.lock, for setups without uv
├── Makefile                            # Short names for common commands: install, check, test
├── prek.toml                           # Commit hooks: requirements.txt, deptry, ty, QML syntax
├── .github/
│   └── workflows/                      # CI (pr-validation.yml), explained in its README.md
├── README.md
├── docs/                               # User documentation (setup, tools, drum charts...)
├── dev/
│   └── plugin_harness.py               # Run the real plugin headless in MuseScore
├── skills/
│   ├── mcp-musescore/                  # Agent skill: tool reference, client config, helper scripts
│   └── musescore-drum-chart/           # Agent skill: compact drum chart workflow
├── tests/                              # Pytest suite and the mock plugin
├── examples/                           # Sample scores
└── src/                                # Source code modules
    ├── client/                         # WebSocket client functionality
    │   └── websocket_client.py
    ├── tools/                          # MCP tool implementations
    │   ├── connection.py               # Connection and score reading
    │   ├── navigation.py               # Score navigation tools
    │   ├── notes_measures.py           # Note and measure manipulation
    │   ├── sequences.py                # Batch operation tools
    │   ├── staff_instruments.py        # Staff and instrument tools
    │   ├── time_tempo.py               # Timing and tempo tools
    │   ├── structure.py                # Repeat analysis, repeats, voltas, drum charts
    │   ├── score_file.py               # Measure-repeat signs and backups (file edits)
    │   ├── formatting.py               # Coloring, highlights and labels
    │   └── viewer.py                   # show_score MCP App tool
    ├── mscz/                           # Reading and editing .mscz/.mscx files
    │   ├── score_file.py
    │   ├── measure_repeats.py
    │   ├── frames.py                   # Title frame, end notes, song structure page
    │   ├── parts.py                    # Part scores from a full score
    │   ├── rolls.py                    # Cymbal rolls
    │   └── locate.py                   # Finding the open score's file, backups
    ├── ui/
    │   └── score_viewer.html           # VexFlow notation viewer
    ├── utils/
    │   ├── lilypond_converter.py       # Score JSON to LilyPond
    │   ├── repetition.py               # Repeated-measure analysis
    │   └── sections.py                 # Groove/fill section analysis
    └── types/
        └── action_types.py             # WebSocket action type definitions
```
