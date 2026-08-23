# Control API only (127.0.0.1:8788). Needed by Beo OS /ai-agents.
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath (Join-Path $repo "control")
python server.py
