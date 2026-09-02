"""Find Israeli businesses, extract public emails, draft as שי. No Hunter."""

from __future__ import annotations

import html as html_lib
import json
import re
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any
from urllib.parse import urljoin, urlparse

from leads_store import (
    SHARED_MAIL_HOSTS,
    _env_value,
    _now,
    get_item,
    gmail_connected,
    known_domains,
    pending_today_count,
    pipeline,
    save_item,
    today_il,
)
from leads_learn import (
    extract_copy_features,
    prompt_addendum,
    ranked_vertical_keys,
    vertical_icp_boost,
)
from leads_seeds import EXTRA_QUERIES, SEED_URLS, city_queries

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
TIMEOUT = 10
DAILY_TARGET = 10
SCORE_FLOOR = 72
FILL_FLOOR = 60
MAX_SEARCH = 80
WAVE_SECONDS = 11 * 60
CTX = ssl.create_default_context()
_RUN_LOCK = threading.Lock()

BEO_SERVICES = [
    "אפליקציות ואתרים",
    "סוכן AI",
    "CRM / מערכת ניהול / פורטל",
    "צ׳אטבוט ואוטומציות",
    "הטמעת AI בארגון",
]

QUERIES = [
    ("סוכנות ביטוח בוטיק ישראל", "insurance"),
    ("סוכנות ביטוח משפחתית", "insurance"),
    ("סוכנות ביטוח רעננה", "insurance"),
    ("חברה משפחתית יבוא והפצה ישראל", "import"),
    ("יבואן סיטונאי משפחתי", "import"),
    ("סיטונאות מזון נתיבות", "import"),
    ("משרד תיווך בוטיק ישראל", "realestate"),
    ("קליניקה לאסתטיקה רפואית ישראל", "clinics"),
    ("יועץ משכנתאות משרד ישראל", "mortgage"),
] + list(EXTRA_QUERIES)

EMAIL_RE = re.compile(
    r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}",
    re.I,
)
SKIP_DOMAINS = {
    "beosystem.com",
    "beosystem.co.il",
    "beo-systems.com",
}
SKIP_EMAIL_PARTS = (
    "example.com",
    "sentry.io",
    "wixpress.com",
    "cloudflare",
    "gstatic.com",
    "googleapis.com",
    "schema.org",
    "w3.org",
    "godaddy",
    "facebook.com",
    "instagram.com",
    "linkedin.com",
)

JUNK_LOCAL = {
    "noreply",
    "no-reply",
    "donotreply",
    "mailer-daemon",
    "postmaster",
    "privacy",
    "abuse",
}

CONTACT_PATHS = (
    "/",
    "/contact",
    "/contact-us",
    "/contactus",
    "/he/contact",
    "/he/contact-us",
    "/en/contact",
    "/%D7%A6%D7%95%D7%A8-%D7%A7%D7%A9%D7%A8",
    "/צור-קשר",
    "/he/צור-קשר",
    "/יצירת-קשר",
    "/contacts",
    "/contact.html",
    "/about",
    "/about-us",
    "/he",
    "/%D7%90%D7%95%D7%93%D7%95%D7%AA",
    "/אודות",
    "/our-story",
    "/privacy",
    "/privacy-policy",
    "/get-in-touch",
    "/keep-in-touch",
)


