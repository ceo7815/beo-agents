"""Johnny Telegram — conversation, tools, voice in/out. Only אור."""

from __future__ import annotations

import io
import json
import os
import re
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from johnny_store import (
    HOME,
    clear_pending,
    get_pending,
    history,
    johnny_is_on,
    log_action,
    memory_facts,
    offset,
    remember,
    rivhit_connected,
    set_offset,
)
from johnny_google import connected as google_connected
from johnny_os import humanize_os_error, os_connected
from johnny_tools import TOOLS, dispatch, execute_pending

CTX = ssl.create_default_context()
API = "https://api.openai.com/v1/responses"
SOUL = Path(__file__).resolve().parents[1] / "agents" / "johnny-beo" / "SOUL.md"
USER = Path(__file__).resolve().parents[1] / "agents" / "johnny-beo" / "USER.md"
CONFIRM = ("כן", "תאשר", "אשר", "יאללה", "בצע", "תנפיק", "תשלח", "ok", "yes")
DENY = ("לא", "בטל", "cancel", "no", "סור", "עזוב")
IL = timezone(timedelta(hours=3))
WEEKDAYS = ("שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון")


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _token() -> str:
    return _env("JOHNNY_TELEGRAM_BOT_TOKEN")


def _allowed() -> set[str]:
    raw = _env("TELEGRAM_ALLOWED_USERS")
    out: set[str] = set()
    for part in raw.split(","):
        p = part.strip().strip('"').strip("'")
        if p:
            out.add(p)
            digits = "".join(c for c in p if c.isdigit())
            if digits:
                out.add(digits)
    return out


def _is_allowed(user_id: str, chat_id: int | None = None) -> bool:
    allowed = _allowed()
    if not allowed:
        return True
    uid = str(user_id or "").strip()
    cid = str(chat_id or "").strip()
    return uid in allowed or cid in allowed or "".join(c for c in uid if c.isdigit()) in allowed


def _log(line: str) -> None:
    path = HOME / "poller.log"
    try:
        HOME.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{datetime.now(timezone.utc).isoformat()} {line}\n")
    except OSError:
        pass


def _tg(method: str, **params: Any) -> dict[str, Any]:
    token = _token()
    if not token:
        return {"ok": False, "error": "no token"}
    url = f"https://api.telegram.org/bot{token}/{method}"
    payload = {k: v for k, v in params.items() if v is not None}
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=40, context=CTX) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        _log(f"{method} {type(exc).__name__}")
        return {"ok": False, "error": type(exc).__name__}


def _tg_file(file_id: str) -> bytes | None:
    meta = _tg("getFile", file_id=file_id)
    path = ((meta.get("result") or {}) if meta.get("ok") else {}).get("file_path")
    if not path:
        return None
    url = f"https://api.telegram.org/file/bot{_token()}/{path}"
    try:
        with urllib.request.urlopen(url, timeout=60, context=CTX) as resp:
            return resp.read()
    except Exception:
        return None


def _soul() -> str:
    try:
        return SOUL.read_text(encoding="utf-8")
    except OSError:
        return "אתה ג'וני. עובד של אור ב-Beo Systems. מדברים רק בטלגרם, על הכל, כמו אדם."


def _user() -> str:
    try:
        return USER.read_text(encoding="utf-8")
    except OSError:
        return "אור, מנכ״ל Beo Systems."


def _now_il() -> str:
    now = datetime.now(timezone.utc).astimezone(IL)
    return f"{WEEKDAYS[now.weekday()]} {now.strftime('%Y-%m-%d %H:%M')} שעון ישראל"


def _live_card() -> str:
    g = google_connected()
    pending = get_pending()
    facts = memory_facts()
    lines = [
        f"עכשיו: {_now_il()}",
        "חיבורים (אל תקרא את זה לאור אלא אם שואל או אם משהו חסר לפעולה):",
        f"- Beo OS: {'מחובר' if os_connected() else 'לא מחובר — BOT_API_KEY + JOHNNY_ACTOR_USER_ID ב-xCloud'}",
        f"- ceo@ / יומן Google: {'מחובר' if g.get('gmail') else 'לא מחובר — CEO_GMAIL_REFRESH_TOKEN'}",
        f"- ריווחית אונליין: {'מחובר' if rivhit_connected() else 'עתידי — לא מחובר'}",
        "המשרד הוא הטלגרם בלבד. תענה על הכל כמו עובד חכם. אל תציע תפריט. אל תזכיר כלים.",
    ]
    if pending:
        lines.append(f"- ממתין לאישור של אור בטלגרם (כפתורים): {pending.get('summary')}")
    if facts:
        lines.append("מה שאתה זוכר על אור/Beo:")
        lines.extend(f"- {f}" for f in facts[-12:])
    return "\n".join(lines)


