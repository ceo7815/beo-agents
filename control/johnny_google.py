"""Google Calendar (master) + ceo@ Gmail for Johnny. Never uses Shay sales@ tokens."""

from __future__ import annotations

import base64
import json
import os
from email.message import EmailMessage
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
TOKEN = REPO / "agents" / "johnny-beo" / "secrets" / "google-token.json"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar",
]


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def connected() -> dict[str, bool]:
    has_refresh = bool(_env("CEO_GMAIL_REFRESH_TOKEN") or TOKEN.is_file())
    return {
        "gmail": has_refresh,
        "calendar": has_refresh,
    }


def _creds():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    refresh = _env("CEO_GMAIL_REFRESH_TOKEN")
    client_id = _env("GMAIL_CLIENT_ID")
    client_secret = _env("GMAIL_CLIENT_SECRET")
    if TOKEN.is_file():
        data = json.loads(TOKEN.read_text(encoding="utf-8"))
        creds = Credentials.from_authorized_user_info(data, SCOPES)
    elif refresh and client_id and client_secret:
        creds = Credentials(
            token=None,
            refresh_token=refresh,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=SCOPES,
        )
    else:
        return None
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds if creds and creds.valid else None


def create_calendar_event(
    *,
    title: str,
    start_date: str,
    start_time: str = "10:00",
    end_time: str = "",
    location: str = "",
    description: str = "",
    meet: bool = False,
) -> dict[str, Any]:
    creds = _creds()
    if creds is None:
        return {"ok": False, "error": "יומן Google לא מחובר. צריך טוקן של ceo@ עם Calendar."}
    try:
        from googleapiclient.discovery import build
    except ImportError:
        return {"ok": False, "error": "חסרה חבילת google-api-python-client"}

    start_hm = (start_time or "10:00")[:5]
    if end_time:
        end_hm = end_time[:5]
    else:
        hh, mm = start_hm.split(":")
        end_hm = f"{(int(hh) + 1) % 24:02d}:{mm}"
    tz = "Asia/Jerusalem"
    body: dict[str, Any] = {
        "summary": title,
        "description": description,
        "location": location,
        "start": {"dateTime": f"{start_date}T{start_hm}:00", "timeZone": tz},
        "end": {"dateTime": f"{start_date}T{end_hm}:00", "timeZone": tz},
    }
    kwargs: dict[str, Any] = {"calendarId": _env("GOOGLE_CALENDAR_ID") or "primary", "body": body}
    if meet:
        body["conferenceData"] = {
            "createRequest": {
                "requestId": f"beo-{start_date}-{start_hm}".replace(":", ""),
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        }
        kwargs["conferenceDataVersion"] = 1
    try:
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        created = service.events().insert(**kwargs).execute()
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:400]}
    entry = (created.get("conferenceData") or {}).get("entryPoints") or []
    meet_link = ""
    for point in entry:
        if point.get("entryPointType") == "video":
            meet_link = str(point.get("uri") or "")
    return {
        "ok": True,
        "event_id": created.get("id"),
        "html_link": created.get("htmlLink"),
        "meet_link": meet_link or created.get("hangoutLink") or "",
    }


def list_mail(*, q: str = "", max_n: int = 8) -> dict[str, Any]:
    creds = _creds()
    if creds is None:
        return {"ok": False, "error": "Gmail של ceo@ לא מחובר"}
    try:
        from googleapiclient.discovery import build

        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        resp = (
            service.users()
            .messages()
            .list(userId="me", q=q or "in:inbox", maxResults=min(max_n, 15))
            .execute()
        )
        items = []
        for row in resp.get("messages") or []:
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=row["id"], format="metadata", metadataHeaders=["From", "Subject", "Date"])
                .execute()
            )
            headers = {h["name"]: h["value"] for h in (msg.get("payload") or {}).get("headers") or []}
            items.append(
                {
                    "id": row["id"],
                    "from": headers.get("From"),
                    "subject": headers.get("Subject"),
                    "date": headers.get("Date"),
                    "snippet": msg.get("snippet"),
                }
            )
        return {"ok": True, "items": items}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:400]}


def send_mail(to_email: str, subject: str, body: str) -> dict[str, Any]:
    creds = _creds()
    if creds is None:
        return {"ok": False, "error": "Gmail של ceo@ לא מחובר"}
    to_email = (to_email or "").strip()
    if "@" not in to_email:
        return {"ok": False, "error": "אין נמען"}
    try:
        from googleapiclient.discovery import build

        msg = EmailMessage()
        msg["To"] = to_email
        msg["From"] = "Beo Systems <ceo@beosystem.co.il>"
        msg["Subject"] = subject or "(ללא נושא)"
        msg.set_content(body or "", charset="utf-8")
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return {"ok": True, "gmail_id": sent.get("id")}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:400]}