def _fetch(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "he-IL,he,en;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=CTX) as resp:
        raw = resp.read(180_000)
        charset = "utf-8"
        ctype = resp.headers.get("Content-Type") or ""
        if "charset=" in ctype.lower():
            charset = ctype.split("charset=", 1)[-1].split(";")[0].strip() or "utf-8"
        return raw.decode(charset, errors="replace")


BAD_HOSTS = (
    "duckduckgo",
    "google.",
    "bing.com",
    "microsoft.",
    "facebook.",
    "instagram.",
    "youtube.",
    "linkedin.",
    "wikipedia.",
    "wix.com",
    "yad2.",
    "alljobs.",
    "drushim.",
    "jobmaster.",
    "jobnet.",
    "indeed.",
    "glassdoor.",
    "leumi.co.il",
    "hapoalim.co.il",
    "mizrahi-tefahot.co.il",
    "discountbank.co.il",
    "harel-group.",
    "migdal.co.il",
    "clalbit.co.il",
    "phoenix.co.il",
    "menora.co.il",
    "osem.co.il",
    "strauss-group.",
    "tnuva.co.il",
    "azrieli.",
    "remax-",
    "anglo-saxon.",
)

SITE_URL = "https://beosystem.com"
INTRO_LINE = "כאן שי מ-Beo Systems."
FIXED_SUBJECT = "Beo Systems | הצעת שירותים"
ASK_BLOCK = (
    "שתף אותי בכאבים של העסק — הפעולות שחוזרות על עצמן.\n"
    "נעזור לייעל את העבודה ולהתאים לכם מעטפת שירותים."
)
SECTION_SERVICES = "השירותים שלנו"
SECTION_CONTACT = "דרכי התקשרות"
HEADER_SERVICES = f"💼 {SECTION_SERVICES}"
HEADER_CONTACT = f"📱 {SECTION_CONTACT}"
ENVELOPE_PREFIX = "אנחנו נותנים מעטפת מלאה לעסק:"
ENVELOPE_LINE = (
    f"{ENVELOPE_PREFIX} אתרים ואפליקציות, סוכני AI, מערכות ניהול, "
    f"צ׳אטבוטים ואוטומציות והטמעת AI. להתרשמות: {SITE_URL}"
)


def _keep_url(href: str) -> str | None:
    href = html_lib.unescape(href).split("#")[0]
    if href.startswith("//"):
        href = "https:" + href
    host = urlparse(href).hostname or ""
    if not host or host in SKIP_DOMAINS:
        return None
    if any(bad in host for bad in BAD_HOSTS):
        return None
    if not href.startswith("http"):
        return None
    return href


def _extract_http_urls(page: str, limit: int) -> list[str]:
    urls: list[str] = []
    for match in re.finditer(r'href="(https?://[^"]+|//[^"]+)"', page, re.I):
        kept = _keep_url(match.group(1))
        if kept and kept not in urls:
            urls.append(kept)
        if len(urls) >= limit:
            break
    for match in re.finditer(r"uddg=([^&\"']+)", page):
        kept = _keep_url(urllib.parse.unquote(match.group(1)))
        if kept and kept not in urls:
            urls.append(kept)
        if len(urls) >= limit:
            break
    return urls


def _search_page_urls(url: str, limit: int) -> list[str]:
    try:
        page = _fetch(url)
    except (urllib.error.URLError, TimeoutError, ssl.SSLError, OSError, ValueError):
        return []
    if "captcha" in page.lower() or "anomaly-modal" in page.lower():
        return []
    return _extract_http_urls(page, limit)


def _ddg_urls(query: str, limit: int = 8) -> list[str]:
    q = urllib.parse.urlencode({"q": query})
    found = _search_page_urls(f"https://lite.duckduckgo.com/lite/?{q}", limit)
    if len(found) >= 3:
        return found[:limit]
    more = _search_page_urls(f"https://html.duckduckgo.com/html/?{q}", limit)
    for href in more:
        if href not in found:
            found.append(href)
    if len(found) >= 3:
        return found[:limit]
    bing = _search_page_urls(
        "https://www.bing.com/search?" + urllib.parse.urlencode({"q": query, "setlang": "he-IL"}),
        limit,
    )
    for href in bing:
        if href not in found:
            found.append(href)
    if len(found) >= 3:
        return found[:limit]
    brave_q = urllib.parse.urlencode({"q": query})
    brave = _search_page_urls(f"https://search.brave.com/search?{brave_q}", limit)
    for href in brave:
        if href not in found:
            found.append(href)
    return found[:limit]


def _ordered_queries() -> list[str]:
    keys = ranked_vertical_keys([v for _, v in QUERIES])
    ordered: list[str] = []
    for key in keys:
        for query, vert in QUERIES:
            if vert == key and query not in ordered:
                ordered.append(query)
    for query, vert in QUERIES:
        if query not in ordered:
            ordered.append(query)
    for query, _vert in city_queries():
        if query not in ordered:
            ordered.append(query)
    return ordered


def collect_candidate_urls(
    limit: int = MAX_SEARCH,
    wave: int = 0,
    exclude: set[str] | None = None,
) -> tuple[list[str], str]:
    """Search first; seeds if engines return almost nothing. Each wave uses a new query slice."""
    skip = exclude or set()
    urls: list[str] = []
    source = "search"
    queries = _ordered_queries()
    chunk = 8
    start = wave * chunk
    slice_q = queries[start : start + chunk]
    if not slice_q:
        source = "seeds"
        for href in SEED_URLS:
            host = _domain(href)
            if host and host not in skip and href not in urls:
                urls.append(href)
            if len(urls) >= limit:
                break
        return urls[:limit], source
    for query in slice_q:
        batch = _ddg_urls(query, limit=6)
        for href in batch:
            host = _domain(href)
            if not host or host in skip or href in urls:
                continue
            urls.append(href)
        if len(urls) >= limit:
            return urls[:limit], source
    if len(urls) < 4:
        source = "seeds"
        for href in SEED_URLS:
            host = _domain(href)
            if host and host not in skip and href not in urls:
                urls.append(href)
            if len(urls) >= limit:
                break
    return urls[:limit], source


def _domain(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _unglue_email(email: str) -> str:
    """Strip a phone number glued to the mailbox (03-9649087ofra@ → ofra@)."""
    local, sep, host = email.partition("@")
    if not sep or not host:
        return email
    local = re.sub(r"^[\d.\-+/]{6,}(?=[a-z])", "", local, flags=re.I)
    if not local:
        return email
    return f"{local}@{host}"


def _decode_cfemail(hexstr: str) -> str:
    try:
        data = bytes.fromhex(hexstr)
    except ValueError:
        return ""
    if len(data) < 2:
        return ""
    key = data[0]
    try:
        return bytes(b ^ key for b in data[1:]).decode("utf-8")
    except UnicodeDecodeError:
        return ""


def _emails_from_html(page: str) -> list[str]:
    found = EMAIL_RE.findall(page)
    for mail in re.findall(r"mailto:([^\"'\s?]+)", page, re.I):
        found.append(urllib.parse.unquote(mail))
    for encoded in re.findall(r"data-cfemail=[\"']([0-9a-f]+)[\"']", page, re.I):
        decoded = _decode_cfemail(encoded)
        if decoded:
            found.append(decoded)
    for encoded in re.findall(r"email-protection#([0-9a-f]+)", page, re.I):
        decoded = _decode_cfemail(encoded)
        if decoded:
            found.append(decoded)
    for local, host in re.findall(
        r"([A-Z0-9._%+\-]+)\s*(?:\[at\]|\(at\)|\s+at\s+|\[@\])\s*([A-Z0-9.\-]+\.[A-Z]{2,})",
        page,
        re.I,
    ):
        found.append(f"{local}@{host}")
    for local, host, tld in re.findall(
        r"([A-Z0-9._%+\-]+)\s*(?:\[at\]|\(at\)|\s+at\s+)\s*([A-Z0-9.\-]+)\s*(?:\[dot\]|\(dot\)|\s+dot\s+)\s*([A-Z]{2,})",
        page,
        re.I,
    ):
        found.append(f"{local}@{host}.{tld}")
    for mail in re.findall(
        r'["\']email["\']\s*:\s*["\']([^"\']+@[^"\']+)["\']',
        page,
        re.I,
    ):
        found.append(mail)
    return found


def _email_host(email: str) -> str:
    return email.split("@", 1)[-1].lower().strip()


def _is_junk_email(email: str) -> bool:
    if "@" not in email or "." not in email.split("@")[-1]:
        return True
    if email.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".css", ".js", ".svg")):
        return True
    local = email.split("@", 1)[0].lower()
    host = _email_host(email)
    if local in JUNK_LOCAL or local.startswith("noreply"):
        return True
    if host in {"google.com", "gstatic.com"}:
        return True
    if any(part in email for part in SKIP_EMAIL_PARTS):
        return True
    return False


def _email_rank(email: str, site_domain: str) -> tuple[int, str]:
    """Lower is better. Gmail/Walla on the page is a real owner mailbox — not a consolation prize."""
    host = _email_host(email)
    local = email.split("@", 1)[0].lower()
    generic = local in GENERIC_MAILBOXES or local.startswith("info") or local.startswith("service")
    webmail = host in SHARED_MAIL_HOSTS
    same = bool(
        site_domain
        and (host == site_domain or host.endswith("." + site_domain) or email.endswith("@" + site_domain))
    )
    if webmail:
        return (0, email)
    if same and not generic:
        return (1, email)
    if same:
        return (2, email)
    return (3, email)


def _clean_emails(found: list[str], domain: str) -> list[str]:
    out: list[str] = []
    for raw in found:
        email = _unglue_email(raw.strip().strip(".,;<>()[]").lower())
        if _is_junk_email(email):
            continue
        if email not in out:
            out.append(email)
    out.sort(key=lambda e: _email_rank(e, domain))
    return out


def _plain(html_chunk: str) -> str:
    text = html_lib.unescape(re.sub(r"<[^>]+>", " ", html_chunk))
    return re.sub(r"\s+", " ", text).strip()