def _system() -> str:
    return _soul() + "\n\n" + _user() + "\n\n" + _live_card()


def _confirm_text(text: str) -> bool:
    low = (text or "").strip().lower()
    low = re.sub(r"[.!,?؟]+", "", low).strip()
    return low in CONFIRM or low in {c.lower() for c in CONFIRM}


def _deny_text(text: str) -> bool:
    low = (text or "").strip().lower()
    low = re.sub(r"[.!,?؟]+", "", low).strip()
    return low in DENY or low in {c.lower() for c in DENY}


ENTITY_HE = {
    "tasks": "משימה",
    "leads": "ליד",
    "clients": "לקוח",
    "projects": "פרויקט",
    "meetings": "פגישה",
    "campaigns": "קמפיין",
    "suppliers": "ספק",
    "deals": "עסקה",
    "docs": "מסמך",
    "invoices": "חשבונית",
    "hostingrecords": "רשומת אחסון",
    "users": "משתמש",
}


def _he_date(value: str) -> str:
    raw = (value or "").strip()[:10]
    if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
        y, m, d = raw.split("-")
        return f"{int(d)}.{int(m)}.{y}"
    return (value or "").strip()


def _confirm_keyboard(pending_id: str) -> dict[str, Any]:
    pid = (pending_id or "x")[:8]
    return {
        "inline_keyboard": [
            [
                {"text": "מאשר", "callback_data": f"j:yes:{pid}"},
                {"text": "לא מאשר", "callback_data": f"j:no:{pid}"},
            ]
        ]
    }


def _pending_card(pending: dict[str, Any]) -> str:
    kind = str(pending.get("kind") or "")
    payload = pending.get("payload") if isinstance(pending.get("payload"), dict) else {}
    if kind == "os_write":
        op = str(payload.get("op") or "create")
        entity = str(payload.get("entity") or "")
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        noun = ENTITY_HE.get(entity, "רשומה")
        title = str(data.get("title") or data.get("name") or pending.get("summary") or noun)
        due = _he_date(str(data.get("dueDate") or data.get("startDate") or ""))
        verb = "עדכון" if op == "update" else "פתיחת"
        lines = [f"{verb} {noun} ב-Beo OS", "", title]
        if due:
            lines.append(f"תאריך יעד: {due}")
        lines += ["", "עדיין לא נשמר במערכת.", "אשר או בטל בכפתורים למטה."]
        return "\n".join(lines)
    if kind == "delete":
        return "\n".join(
            [
                "מחיקה מ-Beo OS",
                "",
                str(pending.get("summary") or "רשומה"),
                "",
                "זה לא בוצע עדיין.",
                "אשר או בטל בכפתורים למטה.",
            ]
        )
    if kind == "calendar":
        title = str(payload.get("title") or pending.get("summary") or "פגישה")
        when = " ".join(
            x for x in (_he_date(str(payload.get("startDate") or "")), str(payload.get("startTime") or "")) if x
        )
        meet = " עם Google Meet" if payload.get("need_meet") else ""
        return "\n".join(
            [
                f"קביעת פגישה ביומן{meet}",
                "",
                title,
                when,
                "",
                "עדיין לא נקבעה.",
                "אשר או בטל בכפתורים למטה.",
            ]
        )
    if kind == "mail":
        return "\n".join(
            [
                "שליחת מייל מ-ceo@",
                "",
                f"אל: {payload.get('to') or ''}",
                str(payload.get("subject") or ""),
                "",
                "עדיין לא נשלח.",
                "אשר או בטל בכפתורים למטה.",
            ]
        )
    if kind == "specialist":
        who = "שי" if payload.get("who") == "shay" else "עדי" if payload.get("who") == "adi" else "הסוכן"
        return "\n".join(
            [
                f"אישור ל{who}",
                "",
                str(pending.get("summary") or ""),
                "",
                "עדיין לא אושר.",
                "אשר או בטל בכפתורים למטה.",
            ]
        )
    return "\n".join(
        [
            str(pending.get("summary") or "פעולה ממתינה"),
            "",
            "עדיין לא בוצע.",
            "אשר או בטל בכפתורים למטה.",
        ]
    )


