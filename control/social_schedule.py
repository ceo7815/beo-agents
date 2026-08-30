"""Publish due Beo Social posts. OS approved only. Server-side."""

from __future__ import annotations

import os
import sys
import threading
import time

from social_store import append_run, claim_due, complete_publish, get_post


def _log(msg: str) -> None:
    sys.stderr.write(f"[social-schedule] {msg}\n")
    sys.stderr.flush()


def scheduler_enabled() -> bool:
    host = (os.environ.get("BEO_CONTROL_HOST") or "127.0.0.1").strip()
    return host in {"0.0.0.0", "::"}


def _assets(row: dict) -> list[dict]:
    assets: list[dict] = []
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


def _publish_claimed(row: dict) -> None:
    from social_meta import publish_post
    from social_notify import notify_published

    post_id = str(row.get("id") or "")
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
        err = "; ".join(result.get("errors") or [])
        complete_publish(post_id, result.get("meta_ids") or {}, error=err)
        append_run("publish", f"{post_id} dry={result.get('dry_run')} {err}")
        notify_published(get_post(post_id) or row, dry_run=bool(result.get("dry_run")), error=err)
        _log(f"published {post_id} dry={result.get('dry_run')}")
    except Exception as exc:
        complete_publish(post_id, {}, error=str(exc)[:400])
        append_run("publish_fail", str(exc)[:200])
        notify_published(get_post(post_id) or row, dry_run=False, error=str(exc)[:400])
        _log(f"fail {post_id}")


_last_inbox = 0.0


def _tick() -> None:
    global _last_inbox
    from social_api import refresh_inbox

    row = claim_due()
    if row:
        _publish_claimed(row)
        return
    if time.time() - _last_inbox < 15 * 60:
        return
    _last_inbox = time.time()
    try:
        refresh_inbox()
    except Exception:
        _log("inbox refresh failed")


def _loop() -> None:
    while True:
        try:
            _tick()
        except Exception:
            _log("tick failed")
        time.sleep(45)


def start_social_thread() -> None:
    if not scheduler_enabled():
        _log("skip (not server)")
        return
    thread = threading.Thread(target=_loop, name="social-schedule", daemon=True)
    thread.start()
    _log("start")
