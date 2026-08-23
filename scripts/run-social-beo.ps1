# Run Beo Social locally on the existing Windows Hermes install.
# Does not touch default / call-qa / offer-agent profiles.
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$home = Join-Path $repo "agents\social-beo"
if (-not (Test-Path -LiteralPath (Join-Path $home ".env"))) {
    Write-Host "Missing agents\social-beo\.env — copy .env.example and fill OPENAI_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USERS"
    exit 1
}
Set-Location -LiteralPath $home
hermes -p social-beo gateway run
