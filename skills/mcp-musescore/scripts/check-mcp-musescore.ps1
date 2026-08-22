$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoDir = if ($env:MCP_MUSESCORE_DIR) { $env:MCP_MUSESCORE_DIR } else { Join-Path $HOME "Downloads\mcp-musescore" }
$pythonBin = if ($env:MCP_MUSESCORE_PYTHON) { $env:MCP_MUSESCORE_PYTHON } else { Join-Path $repoDir ".venv\Scripts\python.exe" }

if (-not (Test-Path (Join-Path $repoDir "server.py"))) { throw "server.py not found in $repoDir" }
if (-not (Test-Path $pythonBin)) { throw "Python executable not found: $pythonBin" }

Push-Location $repoDir
try {
  & $pythonBin -m compileall -q server.py src
  & $pythonBin -c "import server; print('MCP server import OK')"
  & $pythonBin (Join-Path $scriptDir "probe-musescore-bridge.py")
}
finally { Pop-Location }
