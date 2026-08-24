"""Telegram Q&A + push alerts for Beo Leads. Read-only. Never sends mail."""

from __future__ import annotations

import json
import os
import re
import ssl
import threading
import time
from contextlib import contextmanager
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from leads_brief import briefing, end_of_day, pack_for_chat, wants_identity
from leads_learn import VERTICAL_HE
from leads_store import _env_value, REPO, pending_today_count, pipeline, today_il
from power import leads_is_on

CTX = ssl.create_default_context()
HOME = REPO / "agents" / "leads-beo" / "home" / "telegram"
OFFSET_PATH = HOME / "offset.json"
STATE_PATH = HOME / "notify.json"
CHAT_PATH = HOME / "chat.json"
LOCK_PATH = HOME / "poller.lock"
SEEN_PATH = HOME / "seen.json"
API = "https://api.openai.com/v1/chat/completions"
IL = timezone(timedelta(hours=3))

PERSONA = (
    "אתה שי | Beo Leads. עובד של אור, מנכ״ל Beo Systems.\n"
    "כל תור מגיע אליך כל הדאטה של הסוכן כפי שהוא ב-Beo OS: "
    "כל החברות, הטיוטות, הציונים, הדילוגים, הלמידה והכללים. "
    "תתייחס לזה כמו ChatGPT עם הקבצים פתוחים — אתה מבין שאלה חופשית, "
    "מוצא את מה שרלוונטי בדאטה, ועונה כמו בן אדם חכם.\n\n"
    "Beo OS הוא מרכז השליטה (לוח Beo Leads). טלגרם זה שיחה. "
    "אסור להגיד 'אור OS'. תמיד Beo OS. "
    "אתה לא שולח, לא מאשר, לא דוחה, לא משכתב מכאן.\n\n"
    "איך אתה מדבר: עברית מדוברת, חם, חד, ברור. "
    "אורך לפי השאלה — משפט-שניים ל'מה קורה', הסבר מלא ל'למה פנינו לגאיה' "
    "כולל מה כתבנו אם זה בתיק. "
    "בלי מקפים ובלי 'כרגע:' אלא אם ביקשו רשימה. "
    "רק מה שיש בקבצים. אין — תגיד שאין, בלי להמציא."
)

REFUSE = (
    "זה קורה רק ב-Beo OS, לא כאן.\n"
    "בטלגרם אני רק מעדכן ועונה על שאלות — בלי לשלוח, בלי לאשר, בלי לדחות."
)

ACTION_HINTS = (
    "תשלח",
    "שלח מייל",
    "שלח ל",
    "תאשר",
    "לאשר את",
    "תדחה",
    "לדחות",
    "תמחק",
    "תריץ",
    "מחקר יומי",
    "redraft",
    "follow-up",
    "follow up",
    "עדכן טיוטה",
)


def _allowed() -> set[str]:
    raw = _env_value("TELEGRAM_ALLOWED_USERS") or ""
    return {p.strip() for p in raw.split(",") if p.strip()}


def _token() -> str:
    return (_env_value("TELEGRAM_BOT_TOKEN") or "").strip()


def _or_chat() -> str | None:
    users = list(_allowed())
    return users[0] if users else None


def _tg(method: str, *, timeout: float = 40, **params: Any) -> dict[str, Any]:
    token = _token()
    if not token:
        return {"ok": False, "error": "no token"}
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = urllib.parse.urlencode(
        {k: v for k, v in params.items() if v is not None}
    ).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err = ""
        try:
            err = json.loads(exc.read().decode("utf-8")).get("description") or ""
        except Exception:
            err = str(exc.code)
        _log(f"{method} http {exc.code} {err[:180]}")
        return {"ok": False, "error": err or str(exc.code)}
    except Exception as exc:
        _log(f"{method} {type(exc).__name__}")
        return {"ok": False, "error": type(exc).__name__}


def _log(line: str) -> None:
    path = HOME / "poller.log"
    try:
        HOME.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{datetime.now(timezone.utc).isoformat()} {line}\n")
    except OSError:
        pass


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if __import__("os").name == "nt":
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x00100000, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        __import__("os").kill(pid, 0)
        return True
    except OSError:
        return False