def _send_text(chat_id: int, text: str, *, confirm: bool = False) -> None:
    pending = get_pending() if confirm else None
    params: dict[str, Any] = {"chat_id": chat_id, "text": (text or "")[:3900]}
    if pending and pending.get("id"):
        params["reply_markup"] = _confirm_keyboard(str(pending.get("id")))
    _tg("sendMessage", **params)


def _strip_buttons(chat_id: int, message_id: int | None) -> None:
    if not message_id:
        return
    _tg(
        "editMessageReplyMarkup",
        chat_id=chat_id,
        message_id=message_id,
        reply_markup={"inline_keyboard": []},
    )


def _response_tools() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in TOOLS:
        fn = row.get("function") if isinstance(row.get("function"), dict) else {}
        name = str(fn.get("name") or "")
        if not name:
            continue
        out.append(
            {
                "type": "function",
                "name": name,
                "description": str(fn.get("description") or ""),
                "parameters": fn.get("parameters") or {"type": "object", "properties": {}},
            }
        )
    return out


def _openai_respond(inp: list[dict[str, Any]]) -> dict[str, Any]:
    key = _env("OPENAI_API_KEY")
    if not key:
        return {"error": "חסר OPENAI_API_KEY"}
    payload = {
        "model": _env("OPENAI_MODEL") or "gpt-5.6-luna",
        "instructions": _system(),
        "input": inp,
        "tools": _response_tools(),
        "tool_choice": "auto",
        "store": False,
    }
    req = urllib.request.Request(
        API,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120, context=CTX) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")[:400]
        return {"error": err}
    except Exception as exc:
        return {"error": type(exc).__name__}


def _output_text(data: dict[str, Any]) -> str:
    direct = str(data.get("output_text") or "").strip()
    if direct:
        return direct
    chunks: list[str] = []
    for item in data.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if isinstance(part, dict) and part.get("type") in {"output_text", "text"}:
                chunks.append(str(part.get("text") or ""))
    return "".join(chunks).strip()


def _transcribe(blob: bytes) -> str:
    try:
        import openai

        client = openai.OpenAI()
        buf = io.BytesIO(blob)
        buf.name = "voice.ogg"
        out = client.audio.transcriptions.create(model="whisper-1", file=buf, language="he")
        return str(getattr(out, "text", "") or "").strip()
    except Exception as exc:
        _log(f"whisper {exc}")
        return ""


def _speak(text: str) -> bytes | None:
    try:
        import openai

        client = openai.OpenAI()
        speech = client.audio.speech.create(
            model="tts-1",
            voice="onyx",
            input=(text or "")[:900],
        )
        return speech.content
    except Exception as exc:
        _log(f"tts {exc}")
        return None


def _send_voice(chat_id: int, audio: bytes, caption: str = "") -> None:
    token = _token()
    if not token:
        return
    boundary = "----beojohnny"
    chunks = []

    def part(name: str, value: bytes, filename: str | None = None, ctype: str | None = None) -> None:
        disp = f'name="{name}"'
        if filename:
            disp += f'; filename="{filename}"'
        header = f"--{boundary}\r\nContent-Disposition: form-data; {disp}\r\n"
        if ctype:
            header += f"Content-Type: {ctype}\r\n"
        header += "\r\n"
        chunks.append(header.encode("utf-8") + value + b"\r\n")

    part("chat_id", str(chat_id).encode("utf-8"))
    if caption:
        part("caption", caption[:900].encode("utf-8"))
    part("voice", audio, "reply.mp3", "audio/mpeg")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(chunks)
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendVoice",
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        urllib.request.urlopen(req, timeout=40, context=CTX).read()
    except Exception as exc:
        _log(f"sendVoice {exc}")


