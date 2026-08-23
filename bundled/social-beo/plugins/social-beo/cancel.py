"""Detect free-language cancel of a post / questionnaire."""

from __future__ import annotations

import re

ACK = "עצרתי. אין פוסט ואין שאלון. כשתרצה משהו — כתוב בשפה חופשית."

# Whole-message cancel. Includes the typo «טל פוסט» (missing ב).
_EXACT = {
    "בטל",
    "ביטול",
    "תבטל",
    "תפסיק",
    "עצור",
    "cancel",
    "stop",
    "טל פוסט",
    "בטל פוסט",
    "ביטול פוסט",
    "תבטל פוסט",
    "תפסיק פוסט",
    "בטל את הפוסט",
    "תבטל את הפוסט",
    "תפסיק את הפוסט",
    "תפסיק את היצירה",
    "בטל את היצירה",
    "בטל שאלון",
    "בטל את השאלון",
    "תשכח מזה",
    "תשכח מהפוסט",
    "לא רוצה את זה",
    "לא רוצה את הפוסט",
    "לא צריך את הפוסט",
    "מספיק עם זה",
    "מספיק עם הפוסט",
}

_START = re.compile(
    r"^(?:"
    r"בטל|ביטול|תבטל|תפסיק|עצור|טל"
    r")\s+(?:את\s+)?(?:ה)?(?:פוסט|יצירה|שאלון|תהליך)\b",
    re.I,
)
_EN = re.compile(r"^(?:cancel|stop)\s+(?:the\s+)?(?:post|this|it)\b", re.I)


def looks_like_cancel(text: str) -> bool:
    raw = (text or "").strip()
    if not raw or raw.startswith("/"):
        return False
    compact = re.sub(r"\s+", " ", raw).strip(".,!?… \t")
    if not compact:
        return False
    if compact in _EXACT or compact.lower() in _EXACT:
        return True
    return bool(_START.match(compact) or _EN.match(compact))
