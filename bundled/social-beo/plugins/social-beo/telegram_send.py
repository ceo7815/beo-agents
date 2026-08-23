"""Tiny Telegram Bot API helper for Beo Social notices."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

log = logging.getLogger("social-beo")


def chat_id() -> str:
    return (
        os.environ.get("TELEGRAM_HOME_CHANNEL")
        or (os.environ.get("TELEGRAM_ALLOWED_USERS") or "").split(",")[0]
        or ""
    ).strip()


def send_telegram(text: str, reply_markup: dict[str, Any] | None = None) -> bool:
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat = chat_id()
    if not token or not chat or not (text or "").strip():
        return False
    body: dict[str, Any] = {"chat_id": chat, "text": text}
    if reply_markup is not None:
        body["reply_markup"] = reply_markup
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return 200 <= getattr(resp, "status", 200) < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        log.exception("telegram send failed")
        return False
