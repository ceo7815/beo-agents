"""Ask yes/no after the preview, then confirm IG+FB publish for the demo."""

from __future__ import annotations

import re
import threading
import time

from .telegram_send import send_telegram

ASK = "לאשר לפרסום?"
PUBLISHED = "פורסם. אינסטגרם ופייסבוק — עלה לבד לשניהם."
REJECTED = "לא פרסמתי. תגיד מה לשנות."

_YES = {
    "כן",
    "כן.",
    "כן!",
    "מאשר",
    "תפרסם",
    "תפרסמי",
    "יאללה",
    "יאללה תפרסם",
    "בטח",
    "ok",
    "okay",
    "yes",
    "publish",
}
_NO = {
    "לא",
    "לא.",
    "לא!",
    "אל תפרסם",
    "תדחה",
    "no",
    "nope",
}

_awaiting = False
_lock = threading.Lock()
_ask_at = 0.0


def mark_awaiting() -> None:
    global _awaiting
    with _lock:
        _awaiting = True


def clear_awaiting() -> None:
    global _awaiting
    with _lock:
        _awaiting = False


def is_awaiting() -> bool:
    with _lock:
        return _awaiting


def _compact(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).strip(".,!?… \t")


def looks_like_yes(text: str) -> bool:
    t = _compact(text)
    return t in _YES or t.lower() in _YES


def looks_like_no(text: str) -> bool:
    t = _compact(text)
    return t in _NO or t.lower() in _NO


def _yes_no_keyboard() -> dict:
    return {
        "keyboard": [[{"text": "כן"}, {"text": "לא"}]],
        "resize_keyboard": True,
        "one_time_keyboard": True,
    }


def ask_approval() -> None:
    if not is_awaiting():
        return
    send_telegram(ASK, reply_markup=_yes_no_keyboard())


def schedule_ask() -> None:
    global _ask_at
    mark_awaiting()
    with _lock:
        now = time.time()
        if now - _ask_at < 20:
            return
        _ask_at = now
    threading.Timer(2.2, ask_approval).start()


def handle_inbound(text: str) -> str | None:
    """Publishing is approved in Beo OS only. Telegram never confirms a live post."""
    del text
    return None


def on_transform_llm_output(response_text: str, **kwargs):
    del kwargs, response_text
    return None
