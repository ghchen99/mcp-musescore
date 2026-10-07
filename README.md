# MuseScore MCP Server

A Model Context Protocol (MCP) server that provides programmatic control over MuseScore, via a WebSocket-based plugin system. This allows AI assistants like Claude to compose music, add lyrics, navigate scores, and control MuseScore directly.

![Demo GIF](./assets/mcp-muse.gif)

## Prerequisites

- MuseScore 3.x or 4.x
- Python 3.13+
- Claude Desktop or compatible MCP client

## Setup

### 1. Install the MuseScore Plugin

First, save the QML plugin code to your MuseScore plugins directory:

**macOS**: `~/Documents/MuseScore4/Plugins/musescore-mcp-websocket.qml`
**Windows**: `%USERPROFILE%\Documents\MuseScore4\Plugins\musescore-mcp-websocket.qml`
**Linux**: `~/Documents/MuseScore4/Plugins/musescore-mcp-websocket.qml`

### 2. Enable the Plugin in MuseScore

1. Open MuseScore
2. Go to **Plugins → Plugin Manager**
3. Find "MuseScore API Server" and check the box to enable it
4. Click **OK**

### 3. Configure Claude Desktop (with `uv`)

Install [uv](https://docs.astral.sh/uv/). It creates and caches the Python environment on first launch, so there is no venv to manage and the config needs no `.venv` path.

The quickest way is to let FastMCP write the Claude Desktop config for you:

```bash
fastmcp install claude-desktop server.py --name musescore --python 3.13 --with-requirements requirements.txt
```

To print the config instead of writing it, use `fastmcp install mcp-json` with the same options.

Or add it manually to your Claude Desktop configuration file:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "musescore": {
      "command": "uv",
      "args": [
        "run",
        "--no-project",
        "--python", "3.13",
        "--with-requirements", "/path/to/mcp-musescore/requirements.txt",
        "/path/to/mcp-musescore/server.py"
      ]
    }
  }
}
```

**Note**: Update the paths to match your actual project location.

**Windows on ARM**: `cryptography` (a FastMCP dependency) has no ARM64 Windows wheel, so uv would try to compile it and fail with `link.exe not found`. Use the x64 Python instead by replacing `"3.13"` with `"cpython-3.13-windows-x86_64"` after `--python`.

<details>
<summary>Without uv (manual virtual environment)</summary>

```bash
git clone <your-repo>
cd mcp-musescore
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Then point Claude Desktop at the venv's Python:

```json
{
  "mcpServers": {
    "musescore": {
      "command": "/path/to/mcp-musescore/.venv/bin/python",
      "args": ["/path/to/mcp-musescore/server.py"]
    }
  }
}
```

</details>

## Running the System

### Order of Operations

1. **Start MuseScore first** with a score open
2. **Run the MuseScore plugin**: Go to **Plugins → MuseScore API Server**
   - You should see console output: `"Starting MuseScore API Server on port 8765"`
3. **Then start the Python MCP server** or restart Claude Desktop

[insert screenshot of different functionality, harmonisation, melodywriting, as zoomed in GIFs]

### Development and Testing

For development, use the FastMCP CLI:

```bash
# Install the project dependencies (includes the FastMCP CLI)
pip install -r requirements.txt

# Launch the MCP Inspector against your server
fastmcp dev inspector server.py

# List the registered tools
fastmcp inspect server.py

# Run the tests (no MuseScore needed)
pip install pytest
pytest
```

#### Mock MuseScore plugin

`tests/mock_musescore.py` is an in-memory stand-in for the QML plugin. It speaks the same WebSocket protocol on port 8765, so you can run the MCP server and the Inspector without MuseScore:

```bash
# Terminal 1: fake plugin (do not run alongside the real plugin, same port)
# --demo preloads a two-staff Twinkle Twinkle score
python tests/mock_musescore.py --demo

# Terminal 2: MCP Inspector against the server
fastmcp dev inspector server.py
```

It implements a subset of the plugin's actions (ping, getScore, getCursorInfo, addNote, addRest, addLyrics, goToMeasure, appendMeasure, setTimeSignature, setTempo, addInstrument, undo, processSequence). `tests/test_integration.py` uses it to exercise the real tools and WebSocket client.

### Viewing Console Output

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

**Linux**:
```bash
musescore4
```

## Features

This MCP server provides comprehensive MuseScore control. 

**🌟 NEW in this fork:** Built-in automatic, flawless multi-voice Polyphony & Temporal layout mapping to LilyPond!

