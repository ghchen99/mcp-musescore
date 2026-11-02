# Development and testing

[Overview](../README.md) · [Setup](setup.md) · [Tools](tools.md) · [Repeats & drum charts](drum-charts.md) · [Skills](skills.md) · [Development](development.md) · [Troubleshooting](troubleshooting.md)


For development, use the FastMCP CLI:

```bash
# Install the project dependencies (includes the FastMCP CLI)
pip install -r requirements.txt

# Launch the MCP Inspector against your server
fastmcp dev inspector server.py

# List the registered tools
fastmcp inspect server.py

# Run the tests (no MuseScore needed; the MuseScore-based tests are skipped without it)
pip install pytest
pytest
```

## Mock MuseScore plugin

`tests/mock_musescore.py` is an in-memory stand-in for the QML plugin. It speaks the same WebSocket protocol on port 8765, so you can run the MCP server and the Inspector without MuseScore:

```bash
# Terminal 1: fake plugin (do not run alongside the real plugin, same port)
# --demo preloads a two-staff Twinkle Twinkle score
python tests/mock_musescore.py --demo

# Terminal 2: MCP Inspector against the server
fastmcp dev inspector server.py
```

The mock implements a subset of the plugin's actions over a simplified 4/4 score. `tests/test_integration.py` uses it to exercise the real tools and WebSocket client.

## Running the real plugin headless

For changes to the plugin itself, `dev/plugin_harness.py` runs the real plugin in a local MuseScore, without the GUI, on a copy of a score. It prints each command's result and can save or render the edited score. MuseScore runs from a throwaway profile, so your own settings and plugins are not touched:

```bash
python dev/plugin_harness.py '[{"action": "highlightNotes", "params": {"startMeasure": 1, "endMeasure": 2}}]' \
    "examples/jazz piano/Jazz Piano.mscz" --out /tmp/edited.mscz --png /tmp/preview.png
```

MuseScore is found through `MUSESCORE_BIN`, an AppImage in `~/.local/bin`, or `mscore` on the `PATH`. `tests/test_plugin_headless.py` and the file round-trip test in `tests/test_mscz.py` use the same detection and are skipped when MuseScore is not installed.

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
├── requirements.txt
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
