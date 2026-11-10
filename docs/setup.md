# Setup and running

[Overview](../README.md) · [Setup](setup.md) · [Tools](tools.md) · [Repeats & drum charts](drum-charts.md) · [Skills](skills.md) · [Development](development.md) · [Troubleshooting](troubleshooting.md)

## Prerequisites

- MuseScore 4.7 or newer (see [Version requirements](tools.md#version-requirements)). MuseScore 3 is not supported.
- Python 3.13+
- Claude Desktop or compatible MCP client

## Setup

### 1. Install the MuseScore Plugin

Put the QML plugin in your MuseScore plugins directory:

**macOS**: `~/Documents/MuseScore4/Plugins/musescore-mcp-websocket.qml`
**Windows**: `%USERPROFILE%\Documents\MuseScore4\Plugins\musescore-mcp-websocket.qml`
**Linux**: `~/Documents/MuseScore4/Plugins/musescore-mcp-websocket.qml` (see [Ubuntu](#ubuntu) for Snap/Flatpak installs)

If you work from a clone of this repository, a symlink keeps the plugin up to date when you pull (macOS/Linux):

```bash
ln -sfn "$PWD/musescore-mcp-websocket.qml" ~/Documents/MuseScore4/Plugins/musescore-mcp-websocket.qml
```

### 2. Enable the Plugin in MuseScore

1. Open MuseScore
2. Go to **Plugins → Plugin Manager**
3. Find **MuseScore API Server** and check the box to enable it
4. Click **OK**

### 3. Configure Claude Desktop (with `uv`)

[uv](https://docs.astral.sh/uv/) manages the Python version and the environment for you. The repository is a uv project: `pyproject.toml` lists the dependencies and `uv.lock` pins the exact tested versions, so `uv sync` sets everything up and no `uv init` is needed.

**First-time setup:**

1. Install uv:

   ```bash
   # macOS / Linux
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

   ```powershell
   # Windows (PowerShell)
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

   (`brew install uv`, `winget install --id=astral-sh.uv -e` or `pipx install uv` work too.) Open a new terminal afterwards so `uv` is on your `PATH`.

2. Get the code and install the dependencies (uv also downloads a matching Python if you don't have one):

   ```bash
   git clone https://github.com/MikFerrari/mcp-musescore.git
   cd mcp-musescore
   uv sync
   ```

3. Check that the server starts. Run this in the repository folder; it should end with a summary listing the registered tools:

   ```bash
   uv run fastmcp inspect server.py
   ```

**Register the server with Claude Desktop.** The quickest way is to let FastMCP write the Claude Desktop config for you. Run this in the repository folder; `--project .` is turned into the full path of the repository:

```bash
uv run fastmcp install claude-desktop server.py --name musescore --project .
```

To print the config instead of writing it, use `fastmcp install mcp-json` with the same options.

Or add it manually to your Claude Desktop configuration file:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
**Linux**: `~/.config/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "musescore": {
      "command": "uv",
      "args": [
        "run",
        "--directory", "/path/to/mcp-musescore",
        "server.py"
      ]
    }
  }
}
```

**Note**: Replace `/path/to/mcp-musescore` with the location of your clone. Claude Desktop does not start the server from the repository folder, so the full path is needed here: `--directory` makes uv run from that folder, where it finds the project and `server.py`.

**Windows on ARM**: `cryptography` (a FastMCP dependency) has no ARM64 Windows wheel, so uv would try to compile it and fail with `link.exe not found`. Use the x64 Python instead: run `uv sync --python cpython-3.13-windows-x86_64` once in the repository folder. uv then keeps using that Python for the project's environment.

<details>
<summary>Without uv (manual virtual environment)</summary>

```bash
git clone <your-repo>
cd mcp-musescore
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

`requirements.txt` is generated from `uv.lock`, so pip installs the same tested versions. Then point Claude Desktop at the venv's Python:

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

### Ubuntu

These steps were tested on Ubuntu with the MuseScore Studio 4.7 AppImage.

1. **MuseScore**: download the AppImage from [musescore.org](https://musescore.org/en/download), make it executable and start it once so it creates its folders. AppImages need FUSE 2:

   ```bash
   sudo apt install libfuse2t64          # Ubuntu 24.04 and later; on 22.04: sudo apt install libfuse2
   mkdir -p ~/.local/bin
   mv ~/Downloads/MuseScore-Studio-*.AppImage ~/.local/bin/
   chmod +x ~/.local/bin/MuseScore-Studio-*.AppImage
   ~/.local/bin/MuseScore-Studio-*.AppImage
   ```

   The plugins folder is `~/Documents/MuseScore4/Plugins`. If you installed MuseScore with Snap or Flatpak, it may be elsewhere: check **Edit → Preferences → Folders → Plugins**, and use that folder in the symlink command of step 1.

2. **Plugin**: link it from your clone, then enable it as in step 2:

   ```bash
   mkdir -p ~/Documents/MuseScore4/Plugins
   ln -sfn "$PWD/musescore-mcp-websocket.qml" ~/Documents/MuseScore4/Plugins/musescore-mcp-websocket.qml
   ```

3. **uv**: the install script from step 3, or the snap:

   ```bash
   sudo snap install astral-uv --classic
   ```

   Claude Desktop started from the app menu may not have `~/.local/bin` on its `PATH`. If it reports that it cannot start the server, put the full path printed by `which uv` (e.g. `/home/<you>/.local/bin/uv` or `/snap/bin/uv`) in `"command"` instead of `"uv"`.

4. **Claude Desktop**: the config file is `~/.config/Claude/claude_desktop_config.json`. Closing the window leaves Claude Desktop running in the system tray: quit it from the tray icon (or File → Quit) before starting it again, otherwise it keeps the old server process.

5. **Console output and logs**: start the AppImage from a terminal to see the plugin's output. MuseScore also writes logs to `~/.local/share/MuseScore/MuseScore4/logs/`.

## Running the System

### Order of Operations

1. **Start MuseScore first** with a score open
2. **Run the MuseScore plugin**: Go to **Plugins → MuseScore API Server**
   - You should see console output: `"Starting MuseScore API Server on port 8765"`
3. **Then start the Python MCP server** or restart Claude Desktop

### After updating

Both halves load their code once, at startup:

- **Plugin changes** (`musescore-mcp-websocket.qml`): restart MuseScore, then run **Plugins → MuseScore API Server** again.
- **Server changes** (`server.py`, `src/`): quit Claude Desktop completely (File → Quit, not just closing the window; on Linux it may keep running in the tray) and start it again, then open a new chat so it fetches the new tool list.

## Sample Music

Check out the [`examples`](../examples) folder for sample MuseScore files demonstrating various musical styles:

- **Asian Instrumental** - Traditional Asian-inspired instrumental piece
- **Jazz Piano** - Jazz piano piece
- **String Quartet** - Classical string quartet arrangement

Each example includes:
- `.mscz` - MuseScore file (editable)
- `.pdf` - Sheet music
- `.mp3` - Audio preview