### **Navigation & Cursor Control**
- `get_cursor_info()` - Get current cursor position and selection info
- `go_to_measure(measure)` - Navigate to specific measure
- `go_to_beginning_of_score()` / `go_to_final_measure()` - Navigate to start/end
- `next_element()` / `prev_element()` - Move cursor element by element
- `next_staff()` / `prev_staff()` - Move between staves
- `select_current_measure()` - Select entire current measure
- `select_custom_range(start_tick, end_tick, start_staff, end_staff)` - Slicing tool to extract cross-measure, multi-staff phrasing

### **Polyphony & LilyPond Integration**
- **Temporal Rhythm Padding**: Voices with gaps or rests automatically receive LilyPond spacer sequences (`s4.`) to hold their mathematical place accurately.
- **Concurrent Voice Rendering**: Full 4-voice (`\voiceOne`, `\voiceTwo`, etc.) arrays correctly structured and sharded per staff for advanced Agent processing.

### **Note & Rest Creation**
- `add_note(pitch, duration, advance_cursor_after_action, add_to_chord)` - Add notes with MIDI pitch. Sequential notes write a melody; set `add_to_chord=True` to stack a pitch on the current chord.
- `add_rest(duration, advance_cursor_after_action)` - Add rests
- `add_tuplet(duration, ratio, advance_cursor_after_action)` - Add tuplets (triplets, etc.)

### **Measure Management**
- `insert_measure()` - Insert measure at current position
- `append_measure(count)` - Add measures to end of score
- `delete_selection(measure)` - Delete current selection or specific measure

### **Lyrics & Text**
- `add_lyrics_to_current_note(text)` - Add lyrics to current note
- `add_lyrics(lyrics_list)` - Batch add lyrics to multiple notes
- `set_title(title)` - Set score title

### **Score Information**
- `get_score()` - Get complete score analysis and structure
- `show_score(first_measure, last_measure)` - Render the score as sheet music in an interactive viewer (see below)
- `ping_musescore()` - Test connection to MuseScore
- `connect_to_musescore()` - Establish WebSocket connection

### **Utilities**
- `undo()` - Undo last action
- `set_time_signature(numerator, denominator)` - Change time signature
- `processSequence(sequence)` - Execute multiple commands in batch

### Score viewer (MCP Apps)

