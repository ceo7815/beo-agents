"""Stop post creation on cancel phrases before the LLM / questionnaires."""

from __future__ import annotations

import asyncio
import logging

from .cancel import ACK, looks_like_cancel
from .intent import looks_like_brief
from .publish_demo import clear_awaiting, handle_inbound

log = logging.getLogger("social-beo")


def _session_key(gateway, event) -> str:
    source = getattr(event, "source", None)
    fn = getattr(gateway, "_session_key_for_source", None)
    if callable(fn) and source is not None:
        try:
            key = fn(source)
            if key:
                return str(key)
        except Exception:
            log.exception("session key failed")
    chat_id = str(getattr(source, "chat_id", "") or "default")
    return f"tg-{chat_id}"


def _loop(gateway):
    return getattr(gateway, "_gateway_loop", None)


def _run_coro(gateway, coro) -> None:
    loop = _loop(gateway)
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is not None:
        running.create_task(coro)
        return
    if loop is None:
        coro.close()
        return
    try:
        from agent.async_utils import safe_schedule_threadsafe
    except Exception:
        asyncio.run_coroutine_threadsafe(coro, loop)
        return
    safe_schedule_threadsafe(coro, loop, logger=log, log_message="cancel send failed")


def _authorized(gateway, event) -> bool:
    fn = getattr(gateway, "_is_user_authorized", None)
    source = getattr(event, "source", None)
    if not callable(fn) or source is None:
        return True
    try:
        return bool(fn(source))
    except Exception:
        return True


def _stop_run(gateway, event) -> None:
    source = event.source
    session_key = _session_key(gateway, event)
    interrupt_fn = getattr(gateway, "_interrupt_and_clear_session", None)
    if callable(interrupt_fn) and session_key:
        _run_coro(
            gateway,
            interrupt_fn(
                session_key,
                source,
                interrupt_reason="user-cancel-post",
                invalidation_reason="user-cancel-post",
            ),
        )
    try:
        from tools.clarify_gateway import clear_session

        clear_session(session_key)
    except Exception:
        log.exception("clear clarify failed")
    store = getattr(gateway, "session_store", None)
    if store is not None and session_key and hasattr(store, "reset_session"):
        try:
            store.reset_session(session_key)
        except Exception:
            log.exception("reset session failed")


def _send_text(gateway, event, text: str) -> None:
    if not (text or "").strip():
        return
    adapters = getattr(gateway, "adapters", None) or {}
    adapter = adapters.get(event.source.platform)
    if adapter is None:
        return
    _run_coro(gateway, adapter.send(str(event.source.chat_id), text))


def on_pre_gateway_dispatch(event, gateway, **kwargs):
    del kwargs
    if event is None or gateway is None:
        return None
    if not _authorized(gateway, event):
        return None
    text = str(getattr(event, "text", "") or "").strip()
    if handle_inbound(text):
        return {"action": "skip", "reason": "publish-approval"}
    if looks_like_brief(text):
        clear_awaiting()
    if not looks_like_cancel(text):
        return None
    clear_awaiting()
    _stop_run(gateway, event)
    _send_text(gateway, event, ACK)
    return {"action": "skip", "reason": "cancel-post"}


def on_pre_llm_call(session_id: str, user_message: str, **kwargs):
    del session_id, kwargs
    text = user_message or ""
    if looks_like_cancel(text):
        return {
            "context": (
                "המשתמש ביטל את הפוסט ואת השאלון. אסור לקרוא כלים "
                "(לא clarify, לא web_search, לא make_beo_visual). "
                "השב בדיוק את הטקסט הבא בלבד:\n"
                f"{ACK}"
            )
        }
    if looks_like_brief(text):
        return {
            "context": (
                "ההודעה הזו היא הבריף. אל תשאל על מה הפוסט. "
                "אל תציג תפריט מוצרי Beo. "
                "אם חסרים עובדות — web_search. "
                "clarify רק אם חסרים פלטפורמה/פורמט ואין ברירת מחדל בזיכרון. "
                "אחרי תיקון או העדפה שלו — memory(target=user). "
                "אם הוא מתייחס לשיחה קודמת — session_search."
            )
        }
    return None
