"""OpenAI token usage for Beo Leads. Never print secrets."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from leads_store import REPO, _env_value, _now

USAGE_PATH = REPO / "agents" / "leads-beo" / "home" / "learning" / "usage.json"
LOCK = threading.Lock()
IL = timezone(timedelta(hours=3))

KIND_HE = {
    "research": "מחקר טיוטות",
    "telegram": "טלגרם",
    "learn": "למידה",
}

# Defaults if OpenAI does not return a price. Override with env.
INPUT_USD_PER_M = 1.25
OUTPUT_USD_PER_M = 10.0


def _rates() -> tuple[float, float]:
    try:
        inp = float(_env_value("OPENAI_INPUT_USD_PER_MTOK") or INPUT_USD_PER_M)
    except ValueError:
        inp = INPUT_USD_PER_M
    try:
        out = float(_env_value("OPENAI_OUTPUT_USD_PER_MTOK") or OUTPUT_USD_PER_M)
    except ValueError:
        out = OUTPUT_USD_PER_M
    return inp, out


def _usd(prompt: int, completion: int) -> float:
    inp, out = _rates()
    return round((prompt / 1_000_000) * inp + (completion / 1_000_000) * out, 6)


def _read() -> dict[str, Any]:
    if not USAGE_PATH.is_file():
        return {"items": []}
    try:
        data = json.loads(USAGE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"items": []}
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        return {"items": []}
    return data


def _write(data: dict[str, Any]) -> None:
    USAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = USAGE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(USAGE_PATH)


def record_from_response(raw: dict[str, Any] | None, kind: str) -> None:
    if not isinstance(raw, dict):
        return
    usage = raw.get("usage") or {}
    prompt = int(usage.get("prompt_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)
    if prompt <= 0 and completion <= 0:
        return
    model = str(raw.get("model") or _env_value("OPENAI_MODEL") or "gpt-5.6-luna")
    now = datetime.now(timezone.utc).astimezone(IL)
    row = {
        "at": _now(),
        "day": now.strftime("%Y-%m-%d"),
        "month": now.strftime("%Y-%m"),
        "kind": kind,
        "model": model,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
        "usd": _usd(prompt, completion),
    }
    with LOCK:
        data = _read()
        items = data["items"]
        items.append(row)
        data["items"] = items[-4000:]
        _write(data)


def public_report() -> dict[str, Any]:
    month = datetime.now(timezone.utc).astimezone(IL).strftime("%Y-%m")
    with LOCK:
        items = [r for r in _read().get("items") or [] if r.get("month") == month]
    prompt = sum(int(r.get("prompt_tokens") or 0) for r in items)
    completion = sum(int(r.get("completion_tokens") or 0) for r in items)
    usd = round(sum(float(r.get("usd") or 0) for r in items), 4)
    days: list[dict[str, Any]] = []
    for r in reversed(items[-80:]):
        days.append(
            {
                "date": r.get("day"),
                "kind": KIND_HE.get(str(r.get("kind") or ""), str(r.get("kind") or "")),
                "tokens": int(r.get("total_tokens") or 0),
                "usd": round(float(r.get("usd") or 0), 4),
            }
        )
    return {
        "ok": True,
        "month": month,
        "model": _env_value("OPENAI_MODEL") or "gpt-5.6-luna",
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
        "usd": usd,
        "days": days,
    }
