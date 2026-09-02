"""Daily research on the server only. Does not send mail."""

from __future__ import annotations

import os
import sys
import threading
import time

from leads_store import israel_now, pending_today_count, today_il
from power import leads_is_on

# 10 cold drafts ready at 10:00. Hunt from 06:00; keep going until 17:00 if short.
HUNT_START_HOUR = 6
READY_BY_HOUR = 10
HUNT_END_HOUR = 17
EOD_HOUR = 18


def _log(msg: str) -> None:
    sys.stderr.write(f"[leads-schedule] {msg}\n")
    sys.stderr.flush()


def scheduler_enabled() -> bool:
    host = (os.environ.get("BEO_CONTROL_HOST") or "127.0.0.1").strip()
    return host in {"0.0.0.0", "::"}


def _il_now():
    return israel_now()


def _il_workday(now) -> bool:
    return now.weekday() in {6, 0, 1, 2, 3}


def _tick() -> None:
    from leads_research import DAILY_TARGET, run_daily
    from leads_telegram import _save_state, _state, eod_text, notify_or, notify_ten_ready

    now = _il_now()
    day = today_il()
    workday = _il_workday(now)

    if workday and now.hour == EOD_HOUR:
        state = _state()
        if state.get("eod_on") != day:
            try:
                notify_or(eod_text())
            except Exception:
                _log("eod send failed")
            state = _state()
            state["eod_on"] = day
            _save_state(state)

    if not leads_is_on() or not workday:
        return

    try:
        from leads_outreach import queue_followups

        fu = queue_followups()
        if int(fu.get("queued") or 0):
            _log(f"followups queued {fu.get('queued')}")
    except Exception:
        _log("followup queue failed")

    n = pending_today_count()
    if n >= DAILY_TARGET:
        state = _state()
        state["research_on"] = day
        state["research_done"] = day
        _save_state(state)
        notify_ten_ready()
        return

    if now.hour < HUNT_START_HOUR:
        return

    if now.hour == READY_BY_HOUR:
        state = _state()
        if state.get("morning10_on") != day:
            state["morning10_on"] = day
            _save_state(state)
            try:
                if n >= DAILY_TARGET:
                    notify_ten_ready()
                else:
                    notify_or(
                        f"10:00 — יש {n} טיוטות קרות לאישור ב-Beo OS (יעד {DAILY_TARGET}). "
                        "שי ממשיך לחפש עד 17:00. ליד חם = מי שענה למייל, בלוח לידים."
                    )
            except Exception:
                _log("morning ping failed")

    if now.hour >= HUNT_END_HOUR:
        state = _state()
        if state.get("short_on") != day:
            state["short_on"] = day
            state["research_done"] = day
            _save_state(state)
            try:
                notify_or(
                    f"יום העבודה נגמר.\n\nיש {n} טיוטות לאישור ב-Beo OS — היעד הוא {DAILY_TARGET}. "
                    "אפשר להריץ שוב מהלוח."
                )
            except Exception:
                _log("shortfall notify failed")
        return

    state = _state()
    if state.get("research_day") != day:
        state["research_wave"] = 0
        state["research_day"] = day
        _save_state(state)
    last = int(state.get("research_last_ts") or 0)
    gap = 90 if now.hour < READY_BY_HOUR else 8 * 60
    if last and (time.time() - last) < gap and state.get("research_on") == day:
        return
    start_wave = int(state.get("research_wave") or 0)
    state["research_on"] = day
    state["research_last_ts"] = int(time.time())
    if "research_done" in state and state.get("research_done") == day:
        state["research_done"] = ""
    _save_state(state)
    _log(f"run_daily start wave={start_wave} hour={now.hour}")
    try:
        result = run_daily(target=DAILY_TARGET, start_wave=start_wave)
        _log(f"run_daily {result.get('message') or 'done'}")
    except Exception as exc:
        _log(f"run_daily failed {type(exc).__name__}")
        result = {}
    n = pending_today_count()
    state = _state()
    state["research_wave"] = int(result.get("next_wave") or (start_wave + 1))
    if n >= DAILY_TARGET:
        state["research_done"] = day
        _save_state(state)
        notify_ten_ready()
    else:
        _save_state(state)
        _log(f"still short {n}/{DAILY_TARGET} — will hunt again")


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
