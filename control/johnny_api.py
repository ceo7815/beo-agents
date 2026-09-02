"""OS board payload for Johnny."""

from __future__ import annotations

from johnny_google import connected as google_connected
from johnny_os import os_connected, os_get, resolve_actor_id
from johnny_store import env_flag, get_pending, johnny_is_on, recent_actions, rivhit_connected
from johnny_tools import _specialists, _today


def overview() -> dict:
    g = google_connected()
    pending = get_pending()
    uid = resolve_actor_id()
    tasks = os_get("tasks", assigneeId=uid, limit=40) if os_connected() and uid else {"items": []}
    today = _today()
    open_tasks = [
        t
        for t in (tasks.get("items") or [])
        if isinstance(t, dict) and str(t.get("status") or "") not in {"done"}
    ]
    due_today = [t for t in open_tasks if str(t.get("dueDate") or "").startswith(today)]
    specs = _specialists()
    shay = specs.get("shay") if isinstance(specs.get("shay"), dict) else {}
    adi = specs.get("adi") if isinstance(specs.get("adi"), dict) else {}
    return {
        "ok": True,
        "on": johnny_is_on(),
        "os_connected": os_connected(),
        "telegram": env_flag("JOHNNY_TELEGRAM_BOT_TOKEN"),
        "openai": env_flag("OPENAI_API_KEY"),
        "gmail": g.get("gmail"),
        "calendar": g.get("calendar"),
        "actor_id": uid,
        "pending": pending,
        "open_tasks": len(open_tasks),
        "due_today": len(due_today),
        "shay_pending": shay.get("pending_approval") or shay.get("pending") or 0,
        "adi_pending": adi.get("pending_review") or 0,
        "actions": recent_actions(10),
        "mailbox": "ceo@beosystem.co.il",
        "calendar_master": "Google Calendar",
        "meet": bool(g.get("calendar")),
        "voice": True,
        "web_search": True,
        "rivhit": rivhit_connected(),
        "approve_writes": True,
        "chat_api": "responses",
        "build": "luna-responses",
    }
