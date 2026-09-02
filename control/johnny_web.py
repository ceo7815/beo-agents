"""Public web search for Johnny — same idea as ChatGPT browse, no extra API key."""

from __future__ import annotations

import html as html_lib
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

CTX = ssl.create_default_context()
UA = "Mozilla/5.0 (compatible; BeoJohnny/1.0; +https://beosystem.com)"


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=12, context=CTX) as resp:
        return resp.read().decode("utf-8", errors="replace")


def search(query: str, limit: int = 6) -> dict[str, Any]:
    q = (query or "").strip()
    if len(q) < 2:
        return {"ok": False, "error": "אין מה לחפש"}
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": q})
    try:
        page = _fetch(url)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "error": f"חיפוש נכשל: {type(exc).__name__}"}
    items: list[dict[str, str]] = []
    for m in re.finditer(
        r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</(?:a|td|div)',
        page,
        re.I | re.S,
    ):
        href = html_lib.unescape(m.group(1))
        if "uddg=" in href:
            parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
            href = (parsed.get("uddg") or [href])[0]
        title = re.sub(r"<[^>]+>", " ", html_lib.unescape(m.group(2)))
        snippet = re.sub(r"<[^>]+>", " ", html_lib.unescape(m.group(3)))
        title = re.sub(r"\s+", " ", title).strip()[:160]
        snippet = re.sub(r"\s+", " ", snippet).strip()[:280]
        if href.startswith("http") and title:
            items.append({"title": title, "url": href, "snippet": snippet})
        if len(items) >= limit:
            break
    if not items:
        for href, title in re.findall(r'href="(https?://[^"]+)"[^>]*>([^<]{8,120})</a>', page):
            if "duckduckgo.com" in href:
                continue
            items.append({"title": title.strip()[:160], "url": href, "snippet": ""})
            if len(items) >= limit:
                break
    return {"ok": True, "query": q, "items": items}


def fetch_page(url: str) -> dict[str, Any]:
    raw = (url or "").strip()
    if not raw.startswith("http://") and not raw.startswith("https://"):
        return {"ok": False, "error": "צריך כתובת http(s)"}
    try:
        page = _fetch(raw)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return {"ok": False, "error": f"לא נפתח: {type(exc).__name__}"}
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", page)
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"<[^>]+>", " ", html_lib.unescape(text))
    text = re.sub(r"\s+", " ", text).strip()
    return {"ok": True, "url": raw, "text": text[:5000]}
