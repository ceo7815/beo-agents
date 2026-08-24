"""Daily research on the server only. Does not send mail."""

from __future__ import annotations

import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

from leads_store import pending_today_count, today_il
from power import leads_is_on

IL = timezone(timedelta(hours=3))


def _log(msg: str) -> None:
    sys.stderr.write(f"[leads-schedule] {msg}\n")
    sys.stderr.flush()


def scheduler_enabled() -> bool:
    host = (os.environ.get("BEO_CONTROL_HOST") or "127.0.0.1").strip()
    return host in {"0.0.0.0", "::"}


def _il_now() -> datetime:
    return datetime.now(timezone.utc).astimezone(IL)


def _il_workday(now: datetime) -> bool:
    return now.weekday() in {6, 0, 1, 2, 3}


def _tick() -> None:
    from leads_research import run_daily
    from leads_telegram import _save_state, _state, notify_ten_ready

    if not leads_is_on() or not _il_workday(_il_now()):
        return
    now = _il_now()
    if now.hour < 10 or now.hour >= 17:
        return
    day = today_il()
    state = _state()
    if state.get("research_on") == day:
        if pending_today_count() >= 10:
            notify_ten_ready()
        return
    if pending_today_count() >= 10:
        state["research_on"] = day
        state["research_done"] = day
        _save_state(state)
        notify_ten_ready()
        return
    state["research_on"] = day
    _save_state(state)
    _log("run_daily start")
    try:
        result = run_daily(target=10)
        _log(f"run_daily {result.get('message') or 'done'}")
    except Exception as exc:
        _log(f"run_daily failed {type(exc).__name__}")
        result = {}
    state = _state()
    state["research_done"] = day
    _save_state(state)
    n = pending_today_count()
    if n >= 10:
        notify_ten_ready()
    elif n > 0:
        from leads_telegram import notify_or

        notify_or(
            f"המחקר היומי הסתיים.\n\nיש {n} טיוטות לאישור ב-Beo OS."
        )
    else:
        from leads_telegram import notify_or

        notify_or(
            "המחקר היומי הסתיים.\n\nלא נמצאו טיוטות היום — אפשר להריץ שוב מ-Beo OS."
        )


def _loop() -> None:
    while True:
        try:
            _tick()
        except Exception:
            _log("tick failed")
        time.sleep(45)


def start_schedule_thread() -> None:
    if not scheduler_enabled():
        _log("skip (not server)")
        return
    thread = threading.Thread(target=_loop, name="leads-schedule", daemon=True)
    thread.start()
    _log("start")
