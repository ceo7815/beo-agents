"""Beo Social plugin — draft archive and performance learning."""

from __future__ import annotations

import base64
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .specs import SPECS, get_spec

ISO = "%Y-%m-%dT%H:%M:%SZ"


def _home() -> Path:
    root = Path(os.environ.get("HERMES_HOME") or Path(__file__).resolve().parents[2])
    home = root / "home"
    for name in ("drafts", "media", "performance"):
        (home / name).mkdir(parents=True, exist_ok=True)
    return home


def _now() -> str:
    return datetime.now(timezone.utc).strftime(ISO)


def _ok(payload: dict[str, Any]) -> str:
    return json.dumps({"ok": True, **payload}, ensure_ascii=False, indent=2)


def _err(message: str) -> str:
    return json.dumps({"ok": False, "error": message}, ensure_ascii=False)


def get_brand_assets(params: dict, **kwargs) -> str:
    del kwargs, params
    root = Path(os.environ.get("HERMES_HOME") or Path(__file__).resolve().parents[2])
    logo = root / "brand" / "logo-beo.png"
    if not logo.is_file():
        return _err("Logo missing. Expected brand/logo-beo.png in this agent folder.")
    return _ok(
        {
            "logo_path": str(logo.resolve()),
            "mark": "circular Beo Systems — purple Beo, Systems, Digital · AI · Dev, ring #5828A0",
            "how": (
                "Pass this file as the image-gen reference. Paint the mark into the scene "
                "(glass, wall, light, product, reflection). Do not stamp a sticker in the corner."
            ),
        }
    )


def make_beo_visual(params: dict, **kwargs) -> str:
    del kwargs
    from .preparing import send_preparing

    send_preparing()
    headline = str(params.get("headline_he") or "").strip()
    if not headline:
        return _err("headline_he is required")
    sub = str(params.get("sub_he") or "").strip()
    fmt = str(params.get("format") or "feed_4x5").strip().lower().replace(".", "_")
    size = {
        "feed_1x1": "1024x1024",
        "landscape": "1536x1024",
        "cover": "1536x1024",
    }.get(fmt, "1024x1536")

    root = Path(os.environ.get("HERMES_HOME") or Path(__file__).resolve().parents[2])
    logo = root / "brand" / "logo-beo.png"
    if not logo.is_file():
        return _err("brand/logo-beo.png is missing")
    if not os.environ.get("OPENAI_API_KEY"):
        return _err("OPENAI_API_KEY is not set")

    prompt = (
        "Premium social graphic for Beo Systems. Use the attached circular Beo Systems "
        "logo as the exact brand mark — purple ring, word Beo, Systems, Digital AI Dev. "
        "Paint that mark into the composition (glass, wall, light, product). "
        "Do not invent a different logo. Do not put a sticker in the corner. "
        "Colors: purple #5828A0, black, charcoal. "
        f"Render this Hebrew headline large, sharp, RTL, high contrast: {headline}"
    )
    if sub:
        prompt += f" Second Hebrew line, smaller: {sub}"
    prompt += " No English sentences on the graphic except the official Beo wordmark from the logo."

    try:
        import openai
    except ImportError:
        return _err("openai package missing")

    client = openai.OpenAI()
    image_bytes = None
    last_error = ""
    with logo.open("rb") as handle:
        try:
            response = client.images.edit(
                model="gpt-image-2",
                image=handle,
                prompt=prompt,
                size=size,
                quality="medium",
                n=1,
            )
            image_bytes = _b64_from_response(response)
        except Exception as exc:
            last_error = str(exc)

    if image_bytes is None:
        try:
            response = client.images.generate(
                model="gpt-image-2",
                prompt=prompt + " Faithfully reproduce the Beo Systems circular purple logo.",
                size=size,
                quality="medium",
                n=1,
            )
            image_bytes = _b64_from_response(response)
        except Exception as exc:
            return _err(f"Image API failed: {last_error or exc}")

    if not image_bytes:
        return _err("OpenAI returned no image")

    out = _home() / "media" / f"beo-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.png"
    out.write_bytes(image_bytes)
    path = str(out.resolve())
    return _ok(
        {
            "image_path": path,
            "media_tag": f"MEDIA:{path}",
            "size": size,
            "how_to_reply": (
                "ONE Telegram message: first line MEDIA:path, then a SHORT punchy "
                "Hebrew caption (hook + 1-2 lines + 3-5 hashtags). No essay. "
                "Do not ask approval yourself — it is sent automatically after the photo."
            ),
        }
    )


