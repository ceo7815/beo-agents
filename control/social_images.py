"""Generate Beo-branded stills for the OS calendar. Images only — not video."""

from __future__ import annotations

import base64
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from social_store import REPO

MEDIA = REPO / "bundled" / "social-beo" / "home" / "media"
LOGO = REPO / "bundled" / "social-beo" / "brand" / "logo-beo.png"

SIZES = {
    "feed": "1024x1024",
    "story": "1024x1536",
    "feed_4x5": "1024x1536",
}


def _b64(response: Any) -> bytes | None:
    data = getattr(response, "data", None) or []
    if not data:
        return None
    raw = getattr(data[0], "b64_json", None)
    if not raw:
        return None
    return base64.b64decode(raw)


def generate_still(*, headline: str, sub: str = "", fmt: str = "feed") -> dict[str, Any]:
    headline = (headline or "").strip()
    if not headline:
        return {"ok": False, "error": "חסרה כותרת לתמונה"}
    if not (os.environ.get("OPENAI_API_KEY") or "").strip():
        return {"ok": False, "error": "חסר OPENAI_API_KEY"}
    try:
        import openai
    except ImportError:
        return {"ok": False, "error": "חבילת openai חסרה בשרת"}

    size = SIZES.get(fmt, "1024x1024")
    prompt = (
        "Premium social graphic for Beo Systems. Colors purple #5828A0, black, charcoal #181818. "
        "Sharp, technological, Israel. "
        f"Render this Hebrew headline large, sharp, RTL, high contrast: {headline}"
    )
    if sub.strip():
        prompt += f" Second Hebrew line, smaller: {sub.strip()}"
    prompt += (
        " Official circular Beo Systems mark if present in the reference image — paint it into the scene, "
        "not a corner sticker. No English sentences except the Beo wordmark."
    )

    client = openai.OpenAI()
    image_bytes = None
    last = ""
    if LOGO.is_file():
        with LOGO.open("rb") as handle:
            try:
                response = client.images.edit(
                    model="gpt-image-2",
                    image=handle,
                    prompt=prompt,
                    size=size,
                    quality="medium",
                    n=1,
                )
                image_bytes = _b64(response)
            except Exception as exc:
                last = str(exc)
    if image_bytes is None:
        try:
            response = client.images.generate(
                model="gpt-image-2",
                prompt=prompt + " Include a circular purple Beo Systems logo.",
                size=size,
                quality="medium",
                n=1,
            )
            image_bytes = _b64(response)
        except Exception as exc:
            return {"ok": False, "error": (last or str(exc))[:400]}
    if not image_bytes:
        return {"ok": False, "error": "OpenAI לא החזיר תמונה"}

    MEDIA.mkdir(parents=True, exist_ok=True)
    name = f"beo-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.png"
    path = MEDIA / name
    path.write_bytes(image_bytes)
    return {
        "ok": True,
        "file": name,
        "url": f"/api/social/media/{name}",
        "format": fmt,
    }


def media_bytes(name: str) -> tuple[bytes, str] | None:
    safe = Path(name).name
    if safe != name or ".." in name:
        return None
    path = MEDIA / safe
    if not path.is_file():
        return None
    return path.read_bytes(), "image/png"
