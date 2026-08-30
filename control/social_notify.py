"""Push-only Telegram for עדי. Never polls — Hermes owns the chat token."""

from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from social_store import REPO

CTX = ssl.create_default_context()


def _env(key: str) -> str:
    val = (os.environ.get(key) or "").strip()
    if val:
        return val
    for path in (
        REPO / "bundled" / "social-beo" / ".env",
        REPO / "agents" / "social-beo" / ".env",
    ):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            if k.strip() == key:
                return v.strip().strip('"').strip("'")
    return ""


def _token() -> str:
    return _env("SOCIAL_TELEGRAM_BOT_TOKEN") or _env("TELEGRAM_BOT_TOKEN")


def _chat_id() -> str:
    raw = _env("TELEGRAM_ALLOWED_USERS") or _env("TELEGRAM_HOME_CHANNEL")
    return raw.split(",")[0].strip()


def notify_or(text: str) -> None:
    token = _token()
    chat = _chat_id()
    if not token or not chat:
        return
    payload = json.dumps(
        {"chat_id": chat, "text": text[:3500], "disable_web_page_preview": True},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=12, context=CTX):
            pass
    except (urllib.error.URLError, TimeoutError, OSError):
        pass


def notify_published(row: dict[str, Any], *, dry_run: bool, error: str) -> None:
    when = str(row.get("scheduled_at") or "")[:16]
    ig = (row.get("caption_ig") or row.get("caption") or "")[:120]
    if error and not (row.get("meta_ids") or {}).get("facebook_feed") and not (row.get("meta_ids") or {}).get("instagram_feed"):
        notify_or(f"עדי: פרסום נכשל ({when}).\n{error[:300]}")
        return
    mode = "סימולציה (עדיין בלי טוקן Meta)" if dry_run else "עלה לאינסטגרם ולפייסבוק"
    extra = f"\nחלקי: {error[:200]}" if error else ""
    notify_or(f"עדי: {mode}.\n{when}\n{ig}{extra}")
