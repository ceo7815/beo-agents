"""Beo OS bot-data client for Johnny. Uses the real Hub field schema."""

from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

CTX = ssl.create_default_context()

ENTITIES = (
    "tasks",
    "projects",
    "leads",
    "clients",
    "suppliers",
    "campaigns",
    "meetings",
    "invoices",
    "deals",
    "collectiontracking",
    "hostingrecords",
    "docs",
    "recurringtasktemplates",
    "users",
)


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def os_url() -> str:
    return _env("BEO_OS_URL", "https://os.beosystem.com").rstrip("/")


def os_connected() -> bool:
    return bool(_env("BOT_API_KEY") and os_url())


def actor() -> dict[str, str]:
    return {
        "userId": _env("JOHNNY_ACTOR_USER_ID"),
        "userName": _env("JOHNNY_ACTOR_NAME", "אור"),
    }


def _headers() -> dict[str, str]:
    key = _env("BOT_API_KEY")
    return {
        "Content-Type": "application/json",
        "X-Hub-Api-Key": key,
        "Authorization": f"Bearer {key}",
    }


def _request(method: str, path: str, *, query: dict[str, Any] | None = None, body: dict[str, Any] | None = None) -> dict[str, Any]:
    if not os_connected():
        return {"ok": False, "error": "חסר BEO_OS_URL או BOT_API_KEY"}
    qs = urllib.parse.urlencode({k: v for k, v in (query or {}).items() if v not in (None, "")})
    url = f"{os_url()}{path}"
    if qs:
        url = f"{url}?{qs}"
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=raw, method=method, headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=45, context=CTX) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            data = json.loads(exc.read().decode("utf-8"))
        except Exception:
            return {"ok": False, "error": f"OS HTTP {exc.code}"}
        if isinstance(data, dict):
            data.setdefault("ok", False)
            data.setdefault("error", data.get("message") or f"OS HTTP {exc.code}")
            return data
        return {"ok": False, "error": f"OS HTTP {exc.code}"}
    except Exception as exc:
        return {"ok": False, "error": f"OS לא זמין: {type(exc).__name__}"}
    return data if isinstance(data, dict) else {"ok": False, "error": "תשובה לא תקינה מ-OS"}


def os_get(entity: str, *, id: str = "", **filters: Any) -> dict[str, Any]:
    query = {"entity": entity, **filters}
    if id:
        query["id"] = id
    return _request("GET", "/api/bot-data", query=query)


def os_create(entity: str, data: dict[str, Any]) -> dict[str, Any]:
    act = actor()
    if not act["userId"] and entity not in {"invoices", "hostingrecords", "docs", "domainrecords"}:
        resolved = resolve_actor_id()
        if resolved:
            act["userId"] = resolved
    payload = {"data": data, "actor": act}
    return _request("POST", "/api/bot-data", query={"entity": entity}, body=payload)


def os_update(entity: str, id: str, data: dict[str, Any]) -> dict[str, Any]:
    return _request(
        "PATCH",
        "/api/bot-data",
        query={"entity": entity, "id": id},
        body={"data": data, "actor": actor()},
    )


def os_delete(entity: str, id: str) -> dict[str, Any]:
    return _request("DELETE", "/api/bot-data", query={"entity": entity, "id": id})


def finance(path: str, **query: Any) -> dict[str, Any]:
    return _request("GET", f"/api/finance-agent/{path}", query=query)


def issue_invoice(payload: dict[str, Any]) -> dict[str, Any]:
    return _request("POST", "/api/bot-morning/documents", body=payload)


def resolve_actor_id() -> str:
    existing = _env("JOHNNY_ACTOR_USER_ID")
    if existing:
        return existing
    email = _env("JOHNNY_ACTOR_EMAIL", "ceo@beosystem.co.il").lower()
    result = os_get("users", limit=200)
    for row in result.get("items") or []:
        if not isinstance(row, dict):
            continue
        mail = str(row.get("email") or "").strip().lower()
        name = str(row.get("name") or "")
        if mail == email or name.strip() == "אור":
            return str(row.get("id") or "")
    return ""