def _title(html: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    return _plain(m.group(1))[:160] if m else ""


def _og_site_name(html: str) -> str:
    m = re.search(
        r'<meta[^>]+(?:property|name)=["\']og:site_name["\'][^>]*content=["\']([^"\']+)',
        html,
        re.I,
    )
    if not m:
        m = re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\']og:site_name',
            html,
            re.I,
        )
    return html_lib.unescape(m.group(1)).strip() if m else ""


def _h1(html: str) -> str:
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.S)
    return _plain(m.group(1))[:120] if m else ""


def _visible_text(html: str) -> str:
    cut = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    cut = re.sub(r"(?is)<!--.*?-->", " ", cut)
    return _plain(cut)[:8000]


def _brand_from_domain(domain: str) -> str:
    host = (domain or "").split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    base = host.split(".")[0] if host else ""
    if not base:
        return domain
    return re.sub(r"[-_]+", " ", base).strip().title()


def _clean_company(raw: str, domain: str) -> str:
    t = re.sub(r"\s+", " ", (raw or "").strip())
    t = re.sub(
        r"^(דף הבית|עמוד הבית|home|homepage)\b\s*([-–—|:•·]+\s*)?",
        "",
        t,
        flags=re.I,
    )
    t = re.sub(
        r"\s*[-–—|:•·]+\s*(דף הבית|עמוד הבית|home|homepage)\s*$",
        "",
        t,
        flags=re.I,
    )
    if "|" in t:
        t = t.split("|", 1)[0].strip()
    if ":" in t:
        left = t.split(":", 1)[0].strip()
        if len(left) >= 4:
            t = left
    t = t.strip(" -–—|•·,")
    parts = [p.strip() for p in re.split(r"\s[-–—]\s", t) if p.strip()]
    if parts:
        if len(parts[0]) <= 6 and len(parts) >= 2:
            t = f"{parts[0]} - {parts[1]}"
        else:
            t = parts[0] if len(parts[0]) <= 48 else min(parts, key=len)
    low = t.lower()
    if not t or low in {"home", "homepage", "דף הבית", "עמוד הבית"} or len(t) < 2:
        return _brand_from_domain(domain)
    return t[:48]


def scrape_site(url: str) -> dict[str, Any]:
    parsed = urlparse(url if url.startswith("http") else f"https://{url}")
    origin = f"{parsed.scheme}://{parsed.netloc}"
    domain = _domain(origin)
    html_parts: list[str] = []
    emails: list[str] = []
    names: list[str] = []
    for path in CONTACT_PATHS:
        try:
            page = _fetch(urljoin(origin + "/", path.lstrip("/")))
        except (urllib.error.URLError, TimeoutError, ssl.SSLError, OSError, ValueError):
            continue
        html_parts.append(page)
        for candidate in (_og_site_name(page), _h1(page), _title(page)):
            if candidate and candidate not in names:
                names.append(candidate)
        emails.extend(_emails_from_html(page))
        cleaned_now = _clean_emails(emails, domain)
        best_host = _email_host(cleaned_now[0]) if cleaned_now else ""
        is_contact = path not in {
            "/",
            "/he",
            "/about",
            "/about-us",
            "/our-story",
            "/privacy",
            "/privacy-policy",
            "/אודות",
            "/%D7%90%D7%95%D7%93%D7%95%D7%AA",
        }
        if best_host in SHARED_MAIL_HOSTS:
            break
        if cleaned_now and is_contact:
            break
    cleaned = _clean_emails(emails, domain)
    blob = " ".join(html_parts)
    text = _visible_text(blob)
    from leads_outreach import phones_from_html

    phone = phones_from_html(blob, text)
    company = ""
    for raw in names:
        company = _clean_company(raw, domain)
        if company and company.lower() not in {"home", "דף הבית"}:
            break
    return {
        "website": origin,
        "domain": domain,
        "company": company or _brand_from_domain(domain),
        "email": cleaned[0] if cleaned else None,
        "phone": phone,
        "page_text": text,
    }


# ציון = סכום, לא תחושה. מייל גלוי הוא שער כניסה — בלי מייל אין טיוטה ובלי נקודות על עצם המייל.
SCORE_PARTS = (
    ("icp", "התאמת תחום", 40),
    ("site_signal", "אות מהאתר", 25),
    ("pain_fit", "כאב תפעולי", 25),
    ("contact", "איכות פנייה", 10),
)