def _run_agent(user_text: str, chat_id: int | None = None) -> str:
    inp: list[dict[str, Any]] = []
    for turn in history():
        inp.append({"role": "user", "content": turn["q"]})
        inp.append({"role": "assistant", "content": turn["a"]})
    inp.append({"role": "user", "content": user_text})
    for _ in range(8):
        if chat_id:
            _tg("sendChatAction", chat_id=chat_id, action="typing")
        data = _openai_respond(inp)
        if data.get("error"):
            _log(f"openai {data['error'][:240]}")
            return "לא הצלחתי לחשוב עכשיו. תשלח שוב?"
        calls = [
            item
            for item in (data.get("output") or [])
            if isinstance(item, dict) and item.get("type") == "function_call"
        ]
        if calls:
            inp.extend([item for item in (data.get("output") or []) if isinstance(item, dict)])
            asked = False
            for call in calls:
                name = str(call.get("name") or "")
                try:
                    args = json.loads(call.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = dispatch(name, args if isinstance(args, dict) else {})
                inp.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.get("call_id"),
                        "output": result,
                    }
                )
                try:
                    parsed = json.loads(result)
                    if isinstance(parsed, dict) and parsed.get("needs_confirm"):
                        asked = True
                except json.JSONDecodeError:
                    pass
            if asked:
                pending = get_pending()
                return _pending_card(pending) if pending else "צריך אישור, אבל משהו השתבש. תשלח שוב?"
            continue
        return _output_text(data) or "אין לי תשובה."
    return "עצרתי אחרי כמה פעולות. תגיד מה הצעד הבא."


def _wants_voice(text: str, as_voice: bool) -> bool:
    if as_voice:
        return True
    t = (text or "").strip()
    return any(phrase in t for phrase in ("תענה בקול", "תגיד בקול", "ענה בקול"))


def _done_reply(pending: dict[str, Any], raw: str) -> str:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {"ok": False, "error": raw}
    if not isinstance(parsed, dict):
        parsed = {"ok": False, "error": str(parsed)}
    if parsed.get("ok") is False:
        errors = parsed.get("errors") if isinstance(parsed.get("errors"), list) else []
        err = humanize_os_error(str(parsed.get("error") or raw), errors)
        return f"לא בוצע.\n\n{err}"
    kind = str(pending.get("kind") or "")
    payload = pending.get("payload") if isinstance(pending.get("payload"), dict) else {}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    google = parsed.get("google") if isinstance(parsed.get("google"), dict) else {}
    meet = str(google.get("meet_link") or "")
    html_link = str(google.get("html_link") or "")
    title = str(data.get("title") or data.get("name") or payload.get("title") or pending.get("summary") or "")
    due = _he_date(str(data.get("dueDate") or payload.get("startDate") or ""))
    if kind == "calendar":
        lines = ["הפגישה נקבעה ביומן Google."]
        if title:
            lines.extend(["", title])
        if meet:
            lines.append(f"Meet: {meet}")
        elif html_link:
            lines.append(html_link)
        return "\n".join(lines)
    if kind == "mail":
        return f"המייל נשלח אל {payload.get('to') or 'הנמען'}."
    if kind == "invoice":
        return "ריווחית אונליין עוד לא מחוברת. לא הונפק כלום."
    if kind == "delete":
        return "נמחק מ-Beo OS."
    if kind == "specialist":
        who = "שי" if payload.get("who") == "shay" else "עדי"
        return f"אושר ל{who}."
    entity = str(payload.get("entity") or "")
    noun = ENTITY_HE.get(entity, "רשומה")
    op = str(payload.get("op") or "create")
    head = f"עדכנתי את ה{noun} ב-Beo OS." if op == "update" else f"פתחתי {noun} ב-Beo OS."
    lines = [head]
    if title:
        lines.extend(["", title])
    if due:
        lines.append(f"תאריך יעד: {due}")
    if meet:
        lines.append(f"Meet: {meet}")
    return "\n".join(lines)


def _apply_decision(chat_id: int, *, approve: bool, message_id: int | None = None) -> None:
    pending = get_pending()
    _strip_buttons(chat_id, message_id)
    if not pending:
        _send_text(chat_id, "אין פעולה ממתינה.")
        return
    if not approve:
        clear_pending()
        reply = "ביטלתי. לא נגעתי בכלום."
        remember("לא מאשר", reply)
        _send_text(chat_id, reply)
        return
    _tg("sendChatAction", chat_id=chat_id, action="typing")
    raw = execute_pending(pending)
    clear_pending()
    reply = _done_reply(pending, raw)
    log_action("confirm", pending.get("kind") or "")
    remember("מאשר", reply)
    _send_text(chat_id, reply)


