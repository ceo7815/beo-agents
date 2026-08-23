# Run the Beo Agents dashboard locally (control API + UI).
# Does not start agent gateways. Bind 127.0.0.1 only.
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath (Join-Path $repo "dashboard")
if (-not (Test-Path -LiteralPath "node_modules")) {
    npm install
}
$control = Start-Process -FilePath "python" -ArgumentList @(
    (Join-Path $repo "control\server.py")
) -WorkingDirectory (Join-Path $repo "control") -PassThru -WindowStyle Hidden
Write-Host "Control PID $($control.Id)  http://127.0.0.1:8788"
Write-Host "Dashboard  http://127.0.0.1:5174"
try {
    npm run dev
} finally {
    if (-not $control.HasExited) {
        Stop-Process -Id $control.Id -Force -ErrorAction SilentlyContinue
    }
}
