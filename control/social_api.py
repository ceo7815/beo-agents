"""HTTP handlers for Beo Social. Used by Beo OS. Never publishes without scheduled+approved."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qs, urlparse

from social_store import (
    STATUS_HE,
    add_inbox,
    approve_post,
    complete_publish,
    create_post,
    get_post,
    list_inbox,
    list_posts,
    mark_inbox,
    overview,
    save_settings,
    skip_post,
    update_post,
)


def _read_json(raw: bytes) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _assets(row: dict[str, Any]) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    if row.get("image_url"):
        assets.append(
            {
                "kind": "feed",
                "signed_url": row["image_url"],
                "mime_type": "image/jpeg",
                "file_name": "feed.jpg",
            }
        )
    if row.get("story_image_url"):
        assets.append(
            {
                "kind": "story",
                "signed_url": row["story_image_url"],
                "mime_type": "image/jpeg",
                "file_name": "story.jpg",
            }
        )
    return assets


def publish_now(post_id: str) -> dict[str, Any]:
    from social_meta import publish_post
    from social_store import append_run

    row = get_post(post_id)
    if not row:
        return {"ok": False, "error": "פוסט לא נמצא"}
    try:
        result = publish_post(
            post_id=post_id,
            caption=str(row.get("caption") or ""),
            caption_ig=str(row.get("caption_ig") or ""),
            caption_fb=str(row.get("caption_fb") or ""),
            platforms=list(row.get("platforms") or ["facebook_page", "instagram"]),
            formats=list(row.get("formats") or ["feed"]),
            assets=_assets(row),
        )
    except Exception as exc:
        complete_publish(post_id, {}, error=str(exc)[:400])
        append_run("publish_fail", str(exc)[:200])
        return {"ok": False, "error": str(exc)[:400]}
    err = "; ".join(result.get("errors") or [])
    complete_publish(post_id, result.get("meta_ids") or {}, error=err)
    append_run("publish", f"{post_id} dry_run={result.get('dry_run')}")
    if err and not any(k for k in (result.get("meta_ids") or {}) if k != "dry_run"):
        return {"ok": False, "error": err}
    return {"ok": True, "item": get_post(post_id), "dry_run": result.get("dry_run")}


def refresh_inbox() -> dict[str, Any]:
    from social_meta import fetch_comments, fetch_insights

    n = 0
    for row in list_posts():
        if row.get("status") != "published":
            continue
        meta = row.get("meta_ids") or {}
        if not isinstance(meta, dict):
            continue
        comments = fetch_comments(meta, str(row.get("id") or ""))
        n += add_inbox(comments)
        metrics = fetch_insights(meta)
        update_post(str(row.get("id") or ""), {"analytics": metrics})
    return {"ok": True, "added": n}


def handle_get(path: str) -> tuple[int, dict[str, Any]]:
    parsed = urlparse(path)
    clean = parsed.path.rstrip("/") or "/"
    qs = parse_qs(parsed.query)
    if clean == "/api/social/overview":
        return 200, overview()
    if clean == "/api/social/posts":
        year = int((qs.get("year") or [0])[0] or 0)
        month = int((qs.get("month") or [0])[0] or 0)
        return 200, {
            "ok": True,
            "items": list_posts(year=year or None, month=month or None),
            "status_labels": STATUS_HE,
        }
    if clean == "/api/social/inbox":
        return 200, {"ok": True, "items": list_inbox()}
    if clean.startswith("/api/social/posts/"):
        post_id = clean.split("/")[-1]
        row = get_post(post_id)
        if not row:
            return 404, {"ok": False, "error": "פוסט לא נמצא"}
        return 200, {"ok": True, "item": row}
    return 404, {"ok": False, "error": "not found"}


def handle_post(path: str, raw: bytes) -> tuple[int, dict[str, Any]]:
    clean = urlparse(path).path.rstrip("/")
    body = _read_json(raw)
    if clean == "/api/social/generate-image":
        from social_images import generate_still

        fmt = str(body.get("format") or "feed").strip().lower()
        if fmt not in {"feed", "story", "feed_4x5"}:
            fmt = "feed"
        result = generate_still(
            headline=str(body.get("headline") or ""),
            sub=str(body.get("sub") or ""),
            fmt=fmt,
        )
        return (200, result) if result.get("ok") else (400, result)
    if clean == "/api/social/compose-caption":
        from social_caption import compose_from_idea, with_hashtags

        idea = str(body.get("idea") or body.get("user_notes") or "").strip()
        include = bool(body.get("include_hashtags"))
        result = compose_from_idea(idea=idea, date=str(body.get("date") or ""))
        if not result.get("ok"):
            return 400, result
        body_text = str(result.get("body") or "")
        ig = with_hashtags(body_text, include)
        return 200, {
            "ok": True,
            "body": body_text,
            "caption_ig": ig,
            "caption_fb": body_text,
            "hashtags": result.get("hashtags") or [],
        }
    if clean == "/api/social/posts":
        item = create_post(body)
        return 200, {"ok": True, "item": item}
    if clean == "/api/social/settings":
        return 200, {"ok": True, "settings": save_settings(body)}
    if clean == "/api/social/refresh-inbox":
        return 200, refresh_inbox()

    parts = clean.split("/")
    if len(parts) == 6 and parts[1] == "api" and parts[2] == "social" and parts[3] == "posts":
        post_id, action = parts[4], parts[5]
        row = get_post(post_id)
        if not row:
            return 404, {"ok": False, "error": "פוסט לא נמצא"}
        if action == "update":
            updated = update_post(post_id, body)
            return 200, {"ok": True, "item": updated}
        if action == "approve":
            result = approve_post(post_id, immediate=bool(body.get("immediate")))
            return (200, result) if result.get("ok") else (400, result)
        if action == "skip":
            return 200, skip_post(post_id)
        if action == "publish":
            approved = approve_post(post_id, immediate=True)
            if not approved.get("ok"):
                return 400, approved
            return 200, publish_now(post_id)
    if len(parts) == 6 and parts[1] == "api" and parts[2] == "social" and parts[3] == "inbox":
        item_id, action = parts[4], parts[5]
        if action == "read":
            return 200, {"ok": True, "item": mark_inbox(item_id, "read")}
        if action == "handled":
            return 200, {"ok": True, "item": mark_inbox(item_id, "handled")}
    return 404, {"ok": False, "error": "not found"}
