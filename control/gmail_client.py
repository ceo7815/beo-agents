"""Gmail API for Beo Leads — send from sales@ after OAuth. Never print secrets."""

from __future__ import annotations

import base64
import html as html_mod
import json
import re
import threading
import time
from email.message import EmailMessage
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
OAUTH = REPO / "agents" / "leads-beo" / "secrets" / "gmail-oauth.json"
TOKEN = REPO / "agents" / "leads-beo" / "secrets" / "gmail-token.json"
HOME_TOKEN = REPO / "agents" / "leads-beo" / "home" / "secrets" / "gmail-token.json"

SEND_SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]
# Signature HTML needs this extra scope. Old refresh tokens do not have it —
# never request it on refresh or Google returns invalid_scope and send fails.
CONNECT_SCOPES = SEND_SCOPES + [
    "https://www.googleapis.com/auth/gmail.settings.basic",
]
SCOPES = SEND_SCOPES

GMAIL_LOCK = threading.Lock()
GMAIL_HTTP_TIMEOUT = 20
_SIG_CACHE: dict[str, tuple[float, str]] = {}
_SIG_TTL = 3600.0


def oauth_file_present() -> bool:
    return OAUTH.is_file()


def token_present() -> bool:
    if TOKEN.is_file() or HOME_TOKEN.is_file():
        return True
    try:
        from leads_store import _env_value
    except Exception:
        return False
    return bool((_env_value("GMAIL_REFRESH_TOKEN") or "").strip())


def _token_file() -> Path:
    if HOME_TOKEN.is_file():
        return HOME_TOKEN
    return TOKEN


