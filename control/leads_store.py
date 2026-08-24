"""JSON pipeline for Beo Leads. No secrets in this file."""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
STATE_PATH = REPO / "agents" / "leads-beo" / "home" / "pipeline" / "state.json"
LOCK = threading.Lock()

STATUSES = (
    "found",
    "skipped_no_email",
    "skipped_too_big",
    "skipped_low_score",
    "pending_approval",
    "rejected",
    "approved",
    "sent",
    "replied",
    "closed_no_reply",
)

STATUS_HE = {
    "found": "נמצא",
    "skipped_no_email": "דילג (אין מייל)",
    "skipped_too_big": "דילג (גדול מדי)",
    "skipped_low_score": "דילג (ציון נמוך)",
    "pending_approval": "ממתין לאישור",
    "rejected": "נדחה",
    "approved": "אושר · ממתין ל-Gmail",
    "sent": "נשלח",
    "replied": "נענה → ליד",
    "closed_no_reply": "לא ענו → סגור",
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today_il() -> str:
    # Israel is UTC+2 / +3; date-only for daily batch is local enough via UTC+3 window.
    from datetime import timedelta

    return (datetime.now(timezone.utc) + timedelta(hours=3)).strftime("%Y-%m-%d")


def _empty() -> dict[str, Any]:
    return {"updated_at": _now(), "items": []}


def _read() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return _empty()
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty()
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        return _empty()
    return data


def _write(data: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = _now()
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_PATH)


def load() -> dict[str, Any]:
    with LOCK:
        return _read()


def save_item(item: dict[str, Any]) -> dict[str, Any]:
    with LOCK:
        data = _read()
        items: list[dict[str, Any]] = data["items"]
        item_id = str(item.get("id") or "")
        if not item_id:
            item["id"] = str(uuid.uuid4())
            item_id = item["id"]
        found = False
        for i, row in enumerate(items):
            if str(row.get("id")) == item_id:
                items[i] = item
                found = True
                break
        if not found:
            items.append(item)
        _write(data)
        return item


def get_item(item_id: str) -> dict[str, Any] | None:
    with LOCK:
        for row in _read().get("items") or []:
            if str(row.get("id")) == item_id:
                return row
    return None


def known_domains() -> set[str]:
    with LOCK:
        out: set[str] = set()
        for row in _read().get("items") or []:
            domain = str(row.get("domain") or "").strip().lower()
            if domain:
                out.add(domain)
            email = str(row.get("email") or "").strip().lower()
            if "@" in email:
                out.add(email.split("@", 1)[1])
        return out


def pending_today_count() -> int:
    day = today_il()
    with LOCK:
        n = 0
        for row in _read().get("items") or []:
            if row.get("status") == "pending_approval" and str(row.get("batch_date") or "") == day:
                n += 1
        return n


def overview() -> dict[str, Any]:
    day = today_il()
    with LOCK:
        items = _read().get("items") or []
    def count(*statuses: str, today: bool = False) -> int:
        n = 0
        for row in items:
            if row.get("status") not in statuses:
                continue
            if today and str(row.get("batch_date") or "") != day:
                continue
            n += 1
        return n

    return {
        "ok": True,
        "date": day,
        "target_ready_by": "10:00",
        "daily_target": 10,
        "score_floor": 72,
        "checked_today": count(
            "found",
            "skipped_no_email",
            "skipped_too_big",
            "skipped_low_score",
            "pending_approval",
            "rejected",
            "approved",
            "sent",
            today=True,
        ),
        "skipped_today": count("skipped_no_email", "skipped_too_big", "skipped_low_score", today=True),
        "pending_approval": count("pending_approval"),
        "pending_today": count("pending_approval", today=True),
        "sent_today": count("sent", today=True),
        "replied": count("replied"),
        "closed_no_reply": count("closed_no_reply"),
        "gmail_connected": gmail_connected(),
        "gmail_oauth_file": gmail_oauth_present(),
        "openai_connected": openai_connected(),
        "telegram_connected": telegram_connected(),
        "whatsapp_url": _env_value("WHATSAPP_ME_URL") or "",
        "from_email": _env_value("GMAIL_FROM") or "sales@beosystem.com",
        "from_name": _env_value("GMAIL_FROM_NAME") or "שי | Beo Systems",
        "status_labels": STATUS_HE,
    }


def pipeline(status: str | None = None) -> dict[str, Any]:
    with LOCK:
        items = list(_read().get("items") or [])
    if status:
        items = [r for r in items if r.get("status") == status]
    items.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return {"ok": True, "items": items, "status_labels": STATUS_HE}


def approvals() -> dict[str, Any]:
    return pipeline("pending_approval")


def _env_path() -> Path:
    return REPO / "agents" / "leads-beo" / ".env"


def _env_value(key: str) -> str:
    from_env = (os.environ.get(key) or "").strip().strip('"').strip("'")
    if from_env:
        return from_env
    path = _env_path()
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k.strip() == key:
            return v.strip().strip('"').strip("'")
    return ""


def openai_connected() -> bool:
    return bool(_env_value("OPENAI_API_KEY"))


def telegram_connected() -> bool:
    return bool(_env_value("TELEGRAM_BOT_TOKEN"))


def gmail_oauth_present() -> bool:
    creds = REPO / "agents" / "leads-beo" / "secrets" / "gmail-oauth.json"
    return creds.is_file()


def gmail_connected() -> bool:
    for path in (
        REPO / "agents" / "leads-beo" / "secrets" / "gmail-token.json",
        REPO / "agents" / "leads-beo" / "home" / "secrets" / "gmail-token.json",
    ):
        if path.is_file():
            return True
    return bool(_env_value("GMAIL_REFRESH_TOKEN"))


def set_status(item_id: str, status: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    if status not in STATUSES:
        return {"ok": False, "error": "סטטוס לא חוקי"}
    with LOCK:
        data = _read()
        for i, row in enumerate(data["items"]):
            if str(row.get("id")) == item_id:
                row["status"] = status
                row["updated_at"] = _now()
                if extra:
                    row.update(extra)
                data["items"][i] = row
                _write(data)
                return {"ok": True, "item": row}
    return {"ok": False, "error": "פריט לא נמצא"}
