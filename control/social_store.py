"""Beo Social pipeline. Beo OS is the source of truth. Never Liba data."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
STATE_PATH = REPO / "bundled" / "social-beo" / "home" / "pipeline" / "state.json"
LOCK = threading.Lock()

IL = timezone(timedelta(hours=3))
STATUSES = (
    "draft",
    "pending_review",
    "scheduled",
    "publishing",
    "published",
    "failed",
    "skipped",
)
STATUS_HE = {
    "draft": "טיוטה",
    "pending_review": "ממתין לאישור",
    "scheduled": "מאושר / מתוזמן",
    "publishing": "מפרסם",
    "published": "פורסם",
    "failed": "נכשל",
    "skipped": "דולג",
}

DEFAULT_BRAND = {
    "name": "Beo Systems",
    "altName": "Beo",
    "primaryColor": "#5828A0",
    "secondaryColor": "#181818",
            "logoPath": "/logo-beo-os.png",
    "website": "https://beosystem.com",
    "visualLanguage": (
        "שפת Beo Systems (beosystem.com): סגול #5828A0, שחור, פחם #181818. "
        "חד, טכנולוגי, עברית מדוברת. לוגו רשמי מעגלי — לא מדבקה בפינה. "
        "קו: מבינים תוכנה. מבינים AI."
    ),
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today_il() -> str:
    return datetime.now(timezone.utc).astimezone(IL).strftime("%Y-%m-%d")


def _empty() -> dict[str, Any]:
    return {
        "updated_at": _now(),
        "settings": {
            "brand": dict(DEFAULT_BRAND),
            "tone_guidelines": (
                "עברית חדה. מוכרת בלי באזז. אינסטגרם: הוק + 3–5 האשטגים. "
                "פייסבוק: משפט-שניים, בלי האשטגים. אותו ויזואל, כותרת מותאמת לרשת."
            ),
            "forbidden_phrases": ["שמח לעזור", "להיכנס לאפליקציה", "העתק והדבק"],
            "default_publish_time": "10:00",
            "platforms": ["facebook_page", "instagram"],
            "phone": None,
            "email": "ceo@beosystem.co.il",
            "address": "החרושת 10, קריית ביאליק",
            "ctas": [
                {"label": "beosystem.com", "url": "https://beosystem.com"},
            ],
        },
        "posts": [],
        "inbox": [],
        "runs": [],
    }


def _read() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return _empty()
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty()
    if not isinstance(data, dict):
        return _empty()
    data.setdefault("posts", [])
    data.setdefault("inbox", [])
    data.setdefault("runs", [])
    data.setdefault("settings", _empty()["settings"])
    return data


def _write(data: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = _now()
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_PATH)


def settings() -> dict[str, Any]:
    with LOCK:
        return dict(_read().get("settings") or _empty()["settings"])


def save_settings(patch: dict[str, Any]) -> dict[str, Any]:
    with LOCK:
        data = _read()
        cur = data.get("settings") or _empty()["settings"]
        for key in (
            "tone_guidelines",
            "default_publish_time",
            "phone",
            "email",
            "address",
        ):
            if key in patch:
                cur[key] = patch[key]
        if "forbidden_phrases" in patch and isinstance(patch["forbidden_phrases"], list):
            cur["forbidden_phrases"] = [str(x) for x in patch["forbidden_phrases"]]
        if "platforms" in patch and isinstance(patch["platforms"], list):
            cur["platforms"] = [str(x) for x in patch["platforms"]]
        if "brand" in patch and isinstance(patch["brand"], dict):
            brand = dict(cur.get("brand") or DEFAULT_BRAND)
            brand.update({k: v for k, v in patch["brand"].items() if v is not None})
            cur["brand"] = brand
        data["settings"] = cur
        _write(data)
        return cur


def list_posts(*, year: int | None = None, month: int | None = None) -> list[dict[str, Any]]:
    with LOCK:
        posts = list(_read().get("posts") or [])
    if year and month:
        prefix = f"{year:04d}-{month:02d}-"
        posts = [p for p in posts if _il_date(p).startswith(prefix)]
    posts.sort(key=lambda p: str(p.get("scheduled_at") or ""), reverse=True)
    return posts


def _il_date(post: dict[str, Any]) -> str:
    raw = str(post.get("scheduled_at") or "")
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(IL).strftime("%Y-%m-%d")
    except ValueError:
        return raw[:10]


def get_post(post_id: str) -> dict[str, Any] | None:
    with LOCK:
        for row in _read().get("posts") or []:
            if str(row.get("id")) == post_id:
                return row
    return None


def _new_post(body: dict[str, Any]) -> dict[str, Any]:
    now = _now()
    platforms = body.get("platforms") or ["facebook_page", "instagram"]
    formats = body.get("formats") or ["feed"]
    return {
        "id": str(uuid.uuid4()),
        "scheduled_at": str(body.get("scheduled_at") or now),
        "status": str(body.get("status") or "draft"),
        "caption": str(body.get("caption") or ""),
        "caption_ig": str(body.get("caption_ig") or body.get("caption") or ""),
        "caption_fb": str(body.get("caption_fb") or body.get("caption") or ""),
        "caption_locked": bool(body.get("caption_locked") or False),
        "media_mode": str(body.get("media_mode") or "none"),
        "platforms": list(platforms),
        "formats": list(formats),
        "image_url": str(body.get("image_url") or ""),
        "story_image_url": str(body.get("story_image_url") or ""),
        "user_notes": str(body.get("user_notes") or ""),
        "image_prompt": str(body.get("image_prompt") or ""),
        "ai_suggestion": str(body.get("ai_suggestion") or ""),
        "include_hashtags": bool(body.get("include_hashtags") or False),
        "approved_at": None,
        "published_at": None,
        "meta_ids": None,
        "analytics": {},
        "error": None,
        "queue_trigger": body.get("queue_trigger"),
        "queue_status": None,
        "queue_error": None,
        "created_at": now,
        "updated_at": now,
    }


def create_post(body: dict[str, Any]) -> dict[str, Any]:
    item = _new_post(body)
    if item["status"] not in STATUSES:
        item["status"] = "draft"
    with LOCK:
        data = _read()
        data["posts"].append(item)
        _write(data)
    return item


def update_post(post_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    with LOCK:
        data = _read()
        for i, row in enumerate(data["posts"]):
            if str(row.get("id")) != post_id:
                continue
            for key in (
                "scheduled_at",
                "caption",
                "caption_ig",
                "caption_fb",
                "media_mode",
                "image_url",
                "story_image_url",
                "user_notes",
                "image_prompt",
                "ai_suggestion",
                "caption_locked",
                "error",
                "queue_trigger",
                "queue_status",
                "queue_error",
                "published_at",
                "approved_at",
            ):
                if key in patch:
                    row[key] = patch[key]
            if "platforms" in patch and isinstance(patch["platforms"], list):
                row["platforms"] = list(patch["platforms"])
            if "formats" in patch and isinstance(patch["formats"], list):
                row["formats"] = list(patch["formats"])
            if "include_hashtags" in patch:
                row["include_hashtags"] = bool(patch["include_hashtags"])
            if "meta_ids" in patch:
                row["meta_ids"] = patch["meta_ids"]
            if "analytics" in patch and isinstance(patch["analytics"], dict):
                row["analytics"] = patch["analytics"]
            if "status" in patch:
                status = str(patch["status"])
                if status in STATUSES:
                    row["status"] = status
            row["updated_at"] = _now()
            data["posts"][i] = row
            _write(data)
            return row
    return {}


def approve_post(post_id: str, *, immediate: bool = False) -> dict[str, Any]:
    row = get_post(post_id)
    if not row:
        return {"ok": False, "error": "פוסט לא נמצא"}
    if row.get("status") not in {"draft", "pending_review", "failed", "scheduled"}:
        return {"ok": False, "error": "אי אפשר לאשר את הסטטוס הזה"}
    patch: dict[str, Any] = {
        "status": "scheduled",
        "approved_at": _now(),
        "queue_status": "pending",
        "queue_error": None,
        "error": None,
        "queue_trigger": "immediate" if immediate else "scheduled",
    }
    if immediate:
        patch["scheduled_at"] = _now()
    updated = update_post(post_id, patch)
    return {"ok": True, "item": updated}


def skip_post(post_id: str) -> dict[str, Any]:
    updated = update_post(post_id, {"status": "skipped", "queue_status": None})
    if not updated:
        return {"ok": False, "error": "פוסט לא נמצא"}
    return {"ok": True, "item": updated}


def claim_due() -> dict[str, Any] | None:
    now = datetime.now(timezone.utc)
    with LOCK:
        data = _read()
        for i, row in enumerate(data["posts"]):
            if row.get("status") != "scheduled":
                continue
            if row.get("queue_status") not in {None, "pending"}:
                continue
            raw = str(row.get("scheduled_at") or "")
            try:
                stamp = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
                due = datetime.fromisoformat(stamp)
                if due.tzinfo is None:
                    due = due.replace(tzinfo=timezone.utc)
            except ValueError:
                due = now
            if due > now:
                continue
            row["status"] = "publishing"
            row["queue_status"] = "claimed"
            row["updated_at"] = _now()
            data["posts"][i] = row
            _write(data)
            return dict(row)
    return None


def complete_publish(post_id: str, meta_ids: dict[str, Any], *, error: str = "") -> dict[str, Any]:
    patch: dict[str, Any] = {
        "meta_ids": meta_ids,
        "published_at": _now(),
        "status": "published" if not error else "failed",
        "queue_status": "done" if not error else "failed",
        "queue_error": error or None,
        "error": error or None,
    }
    return update_post(post_id, patch)


def add_inbox(items: list[dict[str, Any]]) -> int:
    added = 0
    with LOCK:
        data = _read()
        seen = {str(x.get("external_id") or "") for x in data.get("inbox") or []}
        for item in items:
            ext = str(item.get("external_id") or "")
            if not ext or ext in seen:
                continue
            row = {
                "id": str(uuid.uuid4()),
                "platform": item.get("platform") or "instagram",
                "external_id": ext,
                "post_id": item.get("post_id"),
                "author_name": item.get("author_name"),
                "author_handle": item.get("author_handle"),
                "body": item.get("body") or "",
                "received_at": item.get("received_at") or _now(),
                "status": "new",
            }
            data["inbox"].append(row)
            seen.add(ext)
            added += 1
        _write(data)
    return added


def list_inbox() -> list[dict[str, Any]]:
    with LOCK:
        items = list(_read().get("inbox") or [])
    items.sort(key=lambda r: str(r.get("received_at") or ""), reverse=True)
    return items


def mark_inbox(item_id: str, status: str) -> dict[str, Any]:
    with LOCK:
        data = _read()
        for i, row in enumerate(data.get("inbox") or []):
            if str(row.get("id")) == item_id:
                row["status"] = status
                data["inbox"][i] = row
                _write(data)
                return row
    return {}


def append_run(kind: str, detail: str) -> None:
    with LOCK:
        data = _read()
        runs = data.get("runs") or []
        runs.append({"at": _now(), "kind": kind, "detail": detail[:400]})
        data["runs"] = runs[-80:]
        _write(data)


def overview() -> dict[str, Any]:
    day = today_il()
    posts = list_posts()
    def count(status: str, today: bool = False) -> int:
        n = 0
        for p in posts:
            if p.get("status") != status:
                continue
            if today and _il_date(p) != day:
                continue
            n += 1
        return n

    from social_meta import is_dry_run, ig_user_id, page_id, page_token

    return {
        "ok": True,
        "date": day,
        "pending_review": count("pending_review"),
        "scheduled": count("scheduled"),
        "published": count("published"),
        "failed": count("failed"),
        "inbox_new": sum(1 for x in list_inbox() if x.get("status") == "new"),
        "meta_connected": bool(page_id() and page_token()),
        "instagram_connected": bool(ig_user_id() and page_token()),
        "dry_run": is_dry_run(),
        "settings": settings(),
        "status_labels": STATUS_HE,
    }


def board_brief() -> str:
    ov = overview()
    posts = list_posts()[:12]
    lines = [
        f"תאריך: {ov['date']}",
        f"ממתינים לאישור: {ov['pending_review']}",
        f"מתוזמנים: {ov['scheduled']}",
        f"פורסמו: {ov['published']}",
        f"נכשלו: {ov['failed']}",
        f"תגובות חדשות: {ov['inbox_new']}",
        f"Meta: {'מחובר' if ov['meta_connected'] else 'ממתין לטוקנים'} · dry_run={ov['dry_run']}",
        "",
        "פוסטים אחרונים:",
    ]
    if not posts:
        lines.append("אין פוסטים ביומן.")
    for p in posts:
        lines.append(
            f"- {STATUS_HE.get(str(p.get('status')), p.get('status'))} · "
            f"{p.get('scheduled_at')} · {(p.get('caption_ig') or p.get('caption') or '')[:80]}"
        )
    return "\n".join(lines)
