"""Detect a free-language post brief (not a greeting, not cancel)."""

from __future__ import annotations

import re

from .cancel import looks_like_cancel

_GREET = {
    "היי",
    "הי",
    "שלום",
    "מה קורה",
    "מה קורה?",
    "מה נשמע",
    "בוקר טוב",
    "ערב טוב",
    "yo",
    "hi",
    "hey",
    "hello",
}

_BRIEF = re.compile(
    r"פוסט|תכין|תייצר|תיצור|תעשה|תכתוב|תעצב|קלוריות|סטורי|קאבר|האשטאג",
    re.I,
)


def looks_like_brief(text: str) -> bool:
    raw = (text or "").strip()
    if not raw or raw.startswith("/") or looks_like_cancel(raw):
        return False
    compact = re.sub(r"\s+", " ", raw).strip(".,!?… \t")
    if compact in _GREET or compact.lower() in _GREET:
        return False
    if _BRIEF.search(compact) and len(compact) >= 24:
        return True
    return len(compact) >= 90