def _scopes_for_file(path: Path) -> list[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return list(SEND_SCOPES)
    raw = data.get("scopes") or data.get("scope") or []
    if isinstance(raw, str):
        raw = raw.split()
    if not isinstance(raw, list) or not raw:
        return list(SEND_SCOPES)
    cleaned = [str(s) for s in raw if "settings.basic" not in str(s)]
    return cleaned or list(SEND_SCOPES)


def _creds():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    from leads_store import _env_value

    path = _token_file()
    creds = None
    scopes = list(SEND_SCOPES)
    if path.is_file():
        scopes = _scopes_for_file(path)
        creds = Credentials.from_authorized_user_file(str(path), scopes)
    if creds is None:
        refresh = (_env_value("GMAIL_REFRESH_TOKEN") or "").strip()
        client_id = (_env_value("GMAIL_CLIENT_ID") or "").strip()
        client_secret = (_env_value("GMAIL_CLIENT_SECRET") or "").strip()
        if refresh and client_id and client_secret:
            creds = Credentials(
                token=None,
                refresh_token=refresh,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=client_id,
                client_secret=client_secret,
                scopes=SEND_SCOPES,
            )
    if not creds:
        return None
    if not creds.valid:
        if not creds.refresh_token:
            return None
        try:
            creds.refresh(Request())
        except Exception:
            creds = Credentials(
                token=None,
                refresh_token=creds.refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=creds.client_id,
                client_secret=creds.client_secret,
                scopes=SEND_SCOPES,
            )
            creds.refresh(Request())
    HOME_TOKEN.parent.mkdir(parents=True, exist_ok=True)
    HOME_TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return creds


def _gmail_service():
    creds = _creds()
    if creds is None or not creds.valid:
        return None
    from googleapiclient.discovery import build

    try:
        import httplib2
        from google_auth_httplib2 import AuthorizedHttp

        http = AuthorizedHttp(creds, http=httplib2.Http(timeout=GMAIL_HTTP_TIMEOUT))
        return build("gmail", "v1", http=http, cache_discovery=False)
    except Exception:
        return build("gmail", "v1", credentials=creds, cache_discovery=False)


def connect_interactive() -> dict[str, Any]:
    """Open a browser. Sign in as sales@beosystem.com and allow Gmail."""
    if not OAUTH.is_file():
        return {"ok": False, "error": "חסר gmail-oauth.json ב-secrets"}
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        return {
            "ok": False,
            "error": "חסרות חבילות Google. הרץ: pip install google-auth-oauthlib google-api-python-client",
        }
    flow = InstalledAppFlow.from_client_secrets_file(str(OAUTH), CONNECT_SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    TOKEN.parent.mkdir(parents=True, exist_ok=True)
    TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return {"ok": True, "message": "Gmail מחובר. אישור ב-Beo OS ישלח מ-sales@beosystem.com"}


def _html_anchor(url: str, label: str) -> str:
    href = html_mod.escape(url.rstrip(".,);"), quote=True)
    safe_label = html_mod.escape(label)
    return (
        f'<a href="{href}" style="color:#1a73e8;text-decoration:underline">{safe_label}</a>'
    )


def body_to_html(body: str) -> str:
    """RTL HTML: headers bold, blank lines as space, URLs clickable."""
    header_marks = ("💼 ", "📱 ")
    header_titles = ("השירותים שלנו", "דרכי התקשרות")
    chunks: list[str] = []
    for raw in (body or "").split("\n"):
        line = raw.rstrip()
        if not line.strip():
            chunks.append('<div style="height:12px;line-height:12px">&nbsp;</div>')
            continue

        def _url_sub(match: re.Match[str]) -> str:
            url = match.group(1)
            label = "beosystem.com" if "beosystem.com" in url.lower() else url
            return _html_anchor(url, label)

        escaped = html_mod.escape(line)
        escaped = re.sub(r"(https?://[^\s<]+)", _url_sub, escaped)
        escaped = re.sub(
            r'(?<!://)(?<![">])\bbeosystem\.com\b',
            _html_anchor("https://beosystem.com", "beosystem.com"),
            escaped,
            flags=re.I,
        )
        stripped = line.strip()
        is_header = stripped.startswith(header_marks) or stripped in header_titles
        is_url = stripped.startswith("http") or stripped.lower() in {"beosystem.com"}
        if is_header:
            chunks.append(
                '<div style="margin:16px 0 4px;font-weight:700;font-size:15px;'
                f'color:#202124">{escaped}</div>'
            )
        elif is_url:
            chunks.append(f'<div style="margin:2px 0 12px">{escaped}</div>')
        else:
            chunks.append(
                f'<div style="margin:0 0 3px;color:#202124">{escaped}</div>'
            )
    inner = "\n".join(chunks)
    return (
        '<div dir="rtl" style="font-family:Arial,Helvetica,sans-serif;'
        'font-size:15px;line-height:1.7;color:#202124">'
        f"{inner}</div>"
    )


def _strip_html(html: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html or "", flags=re.I)
    text = re.sub(r"</p>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return html_mod.unescape(text).strip()


def _constrain_signature_html(html: str) -> str:
    """Email clients ignore outer CSS — shrink banner images to signature size."""
    html = html or ""

    def _img(match: re.Match[str]) -> str:
        inner = match.group(0)[4:].rstrip()
        if inner.endswith("/>"):
            inner = inner[:-2]
        elif inner.endswith(">"):
            inner = inner[:-1]
        rest = re.sub(
            r"\s(width|height)\s*=\s*(\"[^\"]*\"|'[^']*'|\S+)",
            "",
            inner,
            flags=re.I,
        )
        style = (
            "max-width:480px;width:100%;height:auto;max-height:88px;"
            "display:block;border:0;outline:none;"
        )
        if re.search(r"\bstyle\s*=", rest, re.I):
            rest = re.sub(
                r"\bstyle\s*=\s*(\"|')(.*?)\1",
                lambda s: f"style={s.group(1)}{s.group(2)};{style}{s.group(1)}",
                rest,
                count=1,
                flags=re.I | re.S,
            )
        else:
            rest = f' style="{style}"{rest}'
        return f"<img{rest}>"

    html = re.sub(r"<img\b[^>]*>", _img, html, flags=re.I | re.S)
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        'width="480" style="max-width:480px;width:100%;border-collapse:collapse;">'
        '<tr><td style="max-width:480px;line-height:0;font-size:0;">'
        f"{html}</td></tr></table>"
    )


def _send_as_signature(service: Any, from_email: str) -> str:
    """Gmail UI signatures are not added to API mail unless we append them."""
    mailbox = (from_email or "").strip()
    now = time.time()
    cached = _SIG_CACHE.get(mailbox.lower())
    if cached and now - cached[0] < _SIG_TTL:
        return cached[1]
    html = ""
    try:
        data = (
            service.users()
            .settings()
            .sendAs()
            .get(userId="me", sendAsEmail=mailbox)
            .execute()
        )
        html = str(data.get("signature") or "").strip()
    except Exception:
        html = ""
    if not html:
        try:
            listing = service.users().settings().sendAs().list(userId="me").execute()
            for row in listing.get("sendAs") or []:
                candidate = str(row.get("signature") or "").strip()
                if candidate and (
                    str(row.get("sendAsEmail") or "").lower() == mailbox.lower()
                    or row.get("isDefault")
                    or row.get("isPrimary")
                ):
                    html = candidate
                    break
            if not html:
                for row in listing.get("sendAs") or []:
                    candidate = str(row.get("signature") or "").strip()
                    if candidate:
                        html = candidate
                        break
        except Exception:
            html = ""
    if html:
        html = _constrain_signature_html(html)
        _SIG_CACHE[mailbox.lower()] = (now, html)
    return html


def send_mail(
    *,
    to_email: str,
    subject: str,
    body: str,
    from_email: str,
    from_name: str,
) -> dict[str, Any]:
    to_email = (to_email or "").strip()
    if not to_email or "@" not in to_email:
        return {"ok": False, "error": "אין כתובת נמען"}
    try:
        creds = _creds()
    except Exception as exc:
        text = str(exc)
        if "invalid_scope" in text.lower():
            return {
                "ok": False,
                "error": "Gmail דחה הרשאה ישנה. רעננו ושלחו שוב.",
            }
        return {"ok": False, "error": text[:400]}
    if creds is None or not creds.valid:
        return {
            "ok": False,
            "error": "Gmail לא מחובר. הרץ scripts/connect-gmail.ps1 והתחבר עם sales@beosystem.com",
        }
    with GMAIL_LOCK:
        try:
            service = _gmail_service()
            if service is None:
                return {"ok": False, "error": "Gmail לא מחובר"}
            signature_html = _send_as_signature(service, from_email)
            html = body_to_html(body or "")
            text = body or ""
            if signature_html:
                html = (
                    f"{html}"
                    '<div style="margin-top:24px;padding-top:12px;'
                    'border-top:1px solid #e8eaed">'
                    f"{signature_html}</div>"
                )
                sig_text = _strip_html(signature_html)
                if sig_text:
                    text = f"{text.rstrip()}\n\n{sig_text}"

            msg = EmailMessage()
            msg["To"] = to_email
            msg["From"] = f"{from_name} <{from_email}>"
            msg["Subject"] = subject or "(ללא נושא)"
            msg.set_content(text, charset="utf-8")
            msg.add_alternative(html, subtype="html", charset="utf-8")
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
            sent = (
                service.users()
                .messages()
                .send(userId="me", body={"raw": raw})
                .execute()
            )
            return {
                "ok": True,
                "gmail_id": sent.get("id"),
                "gmail_thread_id": sent.get("threadId"),
            }
        except Exception as exc:
            text = str(exc)
            if "invalid_scope" in text.lower():
                return {
                    "ok": False,
                    "error": "Gmail דחה הרשאה ישנה. רעננו ושלחו שוב — בלי חיבור מחדש.",
                }
            return {"ok": False, "error": text[:400]}


def _extract_addr(from_raw: str) -> str:
    import re

    m = re.search(r"<([^>]+)>", from_raw or "")
    return ((m.group(1) if m else from_raw) or "").strip().lower()


def _classify_reply(subject: str, snippet: str, from_email: str = "") -> str:
    frm = (from_email or "").lower()
    blob = f"{frm} {subject} {snippet}".lower()
    bounce_from = (
        "mailer-daemon",
        "postmaster@",
        "mail-daemon",
        "nobody@",
        "bounce@",
        "delivery-status",
    )
    if any(x in frm for x in bounce_from):
        return "bounced"
    if any(
        m in blob
        for m in (
            "undeliverable",
            "undelivered",
            "delivery status",
            "delivery failure",
            "failure notice",
            "returned to sender",
            "address not found",
            "user unknown",
            "mailbox not found",
            "doesn't exist",
            "does not exist",
            "recipient address rejected",
            "550 5.1.1",
            "5.1.1",
            "לא ניתן למסור",
            "נמען לא נמצא",
            "הכתובת לא קיימת",
            "כתובת שגויה",
            "כתובת לא נכונה",
            "מצב מסירה",
            "הודעת מצב מסירה",
            "mail delivery subsystem",
            "delivery status notification",
        )
    ):
        return "bounced"
    if any(
        m in blob
        for m in (
            "out of office",
            "automatic reply",
            "auto-reply",
            "חופשה",
            "מענה אוטומטי",
            "vacation",
            "ooo",
            "נעדר",
        )
    ):
        return "ooo"
    if any(
        m in blob
        for m in (
            "לא מעוניין",
            "לא רלוונטי",
            "הסירו",
            "unsubscribe",
            "remove me",
            "stop mailing",
        )
    ):
        return "not_interested"
    return "human"


def find_inbox_replies(sent_by_email: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Match inbox messages to sent outreach. Never logs message bodies."""
    with GMAIL_LOCK:
        try:
            service = _gmail_service()
            if service is None:
                return []
            listed = (
                service.users()
                .messages()
                .list(userId="me", q="in:inbox newer_than:21d -from:me", maxResults=15)
                .execute()
            )
            raw_msgs: list[dict[str, Any]] = []
            for msg_ref in listed.get("messages") or []:
                try:
                    raw_msgs.append(
                        service.users()
                        .messages()
                        .get(
                            userId="me",
                            id=msg_ref["id"],
                            format="metadata",
                            metadataHeaders=["From", "Subject"],
                        )
                        .execute()
                    )
                except Exception:
                    continue
        except Exception:
            return []

    hits: list[dict[str, Any]] = []
    seen_items: set[str] = set()
    for msg in raw_msgs:
        headers = {
            str(h.get("name") or "").lower(): str(h.get("value") or "")
            for h in (msg.get("payload") or {}).get("headers") or []
        }
        from_email = _extract_addr(headers.get("from") or "")
        thread_id = str(msg.get("threadId") or "")
        row = sent_by_email.get(from_email) if from_email else None
        if row is None and thread_id:
            for candidate in sent_by_email.values():
                if str(candidate.get("gmail_thread_id") or "") == thread_id:
                    row = candidate
                    break
        if row is None:
            continue
        item_id = str(row.get("id") or "")
        if not item_id or item_id in seen_items:
            continue
        seen_items.add(item_id)
        snippet = str(msg.get("snippet") or "")[:180]
        hits.append(
            {
                "item_id": item_id,
                "reply_kind": _classify_reply(
                    headers.get("subject") or "", snippet, from_email
                ),
                "reply_preview": snippet,
                "gmail_thread_id": thread_id,
            }
        )
    return hits


def sent_by_recipient() -> dict[str, dict[str, str]]:
    """Most recent Sent message per recipient email. Used to close stuck approval cards."""
    with GMAIL_LOCK:
        try:
            service = _gmail_service()
            if service is None:
                return {}
            listed = (
                service.users()
                .messages()
                .list(userId="me", q="in:sent newer_than:21d", maxResults=40)
                .execute()
            )
            raw_msgs: list[dict[str, Any]] = []
            for msg_ref in listed.get("messages") or []:
                try:
                    raw_msgs.append(
                        service.users()
                        .messages()
                        .get(
                            userId="me",
                            id=msg_ref["id"],
                            format="metadata",
                            metadataHeaders=["To", "Subject"],
                        )
                        .execute()
                    )
                except Exception:
                    continue
        except Exception:
            return {}
    out: dict[str, dict[str, str]] = {}
    for msg in raw_msgs:
        headers = {
            str(h.get("name") or "").lower(): str(h.get("value") or "")
            for h in (msg.get("payload") or {}).get("headers") or []
        }
        to_email = _extract_addr(headers.get("to") or "")
        if not to_email or to_email in out:
            continue
        out[to_email] = {
            "gmail_id": str(msg.get("id") or ""),
            "gmail_thread_id": str(msg.get("threadId") or ""),
        }
    return out
