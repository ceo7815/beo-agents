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


def _scrub(text: str) -> str:
    return (
        (text or "")
        .replace("Firebase/Firestore", "")
        .replace("Firebase", "")
        .replace("Firestore", "")
        .replace("firebase", "")
        .replace("firestore", "")
        .strip()
    )


def humanize_os_error(raw: str, errors: list[Any] | None = None) -> str:
    details = [str(x).strip() for x in (errors or []) if str(x).strip()]
    details = [_scrub(x) for x in details if _scrub(x)]
    if details:
        return "לא נשמר ב-Beo OS:\n" + "\n".join(details[:6])
    blob = (raw or "").lower()
    if "firebase" in blob or "firestore" in blob:
        return "לא הצלחתי לשמור ב-Beo OS."
    if "row-level security" in blob or "rls" in blob or "violates row-level" in blob:
        return "Beo OS לא נתן לכתוב למסד. ב-xCloud של os.beosystem.com המפתח SUPABASE_SERVICE_ROLE_KEY חייב להיות service_role, לא anon."
    if "internal server error" in blob:
        return "Beo OS נכשל בשמירה. בדקו ש-SUPABASE_SERVICE_ROLE_KEY באתר OS הוא service_role."
    if "validation" in blob:
        return "חסרים פרטים (כותרת, אחראי ותאריך). לא נשמר כלום."
    if "supabase_not_configured" in blob or "missing_service_role" in blob:
        return "חסר חיבור למסד הנתונים ב-Beo OS. לא נשמר כלום."
    if "unauthorized" in blob or "invalid_api_key" in blob:
        return "מפתח החיבור ל-Beo OS לא תואם. לא נשמר כלום."
    if "unknown_or_blocked" in blob:
        return "סוג הרשומה הזה עדיין לא פתוח ב-Beo OS."
    if blob.startswith("os http") or "http 5" in blob:
        return "Beo OS לא ענה עכשיו. לא נשמר כלום."
    text = _scrub((raw or "").strip())
    if not text:
        return "לא הצלחתי לשמור ב-Beo OS."
    if any(ch.isascii() and ch.isalpha() for ch in text) and " " not in text.replace("_", ""):
        return "לא הצלחתי לשמור ב-Beo OS."
    return text[:400]


def _clean_os_payload(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("ok") is True:
        return data
    err = str(data.get("error") or "")
    errors = data.get("errors") if isinstance(data.get("errors"), list) else []
    if data.get("ok") is False or err:
        data["ok"] = False
        data["error"] = humanize_os_error(err or str(data.get("message") or ""), errors)
        data.pop("message", None)
    return data


def _request(method: str, path: str, *, query: dict[str, Any] | None = None, body: dict[str, Any] | None = None) -> dict[str, Any]:
    if not os_connected():
        return {"ok": False, "error": "Beo OS לא מחובר. חסר מפתח או כתובת."}
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
            return {"ok": False, "error": humanize_os_error(f"OS HTTP {exc.code}")}
        if isinstance(data, dict):
            data["ok"] = False
            code = str(data.get("error") or "")
            detail = str(data.get("message") or data.get("hint") or "")
            if code in {"Internal Server Error", "InternalServerError"} or code.startswith("OS HTTP"):
                data["error"] = detail or code
            else:
                data.setdefault("error", detail or f"OS HTTP {exc.code}")
            return _clean_os_payload(data)
        return {"ok": False, "error": humanize_os_error(f"OS HTTP {exc.code}")}
    except Exception:
        return {"ok": False, "error": "Beo OS לא זמין ברגע זה."}
    if not isinstance(data, dict):
        return {"ok": False, "error": "תשובה לא תקינה מ-Beo OS"}
    return _clean_os_payload(data)


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
    email = _env("JOHNNY_ACTOR_EMAIL", "ceo@beosystem.com").lower()
    result = os_get("users", limit=200)
    for row in result.get("items") or []:
        if not isinstance(row, dict):
            continue
        mail = str(row.get("email") or "").strip().lower()
        name = str(row.get("name") or "")
        if mail == email or name.strip() == "אור":
            return str(row.get("id") or "")
    return ""
