"""HTTP handlers for Beo Leads pipeline (used by Beo OS)."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qs, urlparse

from leads_store import (
    STATUS_HE,
    _now,
    approvals,
    get_item,
    gmail_connected,
    overview,
    pipeline,
    set_status,
)
from leads_research import redraft_pending, run_daily
from leads_learn import extract_copy_features, infer_vertical, learn, public_state
from gmail_client import find_inbox_replies, send_mail, token_present


def _learn_quiet(*, with_llm: bool = False) -> None:
    try:
        learn(with_llm=with_llm)
    except Exception:
        pass


def _notify_reply(item_id: str, kind: str) -> None:
    try:
        from leads_telegram import notify_inbox_reply

        notify_inbox_reply(get_item(item_id), kind)
    except Exception:
        pass


def ingest_replies() -> dict[str, Any]:
    if not token_present():
        return {"ok": False, "error": "Gmail לא מחובר"}
    rows = [r for r in pipeline("sent").get("items") or [] if r.get("email")]
    mapping = {str(r.get("email") or "").strip().lower(): r for r in rows}
    hits = find_inbox_replies(mapping)
    human = 0
    ooo = 0
    not_interested = 0
    new_ids: list[str] = []
    for hit in hits:
        row = get_item(hit["item_id"])
        if not row or row.get("status") != "sent":
            continue
        kind = hit["reply_kind"]
        extra: dict[str, Any] = {
            "reply_kind": kind,
            "reply_preview": hit.get("reply_preview") or "",
            "gmail_thread_id": hit.get("gmail_thread_id") or row.get("gmail_thread_id"),
            "updated_at": _now(),
        }
        if kind == "ooo":
            extra["ooo_at"] = _now()
            extra["status_note"] = "מענה אוטומטי — מחכים לתשובה אנושית"
            set_status(hit["item_id"], "sent", extra)
            ooo += 1
            _notify_reply(hit["item_id"], "ooo")
            continue
        extra["replied_at"] = _now()
        if kind == "not_interested":
            extra["status_note"] = "ענו: לא מעוניין"
            set_status(hit["item_id"], "replied", extra)
            not_interested += 1
            _notify_reply(hit["item_id"], "not_interested")
            continue
        extra["status_note"] = "תשובה אנושית — ליד ב-Beo OS"
        set_status(hit["item_id"], "replied", extra)
        human += 1
        new_ids.append(hit["item_id"])
        _notify_reply(hit["item_id"], "human")
    out = {
        "ok": True,
        "human": human,
        "ooo": ooo,
        "not_interested": not_interested,
        "new_item_ids": new_ids,
        "items": [get_item(i) for i in new_ids if get_item(i)],
    }
    _learn_quiet(with_llm=human > 0)
    return out


def _read_json(raw: bytes) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def handle_get(path: str) -> tuple[int, dict[str, Any]]:
    parsed = urlparse(path)
    clean = parsed.path.rstrip("/") or "/"
    qs = parse_qs(parsed.query)
    if clean == "/api/leads/overview":
        data = overview()
        learned = public_state()
        data["learning_headline"] = learned.get("headline")
        data["learning_human"] = (learned.get("totals") or {}).get("human")
        data["learning_sent"] = (learned.get("totals") or {}).get("sent")
        return 200, data
    if clean == "/api/leads/pipeline":
        status = (qs.get("status") or [None])[0]
        return 200, pipeline(status)
    if clean == "/api/leads/approvals":
        return 200, approvals()
    if clean == "/api/leads/learning":
        return 200, public_state()
    if clean == "/api/leads/costs":
        from leads_usage import public_report

        return 200, public_report()
    if clean.startswith("/api/leads/items/"):
        item_id = clean.split("/")[-1]
        row = get_item(item_id)
        if not row:
            return 404, {"ok": False, "error": "פריט לא נמצא"}
        return 200, {"ok": True, "item": row, "status_labels": STATUS_HE}
    return 404, {"ok": False, "error": "not found"}


def handle_post(path: str, raw: bytes) -> tuple[int, dict[str, Any]]:
    clean = urlparse(path).path.rstrip("/")
    body = _read_json(raw)
    if clean == "/api/leads/run-daily":
        from power import leads_is_on

        if not leads_is_on():
            return 200, {"ok": False, "error": "שי כבוי — הפעילו את הסוכן מהלוח"}
        target = int(body.get("target") or 10)
        target = min(max(target, 1), 10)
        return 200, run_daily(target=target)
    if clean == "/api/leads/redraft":
        return 200, redraft_pending()
    if clean == "/api/leads/check-replies":
        return 200, ingest_replies()
    if clean == "/api/leads/learn":
        return 200, learn(with_llm=True)

    parts = clean.split("/")
    # /api/leads/items/{id}/{action}
    if len(parts) == 6 and parts[1] == "api" and parts[2] == "leads" and parts[3] == "items":
        item_id, action = parts[4], parts[5]
        row = get_item(item_id)
        if not row:
            return 404, {"ok": False, "error": "פריט לא נמצא"}
        if action == "approve":
            extra = {"approved_at": _now(), "updated_at": _now()}
            if "email_subject" in body:
                extra["email_subject"] = str(body.get("email_subject") or "")
            if "email_body" in body:
                extra["email_body"] = str(body.get("email_body") or "")
            subject = str(extra.get("email_subject") or row.get("email_subject") or "")
            mail_body = str(extra.get("email_body") or row.get("email_body") or "")
            if not gmail_connected():
                extra["status_note"] = "אושר. חסר חיבור Gmail — הרץ scripts/connect-gmail.ps1"
                result = set_status(item_id, "approved", extra)
                return (200, result) if result.get("ok") else (400, result)
            sent = send_mail(
                to_email=str(row.get("email") or ""),
                subject=subject,
                body=mail_body,
                from_email=str(row.get("from_email") or "sales@beosystem.com"),
                from_name=str(row.get("from_name") or "שי | Beo Systems"),
            )
            if not sent.get("ok"):
                extra["status_note"] = str(sent.get("error") or "שליחה נכשלה")
                result = set_status(item_id, "approved", extra)
                return 400, {
                    "ok": False,
                    "error": extra["status_note"],
                    "item": result.get("item"),
                }
            extra["sent_at"] = _now()
            extra["gmail_id"] = sent.get("gmail_id")
            extra["gmail_thread_id"] = sent.get("gmail_thread_id")
            extra["status_note"] = "נשלח מ-sales@beosystem.com"
            extra["vertical_key"] = row.get("vertical_key") or infer_vertical(row)
            extra["copy_features"] = extract_copy_features(
                subject=subject,
                body=mail_body,
                owner=str(row.get("owner_name") or ""),
                subject_b=str(row.get("email_subject_b") or ""),
                service=str(row.get("service") or ""),
                vertical_key=str(extra["vertical_key"] or ""),
                draft_source=str(row.get("draft_source") or ""),
            )
            result = set_status(item_id, "sent", extra)
            _learn_quiet(with_llm=False)
            return (200, result) if result.get("ok") else (400, result)
        if action == "reject":
            result = set_status(
                item_id,
                "rejected",
                {"rejected_at": _now(), "updated_at": _now()},
            )
            _learn_quiet(with_llm=False)
            return (200, result) if result.get("ok") else (400, result)
        if action == "edit":
            extra: dict[str, Any] = {"updated_at": _now()}
            if "email_subject" in body:
                extra["email_subject"] = str(body.get("email_subject") or "")
            if "email_body" in body:
                extra["email_body"] = str(body.get("email_body") or "")
            if "os_lead_created" in body:
                extra["os_lead_created"] = bool(body.get("os_lead_created"))
            if row.get("status") != "pending_approval":
                extra_status = str(row.get("status") or "pending_approval")
            else:
                extra_status = "pending_approval"
            result = set_status(item_id, extra_status, extra)
            return (200, result) if result.get("ok") else (400, result)
        if action == "close":
            result = set_status(
                item_id,
                "closed_no_reply",
                {"closed_at": _now(), "updated_at": _now()},
            )
            _learn_quiet(with_llm=False)
            return (200, result) if result.get("ok") else (400, result)
    return 404, {"ok": False, "error": "not found"}