VERTICALS = (
    {
        "key": "insurance",
        "words": ("ביטוח", "סוכנות לביטוח", "פנסיה", "אלמנטרי", "חיים וחסכון"),
        "service": "סוכן AI",
        "icp": 38,
        "pain_fit": 22,
        "board": "סוכנות ביטוח. הכאב הוא פניות שנופלות בין וואטסאפ, טלפון ותיק — לא אתר חדש.",
        "subject": "הפניות שנופלות אצל {company} בין הוואטסאפ לתיק",
        "subject_b": "מי סוגר אצלכם את הפניות מוואטסאפ?",
        "offer": "סוכן שמקבל את הפנייה, פותח תיק, ומוודא שמישהו חוזר",
        "pain": "בסוכנויות ביטוח הפניות מגיעות מוואטסאפ, מהטלפון ומהאתר. חלק נכנס לתיק, חלק נשאר בשיחה.",
        "question": "אצלכם פנייה מוואטסאפ נכנסת לתיק באותו יום?",
    },
    {
        "key": "import",
        "words": (
            "יבוא",
            "ייבוא",
            "סיטונאות",
            "הפצה",
            "מפיץ",
            "import",
            "wholesale",
            "distributor",
            "trade",
            "distribut",
            "ingredients",
            "חומרי בניין",
            "אריזה",
            "ריהוט",
            "furniture",
            "מיטות",
        ),
        "service": "CRM / מערכת ניהול / פורטל",
        "icp": 40,
        "pain_fit": 23,
        "board": "יבוא/סיטונאות. הכאב הוא הצעות, הזמנות וחשבוניות שרצות באקסל ובוואטסאפ.",
        "subject": "הצעות וחשבוניות אצל {company} — בלי אקסל באמצע",
        "subject_b": "ההצעה והחשבונית אצלכם עדיין באקסל?",
        "offer": "מערכת שמעבירה הצעת מחיר לאישור ולחשבונית, בלי להעתיק בין אקסל לוואטסאפ",
        "pain": "אצל יבואנים ההצעה נכתבת באקסל, האישור מגיע בוואטסאפ, והחשבונית נולדת במקום שלישי.",
        "question": "ההצעה והחשבונית אצלכם עדיין רצות באקסל?",
    },
    {
        "key": "realestate",
        "words": ("תיווך", "נדל\"ן", "נדלן", "מתווך", "דירות למכירה", "סוכנות נדל"),
        "service": "סוכן AI",
        "icp": 36,
        "pain_fit": 22,
        "board": "משרד תיווך. הכאב הוא פניות מאתר יד 2 / וואטסאפ / טלפון שלא נסגרות לתיק.",
        "subject": "הפניות של {company} שנופלות בין וואטסאפ לסיור",
        "subject_b": "מי סוגר אצלכם פנייה שהגיעה בערב?",
        "offer": "סוכן שמקבל את הפנייה, רושם פרטים, ומוודא שמישהו חוזר לפני שהלקוח עובר למשרד הבא",
        "pain": "במשרדי תיווך הפנייה מגיעה מוואטסאפ או מאתר יד 2, ואם אף אחד לא חוזר תוך שעה הלקוח כבר במשרד אחר.",
        "question": "פנייה שנוחתת אצלכם בערב נכנסת לתיק עוד באותו לילה?",
    },
    {
        "key": "clinics",
        "words": ("אסתטיקה", "קליניקה", "רפואה אסתטית", "מרפאה", "טיפולי יופי"),
        "service": "צ׳אטבוט ואוטומציות",
        "icp": 36,
        "pain_fit": 21,
        "board": "קליניקה. הכאב הוא תיאום תורים ופניות מוואטסאפ שלא נסגרות.",
        "subject": "הפניות לקליניקה של {company} שנשארות בוואטסאפ",
        "subject_b": "מי סוגר אצלכם תור שהגיע בוואטסאפ?",
        "offer": "מענה שמקבל את הפנייה, מציע תור, וסוגר את השיחה בלי שהמזכירה תרדוף אחריה",
        "pain": "בקליניקות הפנייה מגיעה באינסטגרם ובוואטסאפ, והתור נסגר רק אם מישהו הספיק לענות.",
        "question": "פנייה בוואטסאפ אצלכם נסגרת לתור באותו יום?",
    },
    {
        "key": "mortgage",
        "words": ("משכנתא", "משכנתאות", "יועץ משכנתאות", "ייעוץ משכנתא"),
        "service": "סוכן AI",
        "icp": 37,
        "pain_fit": 22,
        "board": "ייעוץ משכנתאות. הכאב הוא לידים מפרסום שלא נכנסים לתיק באותו יום.",
        "subject": "הלידים של {company} שנופלים אחרי הפרסום",
        "subject_b": "ליד מפייסבוק אצלכם נכנס לתיק באותו יום?",
        "offer": "סוכן שמקבל את הליד, שואל שאלות פתיחה, ומוודא שחוזרים לפני שהלקוח מדבר עם יועץ אחר",
        "pain": "אצל יועצי משכנתאות הליד מגיע מפייסבוק או מאתר, ואם לא חוזרים מהר הוא כבר אצל היועץ הבא.",
        "question": "ליד שהגיע היום אצלכם כבר בתיק עם שיחה ראשונה?",
    },
    {
        "key": "invoices",
        "words": ("חשבונית", "הצעת מחיר", "גבייה", "הזמנות"),
        "service": "צ׳אטבוט ואוטומציות",
        "icp": 34,
        "pain_fit": 20,
        "board": "עסק שחי על הצעות וחשבוניות ידניות. הכאב הוא המעבר מהצעה לחשבונית.",
        "subject": "מההצעה עד החשבונית אצל {company}",
        "subject_b": "כמה זמן אצלכם לוקח מהצעה עד חשבונית?",
        "offer": "אוטומציה שמקצרת את הדרך מהצעת מחיר לחשבונית",
        "pain": "כשכל הצעת מחיר היא קובץ בפני עצמו, האישור מתעכב והחשבונית נשלחת באיחור.",
        "question": "מההצעה עד החשבונית אצלכם זה עדיין ידני?",
    },
    {
        "key": "social",
        "words": ("אינסטגרם", "פייסבוק", "רשתות חברתיות", "סוכנות פרסום", "שיווק דיגיטלי"),
        "service": "סוכן AI",
        "icp": 26,
        "pain_fit": 16,
        "board": "מותג/סטודיו עם נוכחות. הכאב הוא תוכן לרשתות — רק אם זה באמת מה שרואים באתר.",
        "subject": "תוכן קבוע לרשתות של {company}",
        "subject_b": "מי מכין אצלכם את הפוסט הבא?",
        "offer": "סוכן תוכן שמכין ומפרסם פוסטים בקצב קבוע",
        "pain": "כשיש מותג באתר אבל אין מערכת תוכן, הרשתות נעצרות ברגע שאף אחד לא יושב לכתוב.",
        "question": "יש אצלכם מישהו שדואג לתוכן כל שבוע?",
    },
    {
        "key": "generic",
        "words": (),
        "service": "CRM / מערכת ניהול / פורטל",
        "icp": 14,
        "pain_fit": 10,
        "board": "עסק ישראלי בינוני. אין התאמת תחום חדה — הציון נמוך יותר בכוונה.",
        "subject": "משהו ששמתי לב אליו אצל {company}",
        "subject_b": "שאלה קצרה על התפעול אצל {company}",
        "offer": "מערכת תפעול שמתאימה לכאב אחד, לא חבילה",
        "pain": "בעסקים בגודל הזה התפעול יושב אצל אנשים, לא במערכת.",
        "question": "המעקב אצלכם עדיין אצל אנשים, לא במערכת?",
    },
)

GENERIC_MAILBOXES = {
    "info",
    "office",
    "mail",
    "contact",
    "hello",
    "sales",
    "service",
    "service1",
    "admin",
    "support",
}

COPY_BANS = (
    "מייל גלוי",
    "אתר ומייל",
    "רעיון קטן",
    "דף הבית",
    "עמוד הבית",
    "מוצר:",
    "לא עוד צ׳אט",
    "עסק ישראלי בינוני",
    "hunter",
    "ציון",
    "crm /",
)


def _detect_vertical(page_text: str) -> dict[str, Any]:
    t = (page_text or "").lower()
    for vert in VERTICALS:
        if vert["key"] == "generic":
            continue
        if any(w in t for w in vert["words"]):
            return vert
    return VERTICALS[-1]


