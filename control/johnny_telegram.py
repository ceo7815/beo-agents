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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from johnny_store import (
    HOME,
    clear_pending,
    get_pending,
    history,
    johnny_is_on,
    log_action,
    offset,
    remember,
    set_offset,
)
from johnny_tools import TOOLS, dispatch, execute_pending

CTX = ssl.create_default_context()
API = "https://api.openai.com/v1/chat/completions"
SOUL = Path(__file__).resolve().parents[1] / "agents" / "johnny-beo" / "SOUL.md"
CONFIRM = ("כן", "תאשר", "אשר", "יאללה", "בצע", "תנפיק", "תשלח", "ok", "yes")


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
    data = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
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
        return "אתה ג'וני, המנכ״ל הדיגיטלי של Beo Systems. עובד רק מול אור."


def _confirm_text(text: str) -> bool:
    low = (text or "").strip().lower()
    low = re.sub(r"[.!,?؟]+", "", low).strip()
    return low in CONFIRM or low in {c.lower() for c in CONFIRM}


def _openai_chat(messages: list[dict[str, Any]]) -> dict[str, Any]:
    key = _env("OPENAI_API_KEY")
    if not key:
        return {"error": "חסר OPENAI_API_KEY"}
    payload = {
        "model": _env("OPENAI_MODEL") or "gpt-5.6-luna",
        "messages": messages,
        "tools": TOOLS,
        "tool_choice": "auto",
    }
    req = urllib.request.Request(
        API,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=90, context=CTX) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")[:400]
        return {"error": err}
    except Exception as exc:
        return {"error": type(exc).__name__}


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


def _run_agent(user_text: str) -> str:
    messages: list[dict[str, Any]] = [{"role": "system", "content": _soul()}]
    for turn in history():
        messages.append({"role": "user", "content": turn["q"]})
        messages.append({"role": "assistant", "content": turn["a"]})
    messages.append({"role": "user", "content": user_text})
    for _ in range(8):
        data = _openai_chat(messages)
        if data.get("error"):
            return f"לא הצלחתי לחשוב עכשיו. {data['error'][:180]}"
        choice = ((data.get("choices") or [{}])[0]).get("message") or {}
        tool_calls = choice.get("tool_calls") or []
        if tool_calls:
            messages.append(choice)
            for call in tool_calls:
                fn = (call.get("function") or {})
                name = str(fn.get("name") or "")
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = dispatch(name, args if isinstance(args, dict) else {})
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id"),
                        "content": result,
                    }
                )
            continue
        return str(choice.get("content") or "אין לי תשובה.").strip()
    return "עצרתי אחרי כמה פעולות. תגיד מה הצעד הבא."


def _handle_text(chat_id: int, text: str, *, as_voice: bool) -> None:
    pending = get_pending()
    if pending and _confirm_text(text):
        raw = execute_pending(pending)
        clear_pending()
        try:
            parsed = json.loads(raw)
            ok = parsed.get("ok") is not False
            reply = "בוצע." if ok else str(parsed.get("error") or raw)[:800]
            if isinstance(parsed, dict) and parsed.get("id"):
                reply = f"בוצע. מזהה {parsed.get('id')}"
        except json.JSONDecodeError:
            reply = raw[:800]
        log_action("confirm", pending.get("kind") or "")
    else:
        reply = _run_agent(text)
    remember(text, reply)
    _tg("sendMessage", chat_id=chat_id, text=reply[:3900])
    if as_voice:
        audio = _speak(reply)
        if audio:
            _send_voice(chat_id, audio)


def _poll_once() -> None:
    if not johnny_is_on() or not _token():
        return
    data = _tg("getUpdates", offset=offset() + 1, timeout=20, allowed_updates=json.dumps(["message"]))
    if not data.get("ok"):
        return
    for upd in data.get("result") or []:
        upd_id = int(upd.get("update_id") or 0)
        set_offset(upd_id)
        msg = upd.get("message") or {}
        chat = msg.get("chat") or {}
        user = msg.get("from") or {}
        chat_id = int(chat.get("id") or 0)
        if not _is_allowed(str(user.get("id") or ""), chat_id):
            continue
        if not johnny_is_on():
            _tg("sendMessage", chat_id=chat_id, text="ג'וני כבוי ב-Beo OS.")
            continue
        voice = msg.get("voice") or msg.get("audio")
        if voice and voice.get("file_id"):
            blob = _tg_file(str(voice["file_id"]))
            text = _transcribe(blob or b"") if blob else ""
            if not text:
                _tg("sendMessage", chat_id=chat_id, text="לא תפסתי את ההקלטה. תכתוב?")
                continue
            _tg("sendMessage", chat_id=chat_id, text=f"שמעתי: {text[:400]}")
            _handle_text(chat_id, text, as_voice=True)
            continue
        text = str(msg.get("text") or "").strip()
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