def _acquire_poller() -> bool:
    data = _read_json(LOCK_PATH)
    old = int(data.get("pid") or 0)
    me = __import__("os").getpid()
    if old and old != me and _pid_alive(old):
        return False
    _write_json(LOCK_PATH, {"pid": me})
    return True


def _seen_ids() -> set[int]:
    raw = _read_json(SEEN_PATH).get("ids") or []
    out: set[int] = set()
    for item in raw:
        try:
            out.add(int(item))
        except (TypeError, ValueError):
            continue
    return out


def _mark_seen(update_id: int) -> bool:
    """Return False if this update was already handled."""
    seen = _seen_ids()
    if update_id in seen:
        return False
    ids = list(seen)[-80:] + [update_id]
    _write_json(SEEN_PATH, {"ids": ids[-120:]})
    return True


def _state() -> dict[str, Any]:
    data = _read_json(STATE_PATH)
    data.setdefault("replied_ids", [])
    return data


def _save_state(data: dict[str, Any]) -> None:
    _write_json(STATE_PATH, data)


def _chunks(text: str, limit: int = 3900) -> list[str]:
    text = (text or "").strip()
    if len(text) <= limit:
        return [text] if text else []
    parts: list[str] = []
    rest = text
    while rest:
        if len(rest) <= limit:
            parts.append(rest)
            break
        cut = rest.rfind("\n\n", 0, limit)
        if cut < 200:
            cut = rest.rfind("\n", 0, limit)
        if cut < 200:
            cut = limit
        parts.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    return [p for p in parts if p]


def send_typing(chat_id: int | str) -> None:
    _tg("sendChatAction", timeout=8, chat_id=str(chat_id), action="typing")