def _too_big(page_text: str, company: str) -> str | None:
    blob = f"{company} {page_text}"
    t = blob.lower()
    if re.search(r"(בנק לאומי|בנק הפועלים|בנק דיסקונט|מזרחי טפחות)", blob):
        return "בנק — לא יעד של שי"
    if any(
        p in t
        for p in (
            "הגדולה בישראל",
            "מהגדולות במשק",
            "מהגדולות בצפון",
            "אשכול חברות",
            "nasdaq",
            "multinational",
            "חברה ציבורית",
        )
    ):
        return "גדול מדי — מחפשים עסק בינוני, לא שחקן מוביל במשק"
    if re.search(r"בורסה", blob):
        return "גדול מדי — מחפשים עסק בינוני, לא שחקן מוביל במשק"
    if re.search(r"^קבוצת\s", (company or "").strip()):
        return "קבוצת חברות — גדול מדי ליעד הנוכחי"
    workers = re.search(r"(\d{2,4})\s*עובד", t)
    if workers and int(workers.group(1)) >= 50:
        return f"גדול מדי ({workers.group(1)} עובדים) — יעד: עסק בינוני"
    trucks = re.search(r"(\d{2,3})\s*משאיות", t)
    if trucks and int(trucks.group(1)) >= 10:
        return "צי משאיות גדול — לא עסק בינוני"
    if re.search(r"(?:יותר מ[־\-]?\s*|מעל\s*)?(?:1,?000|1000)\s*לקוח", t) and any(
        w in t for w in ("מחסנ", "לוגיסט", "הפצה", "משאיות")
    ):
        return "מפיץ גדול במשק — מחפשים עסק בינוני"
    return None


def _site_hook(page_text: str, company: str, vertical: dict[str, Any]) -> str:
    text = re.sub(r"\s+", " ", page_text or "").strip()
    if not text:
        return ""
    skip = {
        "cookies",
        "javascript",
        "privacy",
        "מדיניות",
        "כל הזכויות",
        "צור קשר",
        "home",
        "דף הבית",
    }
    chunks = re.split(r"(?<=[.!?。])\s+", text)
    for chunk in chunks:
        c = chunk.strip()
        if len(c) < 28 or len(c) > 140:
            continue
        low = c.lower()
        if any(s in low for s in skip):
            continue
        if company and company.lower() in low and len(c) < 40:
            continue
        if any(w in low for w in vertical.get("words") or ()):
            return c[:140]
    for chunk in chunks:
        c = chunk.strip()
        if 40 <= len(c) <= 130 and not any(s in c.lower() for s in skip):
            return c[:140]
    return ""


def _contact_points(email: str | None) -> int:
    if not email or "@" not in email:
        return 0
    local = email.split("@", 1)[0].lower()
    if local in GENERIC_MAILBOXES or local.startswith("info") or local.startswith("service"):
        return 5
    if any(ch.isdigit() for ch in local):
        return 4
    return 9


def _site_signal_points(hook: str, vertical: dict[str, Any]) -> int:
    if not hook:
        return 8 if vertical["key"] != "generic" else 4
    extra = 6 if any(w in hook.lower() for w in vertical.get("words") or ()) else 0
    length = 12 if len(hook) >= 40 else 8
    return min(25, 10 + extra + length)


def _compose_score(
    page_text: str,
    email: str | None,
    company: str,
) -> dict[str, Any]:
    vertical = _detect_vertical(page_text)
    hook = _site_hook(page_text, company, vertical)
    boost = vertical_icp_boost(str(vertical["key"]))
    parts = {
        "icp": max(0, min(40, int(vertical["icp"]) + boost)),
        "site_signal": _site_signal_points(hook, vertical),
        "pain_fit": int(vertical["pain_fit"]),
        "contact": _contact_points(email),
    }
    from leads_outreach import hiring_intent

    hiring = hiring_intent(page_text)
    if hiring:
        parts["pain_fit"] = min(25, int(parts["pain_fit"]) + 6)
    total = min(100, sum(parts.values()))
    why = f"{company} — {vertical['board']}"
    if hook:
        why += f" מהאתר: «{hook}»"
    if hiring:
        why += " אות קנייה: מגייסים / דרושים באתר."
    if boost:
        why += f" למידה מהשוק: {boost:+d} לציון התחום."
    return {
        "score": total,
        "score_parts": parts,
        "score_why": why,
        "service": vertical["service"],
        "vertical": vertical,
        "site_hook": hook,
        "hiring_intent": hiring,
    }


def _owner_first_name(page_text: str, company: str) -> str:
    blob = page_text or ""
    patterns = (
        r"הבעלים[:\s]+(?:הוא\s+|היא\s+)?([א-ת]{2,12})",
        r"מייסד(?:ת)?[:\s]+(?:החברה\s+)?([א-ת]{2,12})",
        r"מנכ[\"״]?ל[:\s]+([א-ת]{2,12})",
        r"בראשות(?:ו של|ה של)?\s+(?:מר |גב['׳]?\s*)?([א-ת]{2,12})",
        r"נוסדה על ידי ([א-ת]{2,12})",
        r"הוקמה על ידי ([א-ת]{2,12})",
        r"בניהולו של ([א-ת]{2,12})",
        r"בניהולה של ([א-ת]{2,12})",
        r"בבעלות ([א-ת]{2,12})",
        r"שמי ([א-ת]{2,12})",
        r"נעים להכיר[, ]+שמי ([א-ת]{2,12})",
    )
    company_tokens = set((company or "").split())
    skip = {"החברה", "הסוכנות", "צוות", "חברת", "העסק", "המשרד", "הקליניקה", "המרפאה"}
    for pat in patterns:
        m = re.search(pat, blob)
        if not m:
            continue
        name = m.group(1).strip()
        if name in skip or name in company_tokens:
            continue
        return name
    return ""


def _copy_banned(text: str) -> bool:
    low = (text or "").lower()
    return any(b in low for b in COPY_BANS)


def _core_word_count(body: str) -> int:
    core = body or ""
    for marker in (SECTION_SERVICES, ENVELOPE_PREFIX, ENVELOPE_LINE):
        if marker in core:
            core = core.split(marker)[0]
            break
    return len([w for w in re.split(r"\s+", core.strip()) if w])


def _one_idea_per_line(text: str) -> str:
    """One sentence per line. Blank lines belong between blocks, not inside a block."""
    t = re.sub(r"\s+", " ", (text or "").strip())
    t = t.replace("? ", "?\n").replace("! ", "!\n")
    t = re.sub(r"\.\s+", ".\n", t)
    lines = [ln.strip() for ln in t.split("\n") if ln.strip()]
    return "\n".join(lines)


def _services_block() -> str:
    return (
        f"{HEADER_SERVICES}\n"
        "אנחנו נותנים מעטפת מלאה לעסק:\n"
        "אתרים ואפליקציות, סוכני AI, מערכות ניהול, צ׳אטבוטים ואוטומציות והטמעת AI.\n"
        "\n"
        "להתרשמות:\n"
        f"{SITE_URL}"
    )


def _contact_block(whatsapp: str) -> str:
    lines = [HEADER_CONTACT, "אפשר לחזור אליי במייל הזה."]
    if whatsapp:
        lines.extend(["", "וואטסאפ:", whatsapp])
    return "\n".join(lines)


