$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoDir = if ($env:MCP_MUSESCORE_DIR) { $env:MCP_MUSESCORE_DIR } else { Join-Path $HOME "Downloads\mcp-musescore" }
$server = Join-Path $repoDir "server.py"
$pythonBin = if ($env:MCP_MUSESCORE_PYTHON) { $env:MCP_MUSESCORE_PYTHON } else { Join-Path $repoDir ".venv\Scripts\python.exe" }

if (-not (Test-Path $server)) {
  throw "mcp-musescore repository not found: $repoDir. Set MCP_MUSESCORE_DIR to the checkout containing server.py."
}

if (-not (Test-Path $pythonBin)) {
  $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
  if ($pythonCommand) { $pythonBin = $pythonCommand.Source }
  else { throw "No usable Python executable found: $pythonBin" }
}

Push-Location $repoDir
try { & $pythonBin $server @args }
finally { Pop-Location }
