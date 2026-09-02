"""Johnny local state: power, pending confirms, chat, actions log."""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
HOME = REPO / "agents" / "johnny-beo" / "home"
POWER = HOME / "power.json"
PENDING = HOME / "pending.json"
CHAT = HOME / "chat.json"
ACTIONS = HOME / "actions.json"
OFFSET = HOME / "offset.json"
MEMORY = HOME / "memory.json"
LOCK = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def johnny_is_on() -> bool:
    if not POWER.is_file():
        return True
    return bool(_read(POWER).get("on", True))


def set_johnny_on(on: bool) -> None:
    _write(POWER, {"on": bool(on)})


def set_pending(kind: str, payload: dict[str, Any], summary: str) -> str:
    item_id = str(uuid.uuid4())[:8]
    with LOCK:
        _write(
            PENDING,
            {
                "id": item_id,
                "kind": kind,
                "payload": payload,
                "summary": summary,
                "created_at": _now(),
            },
        )
    return item_id


def get_pending() -> dict[str, Any] | None:
    data = _read(PENDING)
    if data.get("id"):
        return data
    return None


def clear_pending() -> None:
    if PENDING.is_file():
        try:
            PENDING.unlink()
        except OSError:
            pass


def remember(question: str, answer: str) -> None:
    data = _read(CHAT)
    turns = data.get("turns") if isinstance(data.get("turns"), list) else []
    turns.append({"q": (question or "")[:2000], "a": (answer or "")[:2500]})
    _write(CHAT, {"turns": turns[-60:]})


def history() -> list[dict[str, str]]:
    data = _read(CHAT)
    turns = data.get("turns") if isinstance(data.get("turns"), list) else []
    out: list[dict[str, str]] = []
    for turn in turns[-40:]:
        if isinstance(turn, dict) and turn.get("q") and turn.get("a"):
            out.append({"q": str(turn["q"]), "a": str(turn["a"])})
    return out


def log_action(kind: str, detail: str) -> None:
    data = _read(ACTIONS)
    items = data.get("items") if isinstance(data.get("items"), list) else []
    items.append({"at": _now(), "kind": kind, "detail": detail[:400]})
    _write(ACTIONS, {"items": items[-80:]})


def recent_actions(limit: int = 12) -> list[dict[str, Any]]:
    data = _read(ACTIONS)
    items = data.get("items") if isinstance(data.get("items"), list) else []
    return list(reversed(items[-limit:]))


def offset() -> int:
    try:
        return int(_read(OFFSET).get("offset") or 0)
    except (TypeError, ValueError):
        return 0


def set_offset(value: int) -> None:
    _write(OFFSET, {"offset": int(value)})


def env_flag(name: str) -> bool:
    return bool((os.environ.get(name) or "").strip())


def memory_facts() -> list[str]:
    data = _read(MEMORY)
    facts = data.get("facts") if isinstance(data.get("facts"), list) else []
    return [str(x).strip()[:240] for x in facts if str(x).strip()][:40]


def add_memory(fact: str) -> dict[str, Any]:
    text = (fact or "").strip()
    if not text:
        return {"ok": False, "error": "אין מה לזכור"}
    facts = memory_facts()
    if text not in facts:
        facts.append(text[:240])
    with LOCK:
        _write(MEMORY, {"facts": facts[-40:], "updated_at": _now()})
    return {"ok": True, "facts": facts[-40:]}


def rivhit_connected() -> bool:
    return bool((os.environ.get("RIVHIT_API_KEY") or os.environ.get("RIVHIT_TOKEN") or "").strip())