def _strip_closing(text: str, whatsapp: str) -> str:
    text = (text or "").rstrip()
    text = re.sub(r"\n+שי\s*$", "", text).rstrip()
    for marker in (
        HEADER_CONTACT,
        HEADER_SERVICES,
        SECTION_CONTACT,
        SECTION_SERVICES,
        ENVELOPE_PREFIX,
        "להתרשמות:",
        "אפשר לחזור אליי במייל הזה",
        "אפשר גם בוואטסאפ:",
    ):
        idx = text.find(marker)
        if idx != -1:
            text = text[:idx].rstrip()
    if whatsapp:
        text = re.sub(re.escape(whatsapp) + r"\s*$", "", text).rstrip()
    return text.rstrip()


def _ensure_section_emoji(text: str) -> str:
    headed = {
        SECTION_SERVICES: HEADER_SERVICES,
        SECTION_CONTACT: HEADER_CONTACT,
        HEADER_SERVICES: HEADER_SERVICES,
        HEADER_CONTACT: HEADER_CONTACT,
    }
    out: list[str] = []
    for line in (text or "").splitlines():
        key = line.strip()
        out.append(headed.get(key, line.rstrip()))
    return "\n".join(out)


def _strip_labeled_pain(text: str) -> str:
    drop = {
        "הבעיה",
        "הפתרון",
        "📌 הבעיה",
        "✅ הפתרון",
        "📌הבעיה",
        "✅הפתרון",
    }
    lines = [ln for ln in (text or "").splitlines() if ln.strip() not in drop]
    return "\n".join(lines)


def _human_template(
    company: str,
    scored: dict[str, Any],
    whatsapp: str,
    owner: str = "",
) -> tuple[str, str, str]:
    vert = scored["vertical"]
    hook = str(scored.get("site_hook") or "").strip().strip('"')
    hello = f"שלום {owner}," if owner else "שלום,"
    offer = str(vert["offer"]).rstrip(".") + "."
    hook_lines = [f"עברתי על האתר של {company}."]
    if hook:
        hook_lines.append(hook if hook.endswith((".", "?", "!")) else f"{hook}.")
    body = (
        f"{hello}\n\n"
        f"{INTRO_LINE}\n\n"
        + "\n".join(hook_lines)
        + "\n\n"
        f"{_one_idea_per_line(vert['pain'])}\n\n"
        f"{_one_idea_per_line(offer)}\n\n"
        f"{ASK_BLOCK}"
    )
    return FIXED_SUBJECT, "", _close_mail(body, whatsapp)


def _close_mail(body: str, whatsapp: str) -> str:
    text = _ensure_section_emoji(_strip_closing(body or "", whatsapp))
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return f"{text}\n\n{_services_block()}\n\n{_contact_block(whatsapp)}\n\nשי"


def _llm_enrich(
    company: str,
    website: str,
    page_text: str,
    scored: dict[str, Any],
    owner: str = "",
) -> dict[str, Any] | None:
    key = _env_value("OPENAI_API_KEY")
    if not key:
        return None
    model = _env_value("OPENAI_MODEL") or "gpt-5.6-luna"
    vert = scored["vertical"]
    owner_hint = owner or "אין שם בטקסט — השאר owner_name ריק. אסור לנחש."
    learned = prompt_addendum()
    payload = {
        "model": model,
        "max_completion_tokens": 800,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "אתה שי מ-Beo Systems. כותב מייל בעברית מדוברת, קצר, מקצועי, אישי. "
                    "החזר JSON עם: company_name, site_hook, score_why, email_body, owner_name. "
                    "אל תחזיר נושא — הנושא קבוע במערכת. "
                    "owner_name = שם פרטי רק אם הוא כתוב במפורש בטקסט. אחרת מחרוזת ריקה. אסור לנחש. "
                    "עימוד: שורה ריקה בין בלוקים. משפט אחד = שורה אחת. קישור תמיד בשורה משלו. "
                    "בלי אימוג'י בגוף, בלי כותרות 'הבעיה' או 'הפתרון'. "
                    "מבנה מדויק: "
                    "שלום [שם אם יש], "
                    "שורה ריקה, "
                    f"'{INTRO_LINE}' "
                    "שורה ריקה, "
                    "עברתי על האתר של [שם]. "
                    "שורה חדשה: עובדה אחת מהאתר. "
                    "שורה ריקה, "
                    "2–3 משפטים על הכאב אצלם (בלי לכתוב את המילה הבעיה). "
                    "שורה ריקה, "
                    "1–2 משפטים איך אפשר לסדר את זה (בלי לכתוב את המילה הפתרון). "
                    "שורה ריקה, "
                    f"{ASK_BLOCK.replace(chr(10), ' / ')} "
                    "אל תכתוב שירותים, דרכי התקשרות, קישור או חתימה — מתווספים אוטומטית. "
                    "אסור: רעיון קטן, דף הבית, מייל גלוי, ציון, מוצר:, סלוגנים, "
                    "לא עוד צ׳אט, CRM, Hunter, follow-up, חתימה ארוכה. "
                    f"השירות הפנימי הוא {vert['service']} — אל תכניס את שם השירות הפנימי למייל."
                    + (f"\n\n{learned}" if learned else "")
                ),
            },
            {
                "role": "user",
                "content": (
                    f"שם נקי: {company}\nאתר: {website}\nתחום: {vert['key']}\n"
                    f"שם פרטי שזוהה בדף: {owner_hint}\n"
                    f"כאב ידוע: {vert['pain']}\nהצעה: {vert['offer']}\n"
                    f"טקסט מהאתר:\n{(page_text or '')[:4000]}"
                ),
            },
        ],
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": UA,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60, context=CTX) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        try:
            from leads_usage import record_from_response

            record_from_response(body, "research")
        except Exception:
            pass
        text = body["choices"][0]["message"]["content"].strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text).strip()
            text = re.sub(r"```$", "", text).strip()
        data = json.loads(text)
        if not isinstance(data, dict):
            return None
        subject = str(data.get("email_subject") or "").strip()
        mail = str(data.get("email_body") or "").strip()
        if not mail:
            return None
        if _copy_banned(subject) or _copy_banned(mail):
            return None
        return data
    except Exception:
        return None