def _handle_text(chat_id: int, text: str, *, as_voice: bool) -> None:
    _tg("sendChatAction", chat_id=chat_id, action="typing")
    pending = get_pending()
    if pending and _deny_text(text):
        _apply_decision(chat_id, approve=False)
        return
    if pending and _confirm_text(text):
        _apply_decision(chat_id, approve=True)
        return
    reply = _run_agent(text, chat_id)
    remember(text, reply)
    _send_text(chat_id, reply, confirm=bool(get_pending()))
    if _wants_voice(text, as_voice):
        audio = _speak(reply)
        if audio:
            _send_voice(chat_id, audio)


def _handle_callback(cq: dict[str, Any]) -> None:
    user = cq.get("from") or {}
    msg = cq.get("message") or {}
    chat = msg.get("chat") or {}
    chat_id = int(chat.get("id") or 0)
    if not _is_allowed(str(user.get("id") or ""), chat_id):
        return
    data = str(cq.get("data") or "")
    _tg("answerCallbackQuery", callback_query_id=str(cq.get("id") or ""))
    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    clicked_id = parts[2] if len(parts) > 2 else ""
    pending = get_pending()
    if pending and clicked_id and str(pending.get("id") or "")[:8] != clicked_id:
        _strip_buttons(chat_id, msg.get("message_id"))
        _send_text(chat_id, "הפעולה הזו כבר לא ממתינה.")
        return
    if action == "yes":
        _apply_decision(chat_id, approve=True, message_id=msg.get("message_id"))
        return
    if action == "no":
        _apply_decision(chat_id, approve=False, message_id=msg.get("message_id"))
        return


def _poll_once() -> None:
    if not johnny_is_on() or not _token():
        return
    data = _tg(
        "getUpdates",
        offset=offset() + 1,
        timeout=20,
        allowed_updates=["message", "callback_query"],
    )
    if not data.get("ok"):
        return
    for upd in data.get("result") or []:
        upd_id = int(upd.get("update_id") or 0)
        set_offset(upd_id)
        if upd.get("callback_query"):
            _handle_callback(upd["callback_query"] if isinstance(upd.get("callback_query"), dict) else {})
            continue
        msg = upd.get("message") or {}
        chat = msg.get("chat") or {}
        user = msg.get("from") or {}
        chat_id = int(chat.get("id") or 0)
        if not _is_allowed(str(user.get("id") or ""), chat_id):
            continue
        if not johnny_is_on():
            _send_text(chat_id, "אני כבוי עכשיו. תדליק אותי מלוח ג'וני ב-Beo OS.")
            continue
        voice = msg.get("voice") or msg.get("audio")
        if voice and voice.get("file_id"):
            blob = _tg_file(str(voice["file_id"]))
            text = _transcribe(blob or b"") if blob else ""
            if not text:
                _send_text(chat_id, "לא תפסתי את ההקלטה. תכתוב?")
                continue
            _send_text(chat_id, f"שמעתי: {text[:400]}")
            _handle_text(chat_id, text, as_voice=True)
            continue
        text = str(msg.get("text") or "").strip()
        if text in {"/start", "/help"}:
            _send_text(
                chat_id,
                "היי, אני ג'וני. תדבר חופשי — גם קול — כמו עם עובד.\n\n"
                "אם צריך לשנות משהו בחברה, אשלח בקשה עם כפתורי מאשר / לא מאשר.",
            )
            continue
        if text:
            _handle_text(chat_id, text, as_voice=False)


def _loop() -> None:
    _log("johnny poller start")
    while True:
        try:
            _poll_once()
        except Exception as exc:
            _log(f"poll {exc}")
            time.sleep(4)
        time.sleep(0.4)


def start_johnny_thread() -> None:
    if not _token():
        _log("no JOHNNY_TELEGRAM_BOT_TOKEN")
        return
    t = threading.Thread(target=_loop, name="johnny-telegram", daemon=True)
    t.start()