`show_score` is an [MCP App](https://gofastmcp.com/apps/overview): the tool result is rendered as notation by a small [VexFlow](https://www.vexflow.com/) page (`src/ui/score_viewer.html`) inside hosts that support MCP Apps. Hosts without that support only get a one-line text summary, so use `get_score` there.

- Rendering was verified in a regular browser against the mock plugin. It has not been verified inside Claude or Claude Desktop.
- The page loads VexFlow and the MCP Apps SDK from `unpkg.com`, so the host needs internet access (the server declares that domain in the app's CSP).
- Not drawn: tuplet brackets and ties. Tuplet notes use their written value.
- Long scores: pass `first_measure` and `last_measure` to show a section.

## Sample Music

Check out the `/examples` folder for sample MuseScore files demonstrating various musical styles:

- **Asian Instrumental** - Traditional Asian-inspired instrumental piece
- **String Quartet** - Classical string quartet arrangement

Each example includes:
- `.mscz` - MuseScore file (editable)
- `.pdf` - Sheet music
- `.mp3` - Audio preview

## Usage Examples

### Creating a Simple Melody

```python
# Set up the score
await set_title("My First Song")
await go_to_beginning_of_score()

# Add notes (MIDI pitch: 60=C, 62=D, 64=E, etc.)
await add_note(60, {"numerator": 1, "denominator": 4}, True)  # Quarter note C
await add_note(64, {"numerator": 1, "denominator": 4}, True)  # Quarter note E
await add_note(67, {"numerator": 1, "denominator": 4}, True)  # Quarter note G
await add_note(72, {"numerator": 1, "denominator": 2}, True)  # Half note C

# Add lyrics
await go_to_beginning_of_score()
await add_lyrics_to_current_note("Do")
await next_element()
await add_lyrics_to_current_note("Mi")
await next_element()
await add_lyrics_to_current_note("Sol")
await next_element()
await add_lyrics_to_current_note("Do")
```
### Batch Operations

```python
# Add multiple lyrics at once
await add_lyrics(["Twin-", "kle", "twin-", "kle", "lit-", "tle", "star"])

# Use sequence processing for complex operations
sequence = [
    {"action": "goToBeginningOfScore", "params": {}},
    {"action": "addNote", "params": {"pitch": 60, "duration": {"numerator": 1, "denominator": 4}, "advanceCursorAfterAction": True}},
    {"action": "addNote", "params": {"pitch": 64, "duration": {"numerator": 1, "denominator": 4}, "advanceCursorAfterAction": True}},
    {"action": "addRest", "params": {"duration": {"numerator": 1, "denominator": 4}, "advanceCursorAfterAction": True}}
]
await processSequence(sequence)
```

## Star History

<a href="https://www.star-history.com/?repos=ghchen99%2Fmcp-musescore&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=ghchen99/mcp-musescore&type=date&theme=dark&legend=top-left&sealed_token=odyuE8YGdrYwqllb44_ZA_4jszOPlz9weSOVIc87yiR8SUSbUGaQoLxlylc2J4ZujJBLXPSCBh9dxSpTn9rD1wNfri9JkxySZuf93zfduRtC2cFbRbi0d3REHTcU3W6U0tKKmxu13NwAIo2teYBM3WjkiqauMf04gdfk8t5LM6MQ1oZFcJoY2ZVydzEg" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=ghchen99/mcp-musescore&type=date&legend=top-left&sealed_token=odyuE8YGdrYwqllb44_ZA_4jszOPlz9weSOVIc87yiR8SUSbUGaQoLxlylc2J4ZujJBLXPSCBh9dxSpTn9rD1wNfri9JkxySZuf93zfduRtC2cFbRbi0d3REHTcU3W6U0tKKmxu13NwAIo2teYBM3WjkiqauMf04gdfk8t5LM6MQ1oZFcJoY2ZVydzEg" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=ghchen99/mcp-musescore&type=date&legend=top-left&sealed_token=odyuE8YGdrYwqllb44_ZA_4jszOPlz9weSOVIc87yiR8SUSbUGaQoLxlylc2J4ZujJBLXPSCBh9dxSpTn9rD1wNfri9JkxySZuf93zfduRtC2cFbRbi0d3REHTcU3W6U0tKKmxu13NwAIo2teYBM3WjkiqauMf04gdfk8t5LM6MQ1oZFcJoY2ZVydzEg" />
 </picture>
</a>

## Troubleshooting

### Connection Issues
- **"Not connected to MuseScore"**: 
  - Ensure MuseScore is running with a score open
  - Run the MuseScore plugin (Plugins → MuseScore API Server)
  - Check that port 8765 isn't blocked by firewall

### Plugin Issues
- **Plugin not appearing**: Check the `.qml` file is in the correct plugins directory
- **Plugin won't enable**: Restart MuseScore after placing the plugin file
- **No console output**: Run MuseScore from terminal to see debug messages

### Python Server Issues
- **"No server object found"**: The server object must be named `mcp`, `server`, or `app` at module level
- **WebSocket errors**: Make sure MuseScore plugin is running before starting Python server
- **Connection timeout**: The MuseScore plugin must be actively running, not just enabled

### API Limitations
- **Lyrics**: Only first verse supported in MuseScore 3.x plugin API
- **Title setting**: Uses multiple fallback methods due to frame access limitations
- **Selection persistence**: Some operations may affect current selection

## File Structure

```
mcp-agents-demo/
├── .venv/
├── server.py                           # Python MCP server entry point
├── musescore-mcp-websocket.qml         # MuseScore plugin
├── requirements.txt
├── README.md
└── src/                                # Source code modules
    ├── __init__.py
    ├── client/                         # WebSocket client functionality
    │   ├── __init__.py
    │   └── websocket_client.py
    ├── tools/                          # MCP tool implementations
    │   ├── __init__.py
    │   ├── connection.py               # Connection management tools
    │   ├── navigation.py               # Score navigation tools
    │   ├── notes_measures.py           # Note and measure manipulation
    │   ├── sequences.py                # Batch operation tools
    │   ├── staff_instruments.py        # Staff and instrument tools
    │   ├── time_tempo.py               # Timing and tempo tools
    │   └── viewer.py                   # show_score MCP App tool
    ├── ui/
    │   └── score_viewer.html           # VexFlow notation viewer
    └── types/                          # Type definitions
        ├── __init__.py
        └── action_types.py             # WebSocket action type definitions
```

## MIDI Pitch Reference

Common MIDI pitch values for reference:
- **Middle C**: 60
- **C Major Scale**: 60, 62, 64, 65, 67, 69, 71, 72
- **Chromatic**: C=60, C#=61, D=62, D#=63, E=64, F=65, F#=66, G=67, G#=68, A=69, A#=70, B=71

## Duration Reference

Duration format: `{"numerator": int, "denominator": int}`
- **Whole note**: `{"numerator": 1, "denominator": 1}`
- **Half note**: `{"numerator": 1, "denominator": 2}`
- **Quarter note**: `{"numerator": 1, "denominator": 4}`
- **Eighth note**: `{"numerator": 1, "denominator": 8}`
- **Dotted quarter**: `{"numerator": 3, "denominator": 8}`