def _item_from_scrape(scrape: dict[str, Any], status: str) -> dict[str, Any]:
    whatsapp = _env_value("WHATSAPP_ME_URL") or "https://wa.me/33632519053"
    from_email = _env_value("GMAIL_FROM") or "sales@beosystem.com"
    from_name = _env_value("GMAIL_FROM_NAME") or "שי | Beo Systems"
    company = _clean_company(str(scrape.get("company") or ""), str(scrape.get("domain") or ""))
    scored = _compose_score(scrape.get("page_text") or "", scrape.get("email"), company)
    subject, subject_b, body, draft_source = "", "", "", ""
    why = scored["score_why"]
    hook = scored.get("site_hook") or ""
    owner = _owner_first_name(scrape.get("page_text") or "", company)
    if status == "pending_approval":
        llm = _llm_enrich(
            company,
            scrape["website"],
            scrape.get("page_text") or "",
            scored,
            owner,
        )
        if llm:
            llm_name = _clean_company(str(llm.get("company_name") or ""), scrape["domain"])
            if llm_name:
                company = llm_name
            llm_why = str(llm.get("score_why") or "").strip()
            if llm_why and not _copy_banned(llm_why) and "מייל" not in llm_why:
                why = llm_why
            llm_hook = str(llm.get("site_hook") or "").strip()
            if llm_hook and not _copy_banned(llm_hook):
                hook = llm_hook[:140]
            llm_owner = str(llm.get("owner_name") or "").strip().split()[0] if llm.get("owner_name") else ""
            page = scrape.get("page_text") or ""
            if llm_owner and len(llm_owner) >= 2 and llm_owner in page:
                owner = llm_owner
            body = _strip_labeled_pain(str(llm.get("email_body") or "").strip())
            draft_source = "llm"
        if not body or _core_word_count(body) > 130:
            subject, subject_b, body = _human_template(company, scored, whatsapp, owner)
            draft_source = "template"
        else:
            ask_line = ASK_BLOCK.split("\n", 1)[0]
            if ask_line not in body:
                body = f"{body.rstrip()}\n\n{ASK_BLOCK}"
            body = _close_mail(body, whatsapp)
            subject, subject_b = FIXED_SUBJECT, ""
        features = extract_copy_features(
            subject=subject,
            body=body,
            owner=owner,
            subject_b=subject_b,
            service=scored["service"],
            vertical_key=str(scored["vertical"]["key"]),
            draft_source=draft_source,
        )
    else:
        features = {}
    keep_score = status in {"pending_approval", "skipped_low_score"}
    item = {
        "id": "",
        "company": company,
        "website": scrape["website"],
        "domain": scrape["domain"],
        "city": "",
        "email": scrape.get("email"),
        "phone": scrape.get("phone") or "",
        "owner_name": owner if status == "pending_approval" else "",
        "vertical_key": str(scored["vertical"]["key"]) if keep_score else "",
        "copy_features": features,
        "score": scored["score"] if keep_score else 0,
        "score_parts": scored["score_parts"] if keep_score else {},
        "score_why": why if keep_score else "",
        "site_hook": hook if status == "pending_approval" else "",
        "service": scored["service"] if keep_score else "",
        "draft_source": draft_source,
        "status": status,
        "skip_reason": (
            ""
            if scrape.get("email")
            else "אין מייל גלוי באתר"
        ),
        "email_subject": subject,
        "email_subject_b": subject_b,
        "email_body": body,
        "from_name": from_name,
        "from_email": from_email,
        "whatsapp_url": whatsapp,
        "draft_kind": "first",
        "gmail_connected": gmail_connected(),
        "created_at": _now(),
        "updated_at": _now(),
        "batch_date": today_il(),
        "approved_at": None,
        "rejected_at": None,
        "sent_at": None,
        "page_text": None,
    }
    if status == "pending_approval":
        from leads_outreach import attach_whatsapp

        attach_whatsapp(item)
    return item


def _revive_ok(row: dict[str, Any]) -> bool:
    if not row.get("email"):
        return False
    seed_hosts = {_domain(href) for href in SEED_URLS}
    return _domain(str(row.get("website") or row.get("domain") or "")) in seed_hosts


def redraft_pending() -> dict[str, Any]:
    """Rewrite pending drafts with current copy. Does not revive rejected. Does not send mail."""
    rows = pipeline().get("items") or []
    chosen = [
        row
        for row in rows
        if row.get("status") == "pending_approval"
        and str(row.get("draft_kind") or "first") != "followup"
    ]
    updated = 0
    skipped_floor = 0
    errors: list[str] = []
    sources: dict[str, int] = {}
    for row in chosen:
        website = str(row.get("website") or "")
        if not website:
            continue
        try:
            scrape = scrape_site(website)
            if row.get("email") and not scrape.get("email"):
                scrape["email"] = row.get("email")
            if row.get("phone") and not scrape.get("phone"):
                scrape["phone"] = row.get("phone")
            item = _item_from_scrape(scrape, "pending_approval")
            item["id"] = row["id"]
            item["created_at"] = row.get("created_at") or _now()
            item["batch_date"] = row.get("batch_date") or today_il()
            if int(item.get("score") or 0) < SCORE_FLOOR:
                item["status"] = "skipped_low_score"
                item["skip_reason"] = f"ציון {item.get('score')} מתחת לסף {SCORE_FLOOR}"
                item["email_subject"] = ""
                item["email_subject_b"] = ""
                item["email_body"] = ""
                save_item(item)
                skipped_floor += 1
                continue
            item["status"] = "pending_approval"
            item["rejected_at"] = None
            save_item(item)
            src = str(item.get("draft_source") or "template")
            sources[src] = sources.get(src, 0) + 1
            updated += 1
        except Exception as exc:
            errors.append(f"{row.get('domain')}: {exc}")
    return {
        "ok": True,
        "message": f"שוכתבו {updated} טיוטות"
        + (f", {skipped_floor} דולגו בגלל ציון נמוך" if skipped_floor else ""),
        "updated": updated,
        "skipped_low_score": skipped_floor,
        "draft_sources": sources,
        "errors": errors,
    }


def _consider_scrape(
    scrape: dict[str, Any],
    *,
    existing_id: str | None = None,
    floor: int = SCORE_FLOOR,
) -> str:
    """Save one site. Returns pending / skipped / error."""
    company = _clean_company(str(scrape.get("company") or ""), str(scrape.get("domain") or ""))
    if not scrape.get("email"):
        item = _item_from_scrape(scrape, "skipped_no_email")
        if existing_id:
            item["id"] = existing_id
            prev = get_item(existing_id) or {}
            item["created_at"] = prev.get("created_at") or item.get("created_at")
            item["email_retried"] = True
        item["skip_reason"] = "אין מייל גלוי באתר"
        save_item(item)
        return "skipped"
    big = _too_big(scrape.get("page_text") or "", company)
    if big:
        item = _item_from_scrape(scrape, "skipped_too_big")
        if existing_id:
            item["id"] = existing_id
        item["skip_reason"] = big
        save_item(item)
        return "skipped"
    scored = _compose_score(scrape.get("page_text") or "", scrape.get("email"), company)
    score = int(scored.get("score") or 0)
    if score < floor:
        item = _item_from_scrape(scrape, "skipped_low_score")
        if existing_id:
            item["id"] = existing_id
        item["skip_reason"] = f"ציון {score} מתחת לסף {SCORE_FLOOR}"
        item["email_subject"] = ""
        item["email_subject_b"] = ""
        item["email_body"] = ""
        save_item(item)
        return "skipped"
    item = _item_from_scrape(scrape, "pending_approval")
    if existing_id:
        prev = get_item(existing_id) or {}
        item["id"] = existing_id
        item["created_at"] = prev.get("created_at") or item.get("created_at")
    item["status"] = "pending_approval"
    item["skip_reason"] = None
    item["batch_date"] = today_il()
    save_item(item)
    return "pending"