@contextmanager
def _with_typing(chat_id: int | str):
    stop = threading.Event()

    def pulse() -> None:
        send_typing(chat_id)
        while not stop.wait(4.0):
            send_typing(chat_id)

    thread = threading.Thread(target=pulse, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()


def send_message(chat_id: int | str, text: str) -> None:
    for piece in _chunks(text):
        _tg("sendMessage", chat_id=str(chat_id), text=piece)


def notify_or(text: str) -> None:
    chat = _or_chat()
    if not _token() or not chat or not (text or "").strip():
        return
    send_message(chat, text.strip())


def _vert(row: dict[str, Any]) -> str:
    key = str(row.get("vertical_key") or "")
    return VERTICAL_HE.get(key, row.get("service") or key or "")


def notify_ten_ready() -> None:
    day = today_il()
    state = _state()
    if state.get("pending10_on") == day:
        return
    n = pending_today_count()
    if n < 10:
        return
    rows = [
        r
        for r in (pipeline("pending_approval").get("items") or [])
        if str(r.get("batch_date") or "") == day
    ]
    lines = [
        "יש 10 מיילים מוכנים לאישור ב-Beo OS.",
        "",
    ]
    for row in rows[:10]:
        lines.append(
            f"• {row.get('company')} · ציון {row.get('score')} · {_vert(row)}"
        )
    lines += ["", "אישור ושליחה רק במערכת — לא כאן."]
    notify_or("\n".join(lines))
    state["pending10_on"] = day
    _save_state(state)


def notify_inbox_reply(row: dict[str, Any] | None, kind: str) -> None:
    if not row:
        return
    item_id = str(row.get("id") or "")
    state = _state()
    seen = [str(x) for x in (state.get("replied_ids") or [])]
    mark = f"{item_id}:{kind}"
    if mark in seen:
        return
    company = str(row.get("company") or "חברה")
    email = str(row.get("email") or "")
    why = str(row.get("score_why") or row.get("site_hook") or "").strip()
    preview = str(row.get("reply_preview") or "").strip()
    if kind == "human":
        lines = [
            "ענו.",
            "",
            company,
            email,
            f"ציון {row.get('score')} · {_vert(row)}",
        ]
        if why:
            lines += ["", why]
        if preview:
            lines += ["", "הם כתבו:", preview]
        lines += ["", "הליד נפתח ב-Beo OS."]
    elif kind == "not_interested":
        lines = [
            "ענו — לא מעוניינים.",
            "",
            company,
            email,
        ]
        if preview:
            lines += ["", preview]
    else:
        lines = [
            "חזר מייל אוטומטי (חופשה / מענה אוטומטי).",
            "",
            company,
            "עדיין מחכים לתשובה אנושית.",
        ]
    notify_or("\n".join(lines))
    seen.append(mark)
    state["replied_ids"] = seen[-400:]
    _save_state(state)


def eod_text() -> str:
    data = end_of_day()
    lines = [
        f"דוח סוף יום — {data['date']}",
        "",
        f"נשלחו היום: {data['sent_today']}",
        f"ענו: {data['replied_today']}",
        f"נשלחו ולא חזרו: {data['waiting']}",
        f"נסגרו בלי מענה: {data['closed']}",
        f"עדיין ממתינים לאישור: {data['pending']}",
    ]
    if data.get("sent_rows"):
        lines += ["", "נשלחו:"]
        for row in data["sent_rows"]:
            flag = "ענו" if row.get("replied") else "לא חזר"
            lines.append(f"• {row.get('company')} · {flag}")
    if data.get("replied_rows"):
        lines += ["", "מי שענו:"]
        for row in data["replied_rows"]:
            lines.append(f"• {row.get('company')} · {row.get('kind')}")
    if data.get("waiting_rows"):
        lines += ["", "מחכים לתשובה:"]
        for row in data["waiting_rows"]:
            lines.append(f"• {row.get('company')} · {row.get('email')}")
    return "\n".join(lines)


def _norm_ask(text: str) -> str:
    t = (text or "").strip().lower()
    t = t.replace("؟", "?").replace("!", "")
    t = re.sub(r"[?]+", "", t)
    return re.sub(r"\s+", " ", t).strip()


def _talk_status() -> str:
    from leads_store import overview

    ov = overview()
    n = pending_today_count()
    sent = int(ov.get("sent_today") or 0)
    replied = int(ov.get("replied") or 0)
    if n and not sent:
        return (
            f"יש לך {n} טיוטות שמחכות ב-Beo OS. "
            "עוד לא יצא מייל היום — כשתאשר, נשלח."
        )
    if sent and not replied:
        return f"יצאו היום {sent} מיילים. עדיין מחכים שיחזרו תשובות."
    if replied:
        return f"היום יצאו {sent}, וחזרו {replied} תשובות."
    if n:
        return f"יש {n} טיוטות מוכנות ב-Beo OS."
    return "שקט אצל הלידים. עוד אין טיוטות היום."


def _looks_like_action(text: str) -> bool:
    low = (text or "").strip().lower()
    return any(h in low for h in ACTION_HINTS)


def _chat_history() -> list[dict[str, str]]:
    turns = _read_json(CHAT_PATH).get("turns") or []
    if not isinstance(turns, list):
        return []
    out: list[dict[str, str]] = []
    for turn in turns[-20:]:
        if isinstance(turn, dict) and turn.get("q") and turn.get("a"):
            out.append({"q": str(turn["q"])[:2000], "a": str(turn["a"])[:2500]})
    return out


def _remember(question: str, answer: str) -> None:
    turns = _chat_history()
    turns.append({"q": (question or "")[:2000], "a": (answer or "")[:2500]})
    _write_json(CHAT_PATH, {"turns": turns[-20:]})


def _llm_answer(question: str) -> str:
    key = _env_value("OPENAI_API_KEY")
    if not key:
        return "אין לי חיבור למודל עכשיו."
    pack = pack_for_chat(question)
    history = _chat_history()
    identity = wants_identity(question) or pack.get("answer_focus") == "identity"
    data_json = json.dumps(pack, ensure_ascii=False)
    if len(data_json) > 140000:
        data_json = data_json[:140000]
    messages: list[dict[str, str]] = [{"role": "system", "content": PERSONA}]
    for turn in history:
        messages.append({"role": "user", "content": turn["q"]})
        messages.append({"role": "assistant", "content": turn["a"]})
    messages.append(
        {
            "role": "user",
            "content": (
                "זה כל הדאטה של סוכן Beo Leads כפי שהוא עכשיו ב-Beo OS. "
                "קבצים פתוחים: כל התיקים, הטיוטות, הלמידה והפלייבוק. "
                "ענה רק מתוך זה.\n\n"
                + data_json
            ),
        }
    )
    ask = (question or "").strip()
    if identity:
        ask = (
            "השאלה על מי אתה. ענה מי אתה ומה התפקיד. "
            "אל תדביק רשימת טיוטות אלא אם ביקשו.\n\n"
            + ask
        )
    messages.append({"role": "user", "content": ask})
    payload = {
        "model": _env_value("OPENAI_MODEL") or "gpt-5.6-luna",
        "max_completion_tokens": 1800,
        "messages": messages,
    }
    req = urllib.request.Request(
        API,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120, context=CTX) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        text = str(raw["choices"][0]["message"]["content"] or "").strip()
        return text or "אין לי תשובה ברורה על זה."
    except urllib.error.HTTPError as exc:
        _log(f"llm http {exc.code}")
        return "רגע, נתקעתי. תשאל שוב."
    except Exception as exc:
        _log(f"llm {type(exc).__name__}")
        return "רגע, נתקעתי. תשאל שוב."


def handle_text(chat_id: int, user_id: str, text: str) -> None:
    allowed = _allowed()
    if allowed and user_id not in allowed:
        return
    msg = (text or "").strip()
    if not msg:
        return
    low = _norm_ask(msg)
    if low in {"/start", "start"}:
        send_message(
            chat_id,
            "היי אור, כאן שי. יש לי את כל לוח Beo Leads מ-Beo OS — "
            "תשאל אותי חופשי כמו ב-ChatGPT. על כל חברה, טיוטה, ציון, למה פנינו, "
            "או מה קורה היום.",
        )
        return
    if low in {"/today", "היום", "מה היום", "סיכום"}:
        send_message(chat_id, _today_text())
        return
    if low in {"/report", "דוח", "סוף יום"}:
        send_message(chat_id, eod_text())
        return
    if low in {"/help", "עזרה"}:
        send_message(
            chat_id,
            "שאל כמו עובד:\n"
            "למי שלחת היום?\n"
            "מה עושה ח. כהן?\n"
            "מי ענה ומי לא?\n"
            "למה פנינו לגאיה?\n"
            "איזה תחום החודש הביא תשובות?\n\n"
            "אני לא שולח מיילים מכאן.",
        )
        return
    if _looks_like_action(msg):
        send_message(chat_id, REFUSE)
        return
    with _with_typing(chat_id):
        answer = _llm_answer(msg)
    _remember(msg, answer)
    send_message(chat_id, answer)


def _today_text() -> str:
    pack = briefing()
    ov = pack.get("overview") or {}
    pending = pack.get("pending_all") or []
    sent = pack.get("today_sent") or []
    waiting = pack.get("waiting_for_reply") or []
    replied = pack.get("all_replied") or []
    lines = [
        f"סיכום — {pack.get('today')}",
        "",
        f"מוכנים לאישור: {ov.get('pending_approval') or 0}",
        f"נשלחו היום: {ov.get('sent_today') or 0}",
        f"מחכים לתשובה: {len(waiting)}",
        f"ענו: {len(replied)}",
        f"לא חזרו (נסגרו): {ov.get('closed_no_reply') or 0}",
    ]
    if pending:
        lines += ["", "טיוטות:"]
        for row in pending[:10]:
            lines.append(f"• {row.get('company')} · {row.get('score')} · {row.get('vertical_he')}")
    if sent:
        lines += ["", "נשלחו היום:"]
        for row in sent[:10]:
            lines.append(f"• {row.get('company')} · {row.get('email_subject')}")
    if replied:
        lines += ["", "ענו:"]
        for row in replied[:10]:
            lines.append(f"• {row.get('company')} · {row.get('reply_kind') or 'תשובה'}")
    return "\n".join(lines)


def _il_now() -> datetime:
    return datetime.now(timezone.utc).astimezone(IL)


def _scheduler_enabled() -> bool:
    """Only the server (Docker binds 0.0.0.0) sends 10:00 pings."""
    host = (os.environ.get("BEO_CONTROL_HOST") or "127.0.0.1").strip()
    return host in {"0.0.0.0", "::"}


def _il_workday(now: datetime) -> bool:
    # Israel work week: Sunday–Thursday.
    return now.weekday() in {6, 0, 1, 2, 3}


def _maybe_schedule() -> None:
    if not _token() or not _or_chat() or not _scheduler_enabled():
        return
    now = _il_now()
    day = today_il()
    if pending_today_count() >= 10:
        notify_ten_ready()

    state = _state()
    if now.hour == 10 and state.get("morning_on") != day:
        n = pending_today_count()
        already = state.get("pending10_on") == day
        researching = (
            state.get("research_on") == day and state.get("research_done") != day
        )
        if already:
            pass
        elif researching:
            pass
        elif n >= 10:
            notify_ten_ready()
        elif n > 0:
            notify_or(
                f"בוקר.\n\nיש {n} טיוטות מוכנות היום (יעד 10).\n"
                "אישור ושליחה רק ב-Beo OS."
            )
        else:
            notify_or(
                "בוקר.\n\nאין טיוטות מוכנות היום.\n"
                "אפשר להריץ מחקר יומי מלוח Beo Leads."
            )
        state = _state()
        state["morning_on"] = day
        _save_state(state)
    state = _state()
    if now.hour >= 17 and now.hour < 20 and state.get("eod_on") != day:
        notify_or(eod_text())
        state = _state()
        state["eod_on"] = day
        _save_state(state)


def _inbox_loop() -> None:
    while True:
        time.sleep(90)
        try:
            from gmail_client import token_present
            from leads_api import ingest_replies

            if token_present() and leads_is_on():
                ingest_replies()
        except Exception:
            _log("inbox scan failed")


def _loop() -> None:
    commands_set = False
    greeted = False
    offset = int(_read_json(OFFSET_PATH).get("offset") or 0)
    while True:
        token = _token()
        if not token:
            time.sleep(8)
            continue
        if not leads_is_on():
            time.sleep(3)
            continue
        if not commands_set:
            _tg("deleteWebhook")
            _tg(
                "setMyCommands",
                commands=json.dumps(
                    [
                        {"command": "today", "description": "סיכום היום"},
                        {"command": "report", "description": "דוח סוף יום"},
                        {"command": "help", "description": "מה אפשר לשאול"},
                    ]
                ),
            )
            commands_set = True
        if not greeted:
            greeted = True
        _maybe_schedule()
        data = _tg("getUpdates", offset=str(offset), timeout="20")
        if not data.get("ok"):
            _log(f"getUpdates fail {data.get('error')}")
            time.sleep(2)
            continue
        for upd in data.get("result") or []:
            uid = int(upd.get("update_id") or 0)
            offset = uid + 1
            _write_json(OFFSET_PATH, {"offset": offset})
            msg = upd.get("message") or upd.get("edited_message") or {}
            text = str(msg.get("text") or "")
            chat = msg.get("chat") or {}
            user = msg.get("from") or {}
            chat_id = chat.get("id")
            user_id = str(user.get("id") or "")
            if chat_id is None or not text:
                continue
            try:
                handle_text(int(chat_id), user_id, text)
            except Exception as exc:
                _log(f"handle {type(exc).__name__}")
                try:
                    send_message(int(chat_id), "רגע, נתקעתי. תשאל שוב.")
                except Exception:
                    pass


def start_telegram_thread() -> None:
    me = __import__("os").getpid()
    _write_json(LOCK_PATH, {"pid": me})
    thread = threading.Thread(target=_loop, name="leads-telegram", daemon=True)
    thread.start()
    inbox = threading.Thread(target=_inbox_loop, name="leads-inbox", daemon=True)
    inbox.start()
    _log(f"poller start pid={me}")
