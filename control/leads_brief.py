"""Read-only briefing pack of Beo Leads for Telegram Q&A. No actions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from leads_learn import VERTICAL_HE, public_state
from leads_store import REPO, STATUS_HE, overview, pipeline, today_il

IL = timezone(timedelta(hours=3))

_SLIM = (
    "id",
    "company",
    "email",
    "website",
    "domain",
    "city",
    "status",
    "score",
    "score_parts",
    "score_why",
    "site_hook",
    "service",
    "vertical_key",
    "owner_name",
    "email_subject",
    "email_subject_b",
    "batch_date",
    "sent_at",
    "replied_at",
    "created_at",
    "approved_at",
    "rejected_at",
    "reply_kind",
    "reply_preview",
    "skip_reason",
    "status_note",
    "phone",
    "os_lead_created",
    "draft_source",
    "copy_features",
)


def _il_date(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if len(raw) >= 10 and raw[4] == "-" and "T" not in raw[:11]:
        return raw[:10]
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.astimezone(IL).strftime("%Y-%m-%d")
    except ValueError:
        return raw[:10]


def _week_start(day: str) -> str:
    d = datetime.strptime(day, "%Y-%m-%d").date()
    # Israel work week Sun–Thu; week starts Sunday.
    start = d - timedelta(days=(d.weekday() + 1) % 7)
    return start.strftime("%Y-%m-%d")


def _slim(row: dict[str, Any]) -> dict[str, Any]:
    out = {k: row.get(k) for k in _SLIM}
    status = str(row.get("status") or "")
    out["status_he"] = STATUS_HE.get(status, status)
    vert = str(row.get("vertical_key") or "")
    out["vertical_he"] = VERTICAL_HE.get(vert, vert)
    body = str(row.get("email_body") or "")
    if body:
        out["email_body"] = body[:4500]
    preview = str(row.get("reply_preview") or "")
    if preview:
        out["reply_preview"] = preview[:1500]
    site = str(row.get("page_text") or "").strip()
    if site:
        out["site_excerpt"] = site[:700]
    out["does"] = str(row.get("site_hook") or row.get("score_why") or "").strip()
    out["day"] = (
        _il_date(str(row.get("sent_at") or ""))
        or str(row.get("batch_date") or "")
        or _il_date(str(row.get("created_at") or ""))
    )
    out["replied_day"] = _il_date(str(row.get("replied_at") or ""))
    return out


def briefing() -> dict[str, Any]:
    day = today_il()
    yesterday = (datetime.strptime(day, "%Y-%m-%d").date() - timedelta(days=1)).strftime("%Y-%m-%d")
    week_from = _week_start(day)
    month = day[:7]
    items = [_slim(r) for r in (pipeline().get("items") or [])]
    learned = public_state()
    learning = {
        "headline": learned.get("headline"),
        "lesson": learned.get("lesson"),
        "totals": learned.get("totals"),
        "by_vertical": learned.get("by_vertical"),
        "by_product": learned.get("by_product"),
        "tomorrow": learned.get("tomorrow"),
        "honest": learned.get("honest"),
        "min_decided": learned.get("min_decided"),
    }

    def in_range(row: dict[str, Any], start: str, end: str | None = None) -> bool:
        d = str(row.get("day") or "")
        if not d:
            return False
        if end:
            return start <= d <= end
        return d == start

    def pick(*statuses: str, start: str | None = None, end: str | None = None) -> list[dict[str, Any]]:
        out = []
        for row in items:
            if statuses and row.get("status") not in statuses:
                continue
            if start and not in_range(row, start, end):
                continue
            out.append(row)
        return out

    return {
        "today": day,
        "yesterday": yesterday,
        "week_from": week_from,
        "month": month,
        "overview": overview(),
        "learning": learning,
        "today_pending": pick("pending_approval", start=day),
        "today_sent": [
            r for r in items if _il_date(str(r.get("sent_at") or "")) == day
        ],
        "today_replied": [
            r for r in items if r.get("replied_day") == day
        ],
        "yesterday_sent": pick("sent", start=yesterday),
        "yesterday_replied": pick("replied", start=yesterday),
        "week_sent": pick("sent", start=week_from, end=day),
        "week_replied": pick("replied", start=week_from, end=day),
        "month_sent": pick("sent", start=f"{month}-01", end=day),
        "month_replied": pick("replied", start=f"{month}-01", end=day),
        "waiting_for_reply": pick("sent"),
        "all_replied": pick("replied"),
        "all_bounced": pick("bounced"),
        "today_bounced": [
            r
            for r in items
            if r.get("status") == "bounced"
            and _il_date(str(r.get("bounced_at") or r.get("updated_at") or "")) == day
        ],
        "closed_no_reply": pick("closed_no_reply"),
        "pending_all": pick("pending_approval"),
        "rejected": pick("rejected"),
        "customers": [
            {
                "company": r.get("company"),
                "does": r.get("does"),
                "vertical": r.get("vertical_he"),
                "service": r.get("service"),
                "score": r.get("score"),
                "why": r.get("score_why"),
                "status": r.get("status_he"),
                "email": r.get("email"),
                "owner": r.get("owner_name"),
                "subject": r.get("email_subject"),
                "replied": r.get("status") == "replied",
                "waiting": r.get("status") == "sent",
            }
            for r in items
            if r.get("company") and not str(r.get("status") or "").startswith("skipped")
        ],
        "skipped_today": [
            r
            for r in items
            if str(r.get("status") or "").startswith("skipped") and r.get("day") == day
        ],
        "catalog": items,
    }


IDENTITY = {
    "name": "שי",
    "profile": "שי | Beo Leads",
    "role": "איש הלידים של Beo Systems — סוכן Beo Leads",
    "boss": "אור, מנכ״ל Beo Systems",
    "telegram": "שיחה חופשית ועדכונים. לא שולחים ולא מאשרים מכאן.",
    "control_center": "Beo OS — שם מאשרים טיוטות ושולחים מייל",
    "never_say": "אור OS",
    "daily_job": (
        "מוצא עסקים בינוניים בישראל (8–40 איש), מייל גלוי מהאתר (כולל Gmail/Walla), "
        "טיוטה בעברית כשי, עד 10 ביום לאישור. בלי פולואפ. "
        "תשובה אנושית → ליד ב-Beo OS."
    ),
    "beo_sells": (
        "אתרים ואפליקציות, סוכני AI, מערכות ניהול, צ׳אטבוטים ואוטומציות, הטמעת AI"
    ),
}


def wants_identity(question: str) -> bool:
    q = (question or "").strip().lower()
    keys = (
        "מי אתה",
        "מי את",
        "מה אתה עושה",
        "מה התפקיד",
        "תציג את עצמך",
        "מי שי",
        "who are you",
    )
    return any(k in q for k in keys)


def wants_report(question: str) -> bool:
    q = (question or "").strip().lower()
    keys = (
        "דוח",
        "סיכום",
        "רשימה",
        "למי",
        "מי ענה",
        "מי לא",
        "כמה",
        "ציונים",
        "תן מספר",
        "מספרים",
        "/today",
        "/report",
    )
    return any(k in q for k in keys)


def _playbook() -> str:
    path = REPO / "agents" / "leads-beo" / "SOUL.md"
    try:
        return path.read_text(encoding="utf-8")[:12000]
    except OSError:
        return ""


def _learning_for_chat() -> dict[str, Any]:
    learned = public_state()
    return {
        "headline": learned.get("headline"),
        "lesson": learned.get("lesson"),
        "totals": learned.get("totals"),
        "by_vertical": learned.get("by_vertical"),
        "by_product": learned.get("by_product"),
        "by_style": learned.get("by_style"),
        "tomorrow": learned.get("tomorrow"),
        "honest": learned.get("honest"),
        "min_decided": learned.get("min_decided"),
        "query_order": learned.get("query_order"),
        "icp_boost": learned.get("icp_boost"),
    }


def _mentions(question: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    q = (question or "").strip().lower()
    if len(q) < 2:
        return []
    hits: list[dict[str, Any]] = []
    for row in items:
        blob = " ".join(
            str(row.get(k) or "")
            for k in ("company", "domain", "email", "owner_name", "website", "city")
        ).lower()
        name = str(row.get("company") or "").strip()
        if name and len(name) >= 3 and name.lower() in q:
            hits.append(row)
            continue
        tokens = [t for t in name.replace("-", " ").replace("״", "").split() if len(t) >= 4]
        if any(t.lower() in q for t in tokens) and blob:
            hits.append(row)
    return hits


def pack_for_chat(question: str) -> dict[str, Any]:
    """Every Telegram turn gets the full Beo OS Beo Leads board — like attached files."""
    full = briefing()
    items = list(full.get("catalog") or [])
    mentioned = _mentions(question, items)
    pack = {
        "who_i_am": IDENTITY,
        "board": "Beo OS → סוכני AI → Beo Leads",
        "playbook": _playbook(),
        "overview": full.get("overview"),
        "learning": _learning_for_chat(),
        "today": full.get("today"),
        "counts": {
            "all": len(items),
            "pending": len(full.get("pending_all") or []),
            "sent_today": len(full.get("today_sent") or []),
            "waiting": len(full.get("waiting_for_reply") or []),
            "replied": len(full.get("all_replied") or []),
            "rejected": len(full.get("rejected") or []),
            "skipped_today": len(full.get("skipped_today") or []),
        },
        "mentioned": mentioned,
        "files": items,
    }
    if wants_identity(question):
        pack["answer_focus"] = "identity"
    return pack


def end_of_day() -> dict[str, Any]:
    pack = briefing()
    day = str(pack.get("today") or today_il())
    sent = list(pack.get("today_sent") or [])
    waiting_all = list(pack.get("waiting_for_reply") or [])
    replied_today = list(pack.get("today_replied") or [])
    closed = list(pack.get("closed_no_reply") or [])
    pending = list(pack.get("pending_all") or [])
    bounced = list(pack.get("today_bounced") or pack.get("all_bounced") or [])
    bounced_emails = {
        str(r.get("email") or "").strip().lower() for r in bounced if r.get("email")
    }
    sent_rows = []
    waiting_from_today = []
    for row in sent:
        email = str(row.get("email") or "").strip().lower()
        did = row.get("status") == "replied" or bool(row.get("replied_day"))
        is_bounce = row.get("status") == "bounced" or email in bounced_emails
        item = {
            "company": row.get("company"),
            "email": row.get("email"),
            "replied": did,
            "bounced": is_bounce,
            "vertical": row.get("vertical_he"),
        }
        sent_rows.append(item)
        if not did and not is_bounce and row.get("status") == "sent":
            waiting_from_today.append(item)
    waiting_rows = waiting_from_today + [
        {
            "company": r.get("company"),
            "email": r.get("email"),
            "replied": False,
            "vertical": r.get("vertical_he"),
        }
        for r in waiting_all
        if _il_date(str(r.get("sent_at") or "")) != day
    ]
    return {
        "date": day,
        "sent_today": len(sent),
        "replied_today": len(replied_today),
        "waiting": len(waiting_all),
        "closed": len(closed),
        "pending": len(pending),
        "bounced_today": len(bounced),
        "sent_rows": sent_rows,
        "bounced_rows": [
            {"company": r.get("company"), "email": r.get("email")} for r in bounced
        ],
        "replied_rows": [
            {
                "company": r.get("company"),
                "kind": "לא מעוניין" if r.get("reply_kind") == "not_interested" else "תשובה",
            }
            for r in replied_today
        ],
        "waiting_rows": waiting_rows[:20],
        "pending_rows": [
            {"company": r.get("company"), "score": r.get("score")} for r in pending[:10]
        ],
    }