def _retry_no_email(need: int, errors: list[str]) -> tuple[int, int]:
    added = 0
    checked = 0
    rows = pipeline().get("items") or []
    for row in rows:
        if added >= need:
            break
        if row.get("status") != "skipped_no_email":
            continue
        if row.get("email_retried"):
            continue
        website = str(row.get("website") or "")
        if not website:
            continue
        checked += 1
        try:
            scrape = scrape_site(website)
        except Exception as exc:
            errors.append(f"{row.get('domain')}: {exc}")
            row["email_retried"] = True
            save_item(row)
            continue
        result = _consider_scrape(scrape, existing_id=str(row.get("id") or ""), floor=SCORE_FLOOR)
        if result == "pending":
            added += 1
        else:
            marked = get_item(str(row.get("id") or "")) or row
            marked["email_retried"] = True
            save_item(marked)
    return added, checked


def _fill_from_low_score(need: int) -> int:
    """If still short of 10, promote the best skipped drafts that still have a public email."""
    if need <= 0:
        return 0
    rows = []
    for r in pipeline().get("items") or []:
        if r.get("status") != "skipped_low_score" or not r.get("email"):
            continue
        if str(r.get("vertical_key") or "") == "generic":
            continue
        score = int(r.get("score") or 0)
        if score and score < FILL_FLOOR:
            continue
        rows.append(r)
    rows.sort(key=lambda r: int(r.get("score") or 0), reverse=True)
    added = 0
    for row in rows:
        if added >= need:
            break
        website = str(row.get("website") or "")
        if not website:
            continue
        try:
            scrape = scrape_site(website)
            if row.get("email") and not scrape.get("email"):
                scrape["email"] = row.get("email")
        except Exception:
            continue
        result = _consider_scrape(
            scrape,
            existing_id=str(row.get("id") or ""),
            floor=FILL_FLOOR,
        )
        if result == "pending":
            added += 1
    return added


def run_daily(target: int = DAILY_TARGET, start_wave: int = 0) -> dict[str, Any]:
    """Keep hunting until `target` pending drafts today. Scheduler calls again if still short."""
    if not _RUN_LOCK.acquire(blocking=False):
        return {
            "ok": True,
            "message": "מחקר כבר רץ",
            "added_pending": 0,
            "skipped": 0,
            "checked": 0,
            "pending_today": pending_today_count(),
            "next_wave": start_wave,
        }
    try:
        return _run_daily_locked(target, start_wave=start_wave)
    finally:
        _RUN_LOCK.release()


def _run_daily_locked(target: int, start_wave: int = 0) -> dict[str, Any]:
    try:
        from leads_learn import learn as _learn

        _learn(with_llm=False)
    except Exception:
        pass
    need = max(0, min(target, DAILY_TARGET) - pending_today_count())
    seen = known_domains()
    added_pending = 0
    skipped = 0
    checked = 0
    errors: list[str] = []
    sources: list[str] = []
    if need <= 0:
        try:
            from leads_telegram import notify_ten_ready

            notify_ten_ready()
        except Exception:
            pass
        return {
            "ok": True,
            "message": "כבר יש מספיק טיוטות להיום",
            "added_pending": 0,
            "skipped": 0,
            "checked": 0,
            "pending_today": pending_today_count(),
            "next_wave": start_wave,
            "target_met": True,
        }

    deadline = time.monotonic() + WAVE_SECONDS
    wave = max(0, int(start_wave or 0))
    while added_pending < need and wave < 24 and time.monotonic() < deadline:
        urls, source = collect_candidate_urls(MAX_SEARCH, wave=wave, exclude=seen)
        if source not in sources:
            sources.append(source)
        if source == "seeds" and wave == 0:
            errors.append("מנוע חיפוש חסם בוטים — ממשיכים מרשימת עסקים ומגלים נוספים")
        for url in urls:
            if added_pending >= need or time.monotonic() >= deadline:
                break
            domain = _domain(url)
            if not domain or domain in seen or domain in SKIP_DOMAINS:
                continue
            seen.add(domain)
            checked += 1
            try:
                scrape = scrape_site(url)
            except Exception as exc:
                errors.append(f"{domain}: {exc}")
                continue
            seen.add(scrape["domain"])
            result = _consider_scrape(scrape)
            if result == "pending":
                added_pending += 1
            else:
                skipped += 1
        wave += 1

    if added_pending < need and time.monotonic() < deadline:
        retry_added, retry_checked = _retry_no_email(need - added_pending, errors)
        added_pending += retry_added
        checked += retry_checked

    filled = 0
    if added_pending < need:
        filled = _fill_from_low_score(need - added_pending)
        added_pending += filled

    pending_now = pending_today_count()
    msg = f"נוספו {added_pending} טיוטות לאישור"
    if filled:
        msg += f" (כולל {filled} מהציון {FILL_FLOOR}+ להשלמת היום)"
    if "seeds" in sources and added_pending:
        msg += " · חלק מאתרים ישראלים מוכנים"
    if added_pending == 0 and skipped:
        msg = f"נבדקו אתרים, {skipped} דולגו (אין מייל, גדול מדי או ציון נמוך) — ממשיכים לחפש"
    elif added_pending == 0:
        msg = "לא נמצאו אתרים לסריקה — ננסה שוב עד סוף יום העבודה"
    if pending_now < DAILY_TARGET:
        msg += f". יש {pending_now}/{DAILY_TARGET} להיום — שי ממשיך עד עשר."
    try:
        from leads_telegram import notify_ten_ready

        notify_ten_ready()
    except Exception:
        pass
    return {
        "ok": True,
        "message": msg,
        "added_pending": added_pending,
        "skipped": skipped,
        "checked": checked,
        "pending_today": pending_now,
        "search_source": sources[0] if sources else "search",
        "score_floor": SCORE_FLOOR,
        "errors": errors[:8],
        "gmail_connected": gmail_connected(),
        "target_met": pending_now >= DAILY_TARGET,
        "next_wave": wave,
    }
