"""WhatsApp outreach drafts and one approved follow-up. Never sends without OS approval."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

from leads_store import _now, pipeline, save_item, set_status, today_il

BEO_WA_DIGITS = "33632519053"
FOLLOWUP_AFTER_HOURS = 48
MAX_FOLLOWUPS_PER_DAY = 10
FIXED_SUBJECT = "Beo Systems | הצעת שירותים"


def israel_wa_digits(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if not digits or digits == BEO_WA_DIGITS:
        return ""
    if digits.startswith("972"):
        return digits
    if digits.startswith("0") and len(digits) >= 9:
        return "972" + digits[1:]
    if len(digits) == 9 and digits[0] in "2345789":
        return "972" + digits
    return ""


def wa_me_url(phone: str, text: str) -> str:
    digits = israel_wa_digits(phone)
    if not digits:
        return ""
    return f"https://wa.me/{digits}?text={quote(text or '')}"


def _first_name(owner: str) -> str:
    name = (owner or "").strip().split()[0]
    if len(name) < 2 or not re.search(r"[א-תA-Za-z]", name):
        return ""
    return name


def whatsapp_first_body(company: str, owner: str, hook: str) -> str:
    hello = f"שלום {_first_name(owner)}," if _first_name(owner) else "שלום,"
    fact = (hook or "").strip()
    if len(fact) > 90:
        fact = fact[:87].rstrip() + "…"
    site_line = (
        f"עברתי על האתר של {company} — {fact}"
        if fact
        else f"עברתי על האתר של {company}."
    )
    return (
        f"{hello}\n"
        "כאן שי מ-Beo Systems.\n"
        f"{site_line}\n"
        "יש דקה לשלוח וואטסאפ או מייל על מה שחוזר אצלכם כל יום?"
    )


def whatsapp_followup_body(company: str, owner: str) -> str:
    hello = f"שלום {_first_name(owner)}," if _first_name(owner) else "שלום,"
    brand = (company or "העסק").strip() or "העסק"
    return (
        f"{hello}\n"
        "כאן שי מ-Beo.\n"
        f"שלחתי מייל ל-{brand} — רק לוודא שהגיע.\n"
        "יש דקה?"
    )


def followup_email_body(owner: str) -> str:
    hello = f"שלום {_first_name(owner)}," if _first_name(owner) else "שלום,"
    return (
        f"{hello}\n"
        "\n"
        "רק לוודא שהמייל הקודם הגיע.\n"
        "\n"
        "אם יש אצלכם כאב שחוזר כל יום — וואטסאפ, הצעות, תיקים — תגידו בשורה.\n"
        "\n"
        "שי"
    )


def attach_whatsapp(item: dict[str, Any]) -> dict[str, Any]:
    """Fill prospect WhatsApp draft. Beo wa.me stays on whatsapp_url for the email."""
    phone = str(item.get("phone") or "")
    kind = str(item.get("draft_kind") or "first")
    company = str(item.get("company") or "")
    owner = str(item.get("owner_name") or "")
    hook = str(item.get("site_hook") or "")
    if kind == "followup":
        body = str(item.get("whatsapp_body") or "") or whatsapp_followup_body(company, owner)
    else:
        body = str(item.get("whatsapp_body") or "") or whatsapp_first_body(company, owner, hook)
    item["whatsapp_body"] = body
    item["whatsapp_to_url"] = wa_me_url(phone, body)
    return item


def _parse_utc(stamp: str) -> datetime | None:
    raw = (stamp or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _is_followup(row: dict[str, Any]) -> bool:
    return str(row.get("draft_kind") or "first") == "followup"


def _parent_ids_with_child() -> set[str]:
    out: set[str] = set()
    for row in pipeline().get("items") or []:
        parent = str(row.get("parent_id") or "")
        if parent:
            out.add(parent)
    return out


def queue_followups(*, min_hours: int = FOLLOWUP_AFTER_HOURS) -> dict[str, Any]:
    """Create one pending follow-up per sent-no-reply mail. Does not send."""
    day = today_il()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=min_hours)
    already = _parent_ids_with_child()
    today_followups = 0
    queued = 0
    skipped = 0
    for row in pipeline().get("items") or []:
        if str(row.get("batch_date") or "") == day and _is_followup(row):
            today_followups += 1
    room = max(0, MAX_FOLLOWUPS_PER_DAY - today_followups)
    if room == 0:
        return {"ok": True, "queued": 0, "message": "כבר יש מספיק פולואפים להיום"}

    for row in pipeline("sent").get("items") or []:
        if queued >= room:
            break
        if _is_followup(row):
            skipped += 1
            continue
        item_id = str(row.get("id") or "")
        if not item_id or item_id in already or row.get("followup_queued"):
            skipped += 1
            continue
        if not row.get("email"):
            skipped += 1
            continue
        sent_at = _parse_utc(str(row.get("sent_at") or ""))
        if sent_at is None or sent_at > cutoff:
            skipped += 1
            continue
        child = _build_followup(row)
        save_item(child)
        set_status(
            item_id,
            "sent",
            {"followup_queued": True, "followup_id": child["id"], "updated_at": _now()},
        )
        queued += 1

    return {
        "ok": True,
        "queued": queued,
        "skipped": skipped,
        "message": f"הוכנו {queued} פולואפים לאישור" if queued else "אין פולואפים חדשים",
    }


def _build_followup(parent: dict[str, Any]) -> dict[str, Any]:
    owner = str(parent.get("owner_name") or "")
    company = str(parent.get("company") or "")
    orig_subject = str(parent.get("email_subject") or FIXED_SUBJECT).strip() or FIXED_SUBJECT
    subject = orig_subject if orig_subject.lower().startswith("re:") else f"Re: {orig_subject}"
    item = {
        "id": str(uuid.uuid4()),
        "company": company,
        "website": parent.get("website") or "",
        "domain": parent.get("domain") or "",
        "email": parent.get("email"),
        "phone": parent.get("phone") or "",
        "owner_name": owner,
        "vertical_key": parent.get("vertical_key") or "",
        "score": parent.get("score") or 0,
        "score_parts": parent.get("score_parts") or {},
        "score_why": "פולואפ — נשלח ולא חזרה תשובה. אישור אנושי לפני שליחה.",
        "site_hook": parent.get("site_hook") or "",
        "service": parent.get("service") or "",
        "draft_source": "followup",
        "draft_kind": "followup",
        "parent_id": parent.get("id"),
        "gmail_thread_id": parent.get("gmail_thread_id") or "",
        "parent_gmail_id": parent.get("gmail_id") or "",
        "status": "pending_approval",
        "email_subject": subject,
        "email_subject_b": "",
        "email_body": followup_email_body(owner),
        "from_name": parent.get("from_name") or "שי | Beo Systems",
        "from_email": parent.get("from_email") or "sales@beosystem.com",
        "whatsapp_url": parent.get("whatsapp_url") or "",
        "created_at": _now(),
        "updated_at": _now(),
        "batch_date": today_il(),
        "approved_at": None,
        "rejected_at": None,
        "sent_at": None,
    }
    return attach_whatsapp(item)


def cancel_open_followups(parent_id: str, note: str) -> int:
    n = 0
    pid = str(parent_id or "")
    if not pid:
        return 0
    for row in pipeline().get("items") or []:
        if str(row.get("parent_id") or "") != pid:
            continue
        if row.get("status") not in {"pending_approval", "approved"}:
            continue
        if row.get("gmail_id") or row.get("sent_at"):
            continue
        set_status(
            str(row.get("id") or ""),
            "closed_no_reply",
            {"closed_at": _now(), "updated_at": _now(), "status_note": note},
        )
        n += 1
    return n


def phones_from_html(html: str, text: str) -> str:
    found: list[str] = []
    blob = f"{html or ''} {text or ''}"
    for m in re.finditer(r"href=['\"]tel:([^'\"]+)", blob, re.I):
        found.append(m.group(1))
    for m in re.finditer(
        r"(?:0(?:[2-478]|5\d)[-\s]?\d{3}[-\s]?\d{4}|\+972[-\s]?\d{1,2}[-\s]?\d{3}[-\s]?\d{4})",
        blob,
    ):
        found.append(m.group(0))
    mobiles = [p for p in found if israel_wa_digits(p).startswith("9725")]
    if mobiles:
        return mobiles[0]
    for raw in found:
        if israel_wa_digits(raw):
            return raw
    return ""


def hiring_intent(page_text: str) -> bool:
    blob = page_text or ""
    needles = (
        "דרוש",
        "דרושים",
        "דרושה",
        "רכז לידים",
        "מנהל לידים",
        "we're hiring",
        "we are hiring",
        "join our team",
    )
    return any(n.lower() in blob.lower() if n.isascii() else n in blob for n in needles)


if __name__ == "__main__":
    assert israel_wa_digits("050-123-4567") == "972501234567"
    assert israel_wa_digits("+972 50 123 4567") == "972501234567"
    assert israel_wa_digits("33632519053") == ""
    assert hiring_intent("דרושים רכז לידים למשרד")
    print("leads_outreach ok")
