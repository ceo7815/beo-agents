# Run Beo Leads daily research (up to 10 drafts for Beo OS approval).
# Does not send mail. Does not start Telegram. Does not touch social-beo.
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath (Join-Path $repo "control")
python -c "from leads_research import run_daily; import json; print(json.dumps(run_daily(10), ensure_ascii=False, indent=2))"
