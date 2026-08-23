# One-time: open Google login for sales@beosystem.com and save Gmail token.
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath (Join-Path $repo "control")
pip install -q google-auth-oauthlib google-api-python-client google-auth-httplib2
python -c "from gmail_client import connect_interactive; import json; print(json.dumps(connect_interactive(), ensure_ascii=False))"
