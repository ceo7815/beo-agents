"""Beo Leads plugin tools — write into the shared pipeline store."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[4]
CONTROL = ROOT / "control"
if str(CONTROL) not in sys.path:
    sys.path.insert(0, str(CONTROL))

from leads_store import (  # noqa: E402
    _env_value,
    _now,
    overview,
    pipeline,
    save_item,
    today_il,
)


def _ok(payload: dict[str, Any]) -> str:
    return json.dumps({"ok": True, **payload}, ensure_ascii=False, indent=2)


def _err(message: str) -> str:
    return json.dumps({"ok": False, "error": message}, ensure_ascii=False)


def leads_overview(params: dict, **kwargs) -> str:
    del kwargs, params
    return json.dumps(overview(), ensure_ascii=False, indent=2)


def leads_pipeline(params: dict, **kwargs) -> str:
    del kwargs
    status = str((params or {}).get("status") or "").strip() or None
    return json.dumps(pipeline(status), ensure_ascii=False, indent=2)


def record_lead_candidate(params: dict, **kwargs) -> str:
    del kwargs
    company = str(params.get("company") or "").strip()
    website = str(params.get("website") or "").strip()
    if not company or not website:
        return _err("company and website are required")
    email = str(params.get("email") or "").strip() or None
    skip = bool(params.get("skip")) or not email
    host = (urlparse(website if "://" in website else f"https://{website}").hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    whatsapp = _env_value("WHATSAPP_ME_URL") or ""
    item = {
        "id": "",
        "company": company,
        "website": website if website.startswith("http") else f"https://{website}",
        "domain": host,
        "email": None if skip else email,
        "phone": str(params.get("phone") or ""),
        "score": int(params.get("score") or 0),
        "score_why": str(params.get("score_why") or ""),
        "service": str(params.get("service") or ""),
        "status": "skipped_no_email" if skip else "pending_approval",
        "skip_reason": "אין מייל גלוי באתר" if skip else "",
        "email_subject": str(params.get("email_subject") or ""),
        "email_body": str(params.get("email_body") or ""),
        "from_name": _env_value("GMAIL_FROM_NAME") or "שי | Beo Systems",
        "from_email": _env_value("GMAIL_FROM") or "sales@beosystem.com",
        "whatsapp_url": whatsapp,
        "created_at": _now(),
        "updated_at": _now(),
        "batch_date": today_il(),
    }
    saved = save_item(item)
    return _ok({"item": saved})
