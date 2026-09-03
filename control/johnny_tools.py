"""Johnny tools — Beo OS, specialists, calendar, mail, invoices."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from johnny_os import (
    actor,
    finance,
    os_connected,
    os_create,
    os_delete,
    os_get,
    os_update,
    resolve_actor_id,
)
from johnny_store import add_memory, log_action, rivhit_connected, set_pending

IL = timezone(timedelta(hours=3))

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "os_search",
            "description": "חיפוש ב-Beo OS. entity: tasks, leads, clients, projects, meetings, campaigns, suppliers, deals, users, hostingrecords, invoices, docs",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity": {"type": "string"},
                    "q": {"type": "string"},
                    "status": {"type": "string"},
                    "assigneeId": {"type": "string"},
                    "ownerId": {"type": "string"},
                    "clientId": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["entity"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "os_get",
            "description": "רשומה אחת לפי id",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity": {"type": "string"},
                    "id": {"type": "string"},
                },
                "required": ["entity", "id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "os_create",
            "description": "מבקש ליצור ב-Beo OS (משימה, ליד, לקוח, פרויקט, פגישה…). לא רץ עד שאור לוחץ מאשר.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity": {"type": "string"},
                    "data": {"type": "object"},
                },
                "required": ["entity", "data"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "os_update",
            "description": "מבקש עדכון רשומה ב-Beo OS. רץ רק אחרי מאשר של אור.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity": {"type": "string"},
                    "id": {"type": "string"},
                    "data": {"type": "object"},
                },
                "required": ["entity", "id", "data"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_delete",
            "description": "מחיקה דורשת אישור. שומר טיוטה ומציג כפתורי מאשר / לא מאשר.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity": {"type": "string"},
                    "id": {"type": "string"},
                    "label": {"type": "string"},
                },
                "required": ["entity", "id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "today_brief",
            "description": "תמונת מצב: משימות להיום, לידים חדשים, פגישות היום, שי ועדי",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finance_glance",
            "description": "קריאה בלבד לכספים ב-Beo OS",
            "parameters": {
                "type": "object",
                "properties": {"month": {"type": "string", "description": "YYYY-MM"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "specialists_board",
            "description": "מה אצל שי (לידים קרים) ואצל עדי (סושיאל)",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_specialist_approve",
            "description": "מבקש אישור לאשר לשי לשלוח מייל או לעדי לפרסם. אחרי מאשר של אור.",
            "parameters": {
                "type": "object",
                "properties": {
                    "who": {"type": "string", "enum": ["shay", "adi"]},
                    "id": {"type": "string"},
                    "immediate": {"type": "boolean"},
                    "summary": {"type": "string"},
                },
                "required": ["who", "id", "summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_list",
            "description": "פגישות מ-Google Calendar. day=YYYY-MM-DD או ריק = מהעכשיו והלאה. כולל קישור Meet אם יש.",
            "parameters": {
                "type": "object",
                "properties": {
                    "day": {"type": "string"},
                    "max": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_create",
            "description": "מבקש לקבוע פגישה ביומן Google (מקור האמת) + שיקוף ל-Beo OS. need_meet=true מוסיף Google Meet. רץ אחרי מאשר.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "purpose": {"type": "string"},
                    "agenda": {"type": "string"},
                    "startDate": {"type": "string"},
                    "startTime": {"type": "string"},
                    "endTime": {"type": "string"},
                    "location": {"type": "string"},
                    "need_meet": {"type": "boolean"},
                    "attendees": {"type": "string", "description": "מיילים מוזמנים, מופרדים בפסיק"},
                    "clientId": {"type": "string"},
                    "leadId": {"type": "string"},
                },
                "required": ["title", "startDate"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mail_list",
            "description": "רשימת מיילים אחרונים מ-ceo@",
            "parameters": {
                "type": "object",
                "properties": {"q": {"type": "string"}, "max": {"type": "integer"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mail_get",
            "description": "קריאת מייל אחד מ-ceo@ לפי id מ-mail_list",
            "parameters": {
                "type": "object",
                "properties": {"id": {"type": "string"}},
                "required": ["id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "חיפוש באינטרנט כמו ChatGPT. לחדשות, חברות, מחירים, חוקים — לא במקום Beo OS.",
            "parameters": {
                "type": "object",
                "properties": {"q": {"type": "string"}},
                "required": ["q"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "קורא דף אינטרנט לפי כתובת. אחרי שמצאת קישור ב-web_search.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "זוכר עובדה על אור או על Beo לשיחות הבאות (העדפות, לקוחות, איך מדברים).",
            "parameters": {
                "type": "object",
                "properties": {"fact": {"type": "string"}},
                "required": ["fact"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rivhit_status",
            "description": "סטטוס חיבור ריווחית אונליין (הנהלת חשבונות). עתידי — עד שיהיה API.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_mail_send",
            "description": "טיוטת מייל מ-ceo@. שליחה רק אחרי אישור.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["to", "subject", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_invoice",
            "description": "חשבונית בריווחית אונליין. עתידי — לא מנפיק עד חיבור.",
            "parameters": {
                "type": "object",
                "properties": {
                    "clientId": {"type": "string"},
                    "clientName": {"type": "string"},
                    "email": {"type": "string"},
                    "taxId": {"type": "string"},
                    "description": {"type": "string"},
                    "amount": {"type": "number"},
                    "docType": {"type": "integer", "description": "320 חשבונית, 305 חשבונית-קבלה"},
                },
                "required": ["description", "amount"],
            },
        },
    },
]


def _dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)[:8000]


def _uid() -> str:
    return resolve_actor_id() or actor().get("userId") or ""


_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def _today() -> str:
    return datetime.now(timezone.utc).astimezone(IL).strftime("%Y-%m-%d")


def _ymd(value: Any, fallback: str = "") -> str:
    raw = str(value or "").strip()
    if not raw:
        return fallback
    iso = re.match(r"^(\d{4})-(\d{2})-(\d{2})", raw)
    if iso:
        return f"{iso.group(1)}-{iso.group(2)}-{iso.group(3)}"
    dmy = re.match(r"^(\d{1,2})[./](\d{1,2})[./](\d{2,4})$", raw)
    if dmy:
        day, month, year = int(dmy.group(1)), int(dmy.group(2)), dmy.group(3)
        if len(year) == 2:
            year = f"20{year}"
        return f"{year}-{month:02d}-{day:02d}"
    return fallback


def _uuid_or(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return text if _UUID.match(text) else fallback


def _fill_defaults(entity: str, data: dict[str, Any]) -> dict[str, Any]:
    uid = _uid()
    out = dict(data)
    if entity == "tasks":
        out["assigneeId"] = _uuid_or(out.get("assigneeId"), uid)
        out["dueDate"] = _ymd(out.get("dueDate"), _today())
        out.setdefault("status", "todo")
        out.setdefault("priority", "medium")
        out.setdefault("description", out.get("description") or "")
    if entity == "leads":
        out["ownerId"] = _uuid_or(out.get("ownerId"), uid)
        out.setdefault("status", "new")
    if entity == "meetings":
        out.setdefault("organizerUserId", uid)
        out.setdefault("purpose", out.get("purpose") or out.get("title") or "פגישה")
        out.setdefault("agenda", out.get("agenda") or "")
        if not isinstance(out.get("participantUserIds"), list):
            out["participantUserIds"] = []
    if entity == "projects":
        out.setdefault("ownerId", uid)
        out.setdefault("status", "active")
    if entity == "clients":
        out.setdefault("contact", out.get("contact") or out.get("name") or "")
        out.setdefault("status", out.get("status") or "active")
    return out


def _specialists() -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        from leads_store import overview as leads_ov

        out["shay"] = leads_ov()
    except Exception as exc:
        out["shay"] = {"error": str(exc)[:200]}
    try:
        from social_store import overview as social_ov

        out["adi"] = social_ov()
    except Exception as exc:
        out["adi"] = {"error": str(exc)[:200]}
    return out


def dispatch(name: str, args: dict[str, Any]) -> str:
    if not os_connected() and name.startswith("os_"):
        return _dump({"ok": False, "error": "Beo OS לא מחובר (BOT_API_KEY / BEO_OS_URL)"})

    if name == "os_search":
        entity = str(args.get("entity") or "")
        filters = {k: args[k] for k in ("q", "status", "assigneeId", "ownerId", "clientId", "limit") if args.get(k) not in (None, "")}
        result = os_get(entity, **filters)
        log_action("os_search", f"{entity} {filters}")
        return _dump(result)

    if name == "os_get":
        return _dump(os_get(str(args.get("entity") or ""), id=str(args.get("id") or "")))

    if name == "os_create":
        entity = str(args.get("entity") or "")
        data = args.get("data") if isinstance(args.get("data"), dict) else {}
        data = _fill_defaults(entity, data)
        label = str(data.get("title") or data.get("name") or entity)
        pid = set_pending(
            "os_write",
            {"op": "create", "entity": entity, "data": data, "need_meet": bool(args.get("need_meet"))},
            f"יצירת {entity}: {label}",
        )
        return _dump({"ok": True, "needs_confirm": True, "pending_id": pid, "entity": entity, "label": label})

    if name == "os_update":
        entity = str(args.get("entity") or "")
        item_id = str(args.get("id") or "")
        data = args.get("data") if isinstance(args.get("data"), dict) else {}
        pid = set_pending(
            "os_write",
            {"op": "update", "entity": entity, "id": item_id, "data": data},
            f"עדכון {entity} {item_id}",
        )
        return _dump({"ok": True, "needs_confirm": True, "pending_id": pid, "entity": entity})

    if name == "request_delete":
        entity = str(args.get("entity") or "")
        item_id = str(args.get("id") or "")
        label = str(args.get("label") or item_id)
        pid = set_pending("delete", {"entity": entity, "id": item_id}, f"מחיקת {entity} · {label}")
        return _dump({"ok": True, "needs_confirm": True, "pending_id": pid, "label": label})

    if name == "today_brief":
        today = _today()
        uid = _uid()
        if os_connected():
            tasks = os_get("tasks", assigneeId=uid, limit=50) if uid else os_get("tasks", limit=50)
            leads = os_get("leads", status="new", limit=30)
            meetings = os_get("meetings", limit=50)
            meet_today = [
                m
                for m in (meetings.get("items") or [])
                if isinstance(m, dict) and str(m.get("startDate") or "").startswith(today)
            ]
        else:
            tasks, leads, meet_today = {"items": []}, {"items": []}, []
        google_today: dict[str, Any] = {}
        try:
            from johnny_google import list_events

            google_today = list_events(day=today)
        except Exception as exc:
            google_today = {"ok": False, "error": str(exc)[:200]}
        log_action("brief", today)
        return _dump(
            {
                "ok": True,
                "date": today,
                "tasks": tasks.get("items") or [],
                "leads_new": leads.get("items") or [],
                "meetings_today": meet_today,
                "google_today": google_today.get("items") if isinstance(google_today, dict) else [],
                "specialists": _specialists(),
                "os": os_connected(),
            }
        )

    if name == "finance_glance":
        month = str(args.get("month") or "")[:7]
        return _dump(finance("inventory", month=month or None))

    if name == "specialists_board":
        return _dump({"ok": True, **_specialists()})

    if name == "request_specialist_approve":
        who = str(args.get("who") or "")
        item_id = str(args.get("id") or "")
        summary = str(args.get("summary") or "")
        pid = set_pending(
            "specialist",
            {"who": who, "id": item_id, "immediate": bool(args.get("immediate"))},
            summary,
        )
        return _dump({"ok": True, "needs_confirm": True, "pending_id": pid, "summary": summary})

    if name == "calendar_list":
        from johnny_google import list_events

        return _dump(list_events(day=str(args.get("day") or ""), max_n=int(args.get("max") or 12)))

    if name == "calendar_create":
        title = str(args.get("title") or "")
        start = str(args.get("startDate") or "")
        st = str(args.get("startTime") or "10:00")
        et = str(args.get("endTime") or "")
        meet = True if args.get("need_meet") is None else bool(args.get("need_meet"))
        payload = {
            "title": title,
            "startDate": start,
            "startTime": st,
            "endTime": et,
            "location": str(args.get("location") or ""),
            "purpose": str(args.get("purpose") or title),
            "agenda": str(args.get("agenda") or ""),
            "need_meet": meet,
            "attendees": str(args.get("attendees") or ""),
            "clientId": args.get("clientId"),
            "leadId": args.get("leadId"),
        }
        pid = set_pending(
            "calendar",
            payload,
            f"פגישה {title} {start} {st}" + (" + Meet" if meet else ""),
        )
        return _dump(
            {
                "ok": True,
                "needs_confirm": True,
                "pending_id": pid,
                "title": title,
            }
        )

    if name == "mail_list":
        from johnny_google import list_mail

        return _dump(list_mail(q=str(args.get("q") or ""), max_n=int(args.get("max") or 8)))

    if name == "mail_get":
        from johnny_google import get_mail

        return _dump(get_mail(str(args.get("id") or "")))

    if name == "web_search":
        from johnny_web import search as web_search

        result = web_search(str(args.get("q") or ""))
        log_action("web", str(args.get("q") or "")[:80])
        return _dump(result)

    if name == "web_fetch":
        from johnny_web import fetch_page

        result = fetch_page(str(args.get("url") or ""))
        log_action("fetch", str(args.get("url") or "")[:80])
        return _dump(result)

    if name == "save_memory":
        return _dump(add_memory(str(args.get("fact") or "")))

    if name == "rivhit_status":
        on = rivhit_connected()
        return _dump(
            {
                "ok": True,
                "connected": on,
                "product": "ריווחית אונליין",
                "note": None
                if on
                else "ריווחית אונליין לא מחוברת. חשבוניות לא יוצאות עד שיהיה חיבור API.",
            }
        )

    if name == "request_mail_send":
        to = str(args.get("to") or "")
        subject = str(args.get("subject") or "")
        body = str(args.get("body") or "")
        pid = set_pending("mail", {"to": to, "subject": subject, "body": body}, f"מייל אל {to}: {subject}")
        return _dump({"ok": True, "needs_confirm": True, "pending_id": pid, "to": to, "subject": subject})

    if name == "request_invoice":
        return _dump(
            {
                "ok": False,
                "needs_confirm": False,
                "error": "ריווחית אונליין עדיין לא מחוברת. לא הונפק כלום.",
            }
        )

    return _dump({"ok": False, "error": f"כלי לא מוכר: {name}"})


def execute_pending(pending: dict[str, Any]) -> str:
    kind = str(pending.get("kind") or "")
    payload = pending.get("payload") if isinstance(pending.get("payload"), dict) else {}
    if kind == "delete":
        result = os_delete(str(payload.get("entity") or ""), str(payload.get("id") or ""))
        log_action("delete", str(payload.get("id") or ""))
        return _dump(result)
    if kind == "mail":
        from johnny_google import send_mail

        result = send_mail(str(payload.get("to") or ""), str(payload.get("subject") or ""), str(payload.get("body") or ""))
        log_action("mail", str(payload.get("to") or ""))
        return _dump(result)
    if kind == "invoice":
        return _dump({"ok": False, "error": "ריווחית אונליין לא מחוברת"})
    if kind == "specialist":
        who = str(payload.get("who") or "")
        item_id = str(payload.get("id") or "")
        if who == "shay":
            from leads_api import handle_post

            code, data = handle_post(f"/api/leads/items/{item_id}/approve", b"{}")
            log_action("approve_shay", item_id)
            return _dump({"http": code, **data})
        if who == "adi":
            from social_api import handle_post

            action = "publish" if payload.get("immediate") else "approve"
            code, data = handle_post(f"/api/social/posts/{item_id}/{action}", b"{}")
            log_action("approve_adi", item_id)
            return _dump({"http": code, **data})
        return _dump({"ok": False, "error": "מי זה לא שי ולא עדי"})
    if kind == "os_write":
        op = str(payload.get("op") or "create")
        entity = str(payload.get("entity") or "")
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        if op == "update":
            result = os_update(entity, str(payload.get("id") or ""), data)
            log_action("update", f"{entity} {payload.get('id')}")
            return _dump(result)
        data = _fill_defaults(entity, data)
        if entity == "meetings":
            from johnny_google import create_calendar_event

            cal = create_calendar_event(
                title=str(data.get("title") or ""),
                start_date=str(data.get("startDate") or ""),
                start_time=str(data.get("startTime") or "10:00"),
                end_time=str(data.get("endTime") or ""),
                location=str(data.get("location") or ""),
                description=str(data.get("agenda") or data.get("purpose") or ""),
                meet=bool(payload.get("need_meet")),
                attendees=data.get("attendees"),
            )
            if cal.get("meet_link"):
                data["location"] = cal["meet_link"]
            elif cal.get("html_link"):
                data["location"] = data.get("location") or cal.get("html_link")
            result = os_create(entity, data)
            result["google"] = cal
            log_action("create", f"meetings {data.get('title')}")
            return _dump(result)
        result = os_create(entity, data)
        log_action("create", f"{entity} {data.get('title') or data.get('name') or ''}")
        return _dump(result)
    if kind == "calendar":
        from johnny_google import create_calendar_event

        title = str(payload.get("title") or "")
        start = str(payload.get("startDate") or "")
        st = str(payload.get("startTime") or "10:00")
        et = str(payload.get("endTime") or "")
        meet = bool(payload.get("need_meet"))
        cal = create_calendar_event(
            title=title,
            start_date=start,
            start_time=st,
            end_time=et,
            location=str(payload.get("location") or ""),
            description=str(payload.get("agenda") or payload.get("purpose") or ""),
            meet=meet,
            attendees=payload.get("attendees"),
        )
        uid = _uid()
        data = _fill_defaults(
            "meetings",
            {
                "title": title,
                "purpose": str(payload.get("purpose") or title),
                "agenda": str(payload.get("agenda") or ""),
                "startDate": start,
                "startTime": st,
                "endTime": et,
                "location": cal.get("meet_link") or cal.get("html_link") or payload.get("location") or "",
                "clientId": payload.get("clientId"),
                "leadId": payload.get("leadId"),
                "organizerUserId": uid,
                "participantUserIds": [],
            },
        )
        os_row = os_create("meetings", data) if os_connected() else {"ok": False, "error": "OS לא מחובר"}
        log_action("calendar", title)
        return _dump({"ok": True, "google": cal, "os": os_row})
    return _dump({"ok": False, "error": "אין פעולה ממתינה כזו"})
