$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$localPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $localPython) {
    $env:STATLENS_NODE = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
    $env:STATLENS_ARTIFACT_TOOL = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\@oai\artifact-tool\dist\artifact_tool.mjs'
    & $localPython backend/server.py
} elseif (Test-Path -LiteralPath $bundledPython) {
    $env:STATLENS_NODE = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
    $env:STATLENS_ARTIFACT_TOOL = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\@oai\artifact-tool\dist\artifact_tool.mjs'
    & $bundledPython backend/server.py
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    python backend/server.py
} else {
    Write-Error 'Python was not found. Install Python 3.11+ and follow README.md.'
}
