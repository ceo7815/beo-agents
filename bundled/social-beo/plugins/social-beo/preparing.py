"""One Telegram wait-notice when a post starts producing."""

from __future__ import annotations

import threading
import time

from .telegram_send import send_telegram

TEXT = (
    "זה יקח כמה דקות. אני מכין את התוכן, את התמונה ואת הכל — לאישור ולפרסום."
)

PRODUCTION_TOOLS = {
    "make_beo_visual",
    "web_search",
    "get_brand_assets",
    "get_platform_specs",
    "save_social_pack",
}

_lock = threading.Lock()
_last_sent = 0.0
_turns: set[str] = set()


def send_preparing() -> bool:
    """Send the wait notice at most once per ~45s."""
    global _last_sent
    with _lock:
        now = time.time()
        if now - _last_sent < 45:
            return False
        _last_sent = now
    ok = send_telegram(TEXT)
    if not ok:
        with _lock:
            _last_sent = 0.0
    return ok


def on_pre_tool_call(tool_name: str, args: dict, task_id: str = "", **kwargs):
    del args, kwargs
    if tool_name not in PRODUCTION_TOOLS:
        return None
    turn = str(task_id or "")
    with _lock:
        if turn and turn in _turns:
            return None
        if turn:
            if len(_turns) > 40:
                _turns.clear()
            _turns.add(turn)
    send_preparing()
    return None
