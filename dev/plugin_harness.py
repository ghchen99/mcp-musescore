"""Run the QML plugin's commands headless in MuseScore, without the GUI or the WebSocket bridge.

Builds a copy of musescore-mcp-websocket.qml whose onRun executes a fixed list of commands,
runs it on a score with MuseScore's converter (`--extension`), and prints each command's result.
MuseScore runs from a throwaway profile in a temporary folder, so your own settings and
plugins are not touched.

    python dev/plugin_harness.py '[{"action": "getScore", "params": {"startMeasure": 1, "endMeasure": 2}}]' \\
        "examples/jazz piano/Jazz Piano.mscz" --out /tmp/edited.mscz --png /tmp/edited.png

Commands are a JSON list (inline or a path to a .json file) of {"action": ..., "params": {...}},
exactly what the Python server sends over the WebSocket. Results are passed back through a
"harness" meta tag in the output score, because console.log is not captured in converter mode.
"""

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

REPO = Path(__file__).resolve().parent.parent
PLUGIN = REPO / "musescore-mcp-websocket.qml"
HARNESS_NAME = "mcp-harness.qml"
EXTENSION_URI = f"musescore://extensions/v1/{HARNESS_NAME}"


def find_musescore() -> Optional[str]:
    """MuseScore executable: $MUSESCORE_BIN, an AppImage in ~/.local/bin, or mscore on PATH.

    MUSESCORE_BIN=none means no MuseScore, even when one is installed, so the tests that need it skip themselves.
    """
    if os.environ.get("MUSESCORE_BIN") == "none":
        return None
    candidates = [os.environ.get("MUSESCORE_BIN", "")]
    candidates += sorted(glob.glob(os.path.expanduser("~/.local/bin/MuseScore*.AppImage")))
    candidates += [shutil.which(n) or "" for n in ("mscore4portable", "mscore4", "mscore", "musescore")]
    return next((c for c in candidates if c and os.access(c, os.X_OK)), None)


def build_harness(commands: List[Dict[str, Any]], plugin_source: Union[str, Path] = PLUGIN) -> str:
    """Plugin source whose onRun runs `commands` and stores the results in a meta tag."""
    code = Path(plugin_source).read_text(encoding="utf-8")
    on_run = code.index("    onRun: {")
    runner = f"""    onRun: {{
        var commands = {json.dumps(commands)};
        initCursorState();
        var results = [];
        for (var i = 0; i < commands.length; i++) {{
            var result;
            try {{ result = processCommand(commands[i]); }} catch (e) {{ result = {{ error: e.toString() }}; }}
            results.push({{ action: commands[i].action, result: result }});
        }}
        curScore.startCmd();
        curScore.setMetaTag("harness", JSON.stringify(results));
        curScore.endCmd();
    }}
}}
"""
    head = code[:on_run].replace('menuPath: "Plugins.MuseScore API Server"', 'menuPath: "Plugins.MCP Harness"')
    return head.replace('title: "MuseScore API Server"', 'title: "MCP Harness"') + runner


def read_results(score_path: Union[str, Path]) -> Optional[List[Dict[str, Any]]]:
    """Results stored by the harness in the output score, or None."""
    with zipfile.ZipFile(score_path) as z:
        name = next(n for n in z.namelist() if n.endswith(".mscx") and "/" not in n)
        root = ET.fromstring(z.read(name))
    tag = next((t for t in root.iter("metaTag") if t.get("name") == "harness"), None)
    return json.loads(tag.text) if tag is not None and tag.text else None


def _musescore(binary: str, args: List[str], home: Path, timeout: float) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_DATA_HOME": str(home / ".local" / "share"),
        "QT_QPA_PLATFORM": "offscreen",
    }
    return subprocess.run([binary, *args], env=env, timeout=timeout, capture_output=True, text=True)


def run(commands: List[Dict[str, Any]], score: Union[str, Path], out: Optional[Union[str, Path]] = None,
        png: Optional[Union[str, Path]] = None, musescore: Optional[str] = None, timeout: float = 300,
        png_dpi: int = 130) -> List[Dict[str, Any]]:
    """Run commands on a copy of `score`. Returns the list of {"action", "result"} entries.

    out: where to save the edited score (.mscz); png: where to render it (one file per page,
    MuseScore adds -1, -2, ... before the extension).
    """
    binary = musescore or find_musescore()
    if not binary:
        raise RuntimeError("MuseScore not found: set MUSESCORE_BIN")

    with tempfile.TemporaryDirectory(prefix="mcp-harness-") as tmp:
        tmp = Path(tmp)
        home = tmp / "home"
        plugins = home / "Documents" / "MuseScore4" / "Plugins"
        extensions = home / ".local" / "share" / "MuseScore" / "MuseScore4" / "extensions"
        plugins.mkdir(parents=True)
        extensions.mkdir(parents=True)
        (plugins / HARNESS_NAME).write_text(build_harness(commands), encoding="utf-8")
        (extensions / "config.json").write_text(json.dumps(
            [{"actions": [{"code": "main", "exec_point": "manually"}], "uri": EXTENSION_URI}]))

        work = tmp / "work"  # MuseScore may clear the folder it writes into: keep it private
        work.mkdir()
        source = work / ("input" + Path(score).suffix)
        shutil.copy(score, source)
        edited = work / "output.mscz"

        proc = _musescore(binary, ["--extension", f"{EXTENSION_URI}?action=main", "-o", str(edited), str(source)],
                          home, timeout)
        if proc.returncode != 0 or not edited.exists():
            raise RuntimeError(f"MuseScore failed (exit {proc.returncode}):\n{proc.stdout[-2000:]}{proc.stderr[-2000:]}")
        results = read_results(edited)
        if results is None:
            raise RuntimeError("The harness ran but left no results (did the plugin fail to load?)")

        if out:
            shutil.copy(edited, out)
        if png:
            render_dir = tmp / "render"
            render_dir.mkdir()
            proc = _musescore(binary, ["-r", str(png_dpi), "-o", str(render_dir / Path(png).name), str(edited)],
                              home, timeout)
            pages = sorted(render_dir.glob(f"{Path(png).stem}*{Path(png).suffix}"))
            if not pages:
                raise RuntimeError(f"Rendering failed (exit {proc.returncode})")
            for page in pages:
                shutil.copy(page, Path(png).parent / page.name)
        return results


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("commands", help="JSON list of commands, inline or a path to a .json file")
    parser.add_argument("score", help="Score to run them on (.mscz or .mscx); it is not modified")
    parser.add_argument("--out", help="Save the edited score here (.mscz)")
    parser.add_argument("--png", help="Render the edited score here (one PNG per page)")
    parser.add_argument("--dpi", type=int, default=130, help="PNG resolution")
    parser.add_argument("--musescore", help="MuseScore executable (default: $MUSESCORE_BIN or auto-detect)")
    args = parser.parse_args()

    text = Path(args.commands).read_text() if args.commands.endswith(".json") else args.commands
    results = run(json.loads(text), args.score, out=args.out, png=args.png, musescore=args.musescore,
                  png_dpi=args.dpi)
    for entry in results:
        print(f"{entry['action']} -> {json.dumps(entry['result'])}")
    return 1 if any(isinstance(e["result"], dict) and "error" in e["result"] for e in results) else 0


if __name__ == "__main__":
    sys.exit(main())