def _b64_from_response(response) -> bytes | None:
    data = getattr(response, "data", None) or []
    if not data:
        return None
    b64 = getattr(data[0], "b64_json", None)
    if not b64:
        return None
    return base64.b64decode(b64)


def get_platform_specs(params: dict, **kwargs) -> str:
    del kwargs
    platform = str(params.get("platform") or "").strip().lower()
    rows = list(SPECS.values())
    if platform:
        rows = [row for row in rows if row["platform"] == platform]
        if not rows:
            return _err(f"Unknown platform {platform!r}. Use instagram or facebook.")
    return _ok({"specs": rows})


def save_social_pack(params: dict, **kwargs) -> str:
    del kwargs
    platform = str(params.get("platform") or "").strip().lower()
    fmt = str(params.get("format") or "").strip().lower()
    spec = get_spec(platform, fmt)
    if spec is None:
        return _err("Unknown platform/format. Call get_platform_specs first.")

    pack_id = str(params.get("id") or f"{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}")
    pack = {
        "id": pack_id,
        "created_at": _now(),
        "platform": platform,
        "format": fmt,
        "width": spec["width"],
        "height": spec["height"],
        "ratio": spec["ratio"],
        "language": str(params.get("language") or "he"),
        "hook": str(params.get("hook") or "").strip(),
        "body": str(params.get("body") or "").strip(),
        "cta": str(params.get("cta") or "").strip(),
        "hashtags": params.get("hashtags") or [],
        "story_line": str(params.get("story_line") or "").strip(),
        "image_prompt": str(params.get("image_prompt") or "").strip(),
        "image_path": str(params.get("image_path") or "").strip(),
        "status": str(params.get("status") or "draft"),
        "notes": str(params.get("notes") or "").strip(),
    }
    path = _home() / "drafts" / f"{pack_id}.json"
    path.write_text(json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return _ok({"draft": pack, "path": str(path)})


def record_performance(params: dict, **kwargs) -> str:
    del kwargs
    draft_id = str(params.get("draft_id") or "").strip()
    if not draft_id:
        return _err("draft_id is required")

    row = {
        "id": f"perf-{uuid.uuid4().hex[:8]}",
        "draft_id": draft_id,
        "recorded_at": _now(),
        "platform": str(params.get("platform") or "").strip().lower(),
        "impressions": _num(params.get("impressions")),
        "reach": _num(params.get("reach")),
        "likes": _num(params.get("likes")),
        "comments": _num(params.get("comments")),
        "shares": _num(params.get("shares")),
        "saves": _num(params.get("saves")),
        "profile_visits": _num(params.get("profile_visits")),
        "link_clicks": _num(params.get("link_clicks")),
        "notes": str(params.get("notes") or "").strip(),
    }
    path = _home() / "performance" / f"{row['id']}.json"
    path.write_text(json.dumps(row, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return _ok(
        {
            "recorded": row,
            "path": str(path),
            "next": "Update memories/MEMORY.md with one lesson. Then call performance_insights.",
        }
    )


def performance_insights(params: dict, **kwargs) -> str:
    del kwargs
    folder = _home() / "performance"
    rows = _read_json_dir(folder)
    if not rows:
        return _ok({"count": 0, "message": "No results yet. Ask Or to paste likes/reach after a post goes live."})

    def score(row: dict) -> float:
        return (
            _num(row.get("likes")) * 1.0
            + _num(row.get("comments")) * 3.0
            + _num(row.get("saves")) * 2.5
            + _num(row.get("shares")) * 2.5
            + _num(row.get("link_clicks")) * 4.0
            + _num(row.get("profile_visits")) * 3.0
            + _num(row.get("reach")) * 0.01
        )

    ranked = sorted(rows, key=score, reverse=True)
    top_n = max(1, int(params.get("limit") or 3))
    return _ok(
        {
            "count": len(ranked),
            "best": ranked[:top_n],
            "weakest": list(reversed(ranked[-top_n:])),
            "rule": "Repeat hooks/formats in best. Stop patterns in weakest. Write the lesson to MEMORY.md.",
        }
    )


def _num(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _read_json_dir(folder: Path) -> list[dict]:
    rows: list[dict] = []
    if not folder.is_dir():
        return rows
    for path in sorted(folder.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            rows.append(data)
    return rows
