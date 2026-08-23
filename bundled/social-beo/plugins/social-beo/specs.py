"""Canonical Instagram / Facebook sizes. Source of truth for the plugin tools."""

from __future__ import annotations

SPECS: dict[str, dict] = {
    "instagram.feed_4x5": {
        "platform": "instagram",
        "format": "feed_4x5",
        "label": "Instagram feed portrait (recommended)",
        "width": 1080,
        "height": 1350,
        "ratio": "4:5",
        "image_aspect": "3:4",
        "notes": "Default IG feed. Highest usable portrait in-feed.",
    },
    "instagram.feed_1x1": {
        "platform": "instagram",
        "format": "feed_1x1",
        "label": "Instagram feed square",
        "width": 1080,
        "height": 1080,
        "ratio": "1:1",
        "image_aspect": "1:1",
        "notes": "Carousel-friendly. Less feed real-estate than 4:5.",
    },
    "instagram.story": {
        "platform": "instagram",
        "format": "story",
        "label": "Instagram story / reel",
        "width": 1080,
        "height": 1920,
        "ratio": "9:16",
        "image_aspect": "9:16",
        "notes": "Keep type in the vertical center. Avoid top ~250px and bottom ~250px (ui chrome).",
    },
    "facebook.feed_1x1": {
        "platform": "facebook",
        "format": "feed_1x1",
        "label": "Facebook feed photo",
        "width": 1080,
        "height": 1080,
        "ratio": "1:1",
        "image_aspect": "1:1",
        "notes": "Native photo post. Caption can be longer than IG.",
    },
    "facebook.feed_4x5": {
        "platform": "facebook",
        "format": "feed_4x5",
        "label": "Facebook feed portrait",
        "width": 1080,
        "height": 1350,
        "ratio": "4:5",
        "image_aspect": "3:4",
        "notes": "Mobile-first photo. Not a link preview.",
    },
    "facebook.landscape": {
        "platform": "facebook",
        "format": "landscape",
        "label": "Facebook link / landscape",
        "width": 1200,
        "height": 630,
        "ratio": "1.91:1",
        "image_aspect": "16:9",
        "notes": "Link shares and landscape feed. Crop 16:9 toward 1200x630.",
    },
    "facebook.story": {
        "platform": "facebook",
        "format": "story",
        "label": "Facebook story",
        "width": 1080,
        "height": 1920,
        "ratio": "9:16",
        "image_aspect": "9:16",
        "notes": "Same canvas as IG story. Copy must still be Facebook-toned if posted there.",
    },
    "facebook.cover": {
        "platform": "facebook",
        "format": "cover",
        "label": "Facebook page cover",
        "width": 1640,
        "height": 624,
        "ratio": "2.63:1",
        "image_aspect": "16:9",
        "notes": "Upload 1640x624. Keep logo and type out of profile-photo overlap on the left.",
    },
}


def get_spec(platform: str, fmt: str) -> dict | None:
    key = f"{str(platform).strip().lower()}.{str(fmt).strip().lower()}"
    return SPECS.get(key)
