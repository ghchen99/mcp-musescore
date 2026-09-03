#!/usr/bin/env bash
set -Eeuo pipefail

script_dir="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="${MCP_MUSESCORE_DIR:-$HOME/Downloads/mcp-musescore}"
python_bin="${MCP_MUSESCORE_PYTHON:-$repo_dir/.venv/bin/python}"

[ -f "$repo_dir/server.py" ] || { printf 'server.py not found in %s\n' "$repo_dir" >&2; exit 1; }
[ -x "$python_bin" ] || { printf 'Python executable not found: %s\n' "$python_bin" >&2; exit 1; }

cd "$repo_dir"
"$python_bin" -m compileall -q server.py src
"$python_bin" -c 'import server; print("MCP server import OK")'
"$python_bin" "$script_dir/probe-musescore-bridge.py"
