# Junction Hermes profile leads-beo → this repo folder. Does not touch other profiles.
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$target = Join-Path $repo "agents\leads-beo"
$link = Join-Path $env:LOCALAPPDATA "hermes\profiles\leads-beo"
if (-not (Test-Path -LiteralPath $target)) {
    Write-Host "Missing $target"
    exit 1
}
if (Test-Path -LiteralPath $link) {
    Write-Host "Profile already exists: $link"
    exit 0
}
cmd /c "mklink /J `"$link`" `"$target`""
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Linked $link -> $target"
