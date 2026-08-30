"""Compose Beo Social captions from an idea, in beosystem.com voice."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

HASHTAGS = [
    "#BeoSystems",
    "#סוכניAI",
    "#בינהמלאכותית",
    "#פיתוחתוכנה",
    "#BeoOS",
]

FORBIDDEN = ("שמח לעזור", "להיכנס לאפליקציה", "העתק והדבק")
TAG_TAIL = re.compile(r"(?:\n*(?:#[\u0590-\u05FFa-zA-Z0-9_]+(?:\s+|$))+)\s*$")


def strip_hashtags(text: str) -> str:
    return TAG_TAIL.sub("", (text or "").replace("\r\n", "\n")).strip()


def with_hashtags(text: str, on: bool) -> str:
    body = strip_hashtags(text)
    if not on or not body:
        return body
    return f"{body}\n\n{' '.join(HASHTAGS)}"


def _system() -> str:
    return "\n".join(
        [
            "אתה קופירייטר של Beo Systems (beosystem.com).",
            "קו: מבינים תוכנה. מבינים AI.",
            "עברית מדוברת, חדה, קצרה. בלי באזז ובלי ברושור.",
            "צבעי מותג: סגול #5828A0, שחור, פחם. לא ליבה, לא ביטוח.",
            "מוצרים לבחור מהם לפי הרעיון (לא תפריט): אתרים ואפליקציות, סוכני AI, CRM/פורטלים, צ׳אטבוטים ואוטומציות, הטמעת AI, Beo OS.",
            "מבנה:",
            "1) שורת הוק לבד, עד ~90 תווים.",
            "2) שורה ריקה אחת.",
            "3) 1–3 משפטים קצרים, כל משפט בשורה. בלי פסקה דחוסה.",
            "4) שורה ריקה, ואז CTA שמתחיל ב-👉 ומוביל ל-beosystem.com או לשיחה קצרה.",
            "אסור: האשטגים (נוסיף בנפרד), מחירים, הבטחות מספריות, " + " · ".join(FORBIDDEN) + ".",
            "החזר JSON בלבד: {\"body\": \"...\"} עם ירידות שורה אמיתיות ב-body.",
        ]
    )


def compose_from_idea(*, idea: str, date: str = "") -> dict[str, Any]:
    idea = (idea or "").strip()
    if not idea:
        return {"ok": False, "error": "חסר רעיון לניסוח"}
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        return {"ok": False, "error": "חסר OPENAI_API_KEY"}
    model = (os.environ.get("OPENAI_MODEL") or "gpt-5.6-luna").strip()
    payload = {
        "model": model,
        "temperature": 0.7,
        "max_tokens": 500,
        "messages": [
            {"role": "system", "content": _system()},
            {
                "role": "user",
                "content": (
                    f"תאריך פוסט: {date}\n"
                    "נסח פוסט שיווקי מהרעיון הבא — אל תעתיק מילה במילה:\n"
                    f"{idea}"
                ),
            },
        ],
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")[:300]
        return {"ok": False, "error": err or f"OpenAI HTTP {exc.code}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}

    raw = (((data.get("choices") or [{}])[0]).get("message") or {}).get("content") or ""
    raw = raw.strip()
    body = ""
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            body = str(parsed.get("body") or "").strip()
    except json.JSONDecodeError:
        body = raw
    if body.startswith("```"):
        body = re.sub(r"^```(?:json)?\s*|\s*```$", "", body).strip()
        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict):
                body = str(parsed.get("body") or body).strip()
        except json.JSONDecodeError:
            pass
    body = strip_hashtags(body)
    if not body:
        return {"ok": False, "error": "המודל לא החזיר ניסוח"}
    low = body.lower()
    if any(p in body or p.lower() in low for p in FORBIDDEN):
        return {"ok": False, "error": "הניסוח נפסל — נסו רעיון אחר"}
    return {"ok": True, "body": body, "hashtags": HASHTAGS}
