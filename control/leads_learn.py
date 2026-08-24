"""Beo Leads self-learning. Rebuilds from the pipeline — never invents rates."""

from __future__ import annotations

import json
import random
import re
import ssl
import urllib.request
from pathlib import Path
from typing import Any

from leads_store import _env_value, _now, pipeline, today_il

REPO = Path(__file__).resolve().parents[1]
STATE_PATH = REPO / "agents" / "leads-beo" / "home" / "learning" / "state.json"
CTX = ssl.create_default_context()

# Weak prior ≈ 5% reply rate. Stops one lucky reply from rewriting the ICP.
PRIOR_A = 2.0
PRIOR_B = 38.0
MIN_DECIDED = 3
EXPLORE_FRAC = 0.25

VERTICAL_HE = {
    "insurance": "ביטוח",
    "import": "יבוא / סיטונאות",
    "realestate": "תיווך",
    "clinics": "קליניקות",
    "mortgage": "משכנתאות",
    "invoices": "הצעות וחשבוניות",
    "social": "תוכן לרשתות",
    "generic": "כללי",
    "unknown": "לא מסווג",
}

STYLE_HE = {
    "subject:question": "כותרת שאלה",
    "subject:pain": "כותרת כאב",
    "greeting:named": "פנייה בשם פרטי",
    "greeting:generic": "שלום בלי שם",
    "length:short": "גוף קצר",
    "length:medium": "גוף בינוני",
    "length:long": "גוף ארוך",
    "draft:llm": "ניסוח ממודל",
    "draft:template": "תבנית",
    "subject:a": "כותרת א׳",
    "subject:b": "כותרת ב׳",
}


def _empty() -> dict[str, Any]:
    return {
        "updated_at": _now(),
        "learned_at": None,
        "date": today_il(),
        "headline": "עדיין אין שליחות. הלמידה מתחילה אחרי המייל הראשון שאושר.",
        "lesson": "עד שיש תשובות, שי עובד לפי גל 1: ביטוח, יבוא, תיווך, קליניקות, משכנתאות.",
        "prompt_addendum": "",
        "totals": {
            "sent": 0,
            "waiting": 0,
            "human": 0,
            "not_interested": 0,
            "closed": 0,
            "or_rejected": 0,
            "conversion": None,
        },
        "by_vertical": [],
        "by_product": [],
        "by_style": [],
        "tomorrow": [],
        "icp_boost": {},
        "query_order": [],
        "honest": True,
        "min_decided": MIN_DECIDED,
        "history": [],
    }


def load() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return _empty()
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty()
    if not isinstance(data, dict):
        return _empty()
    return data


def _write(data: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = _now()
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_PATH)


def extract_copy_features(
    *,
    subject: str,
    body: str,
    owner: str = "",
    subject_b: str = "",
    service: str = "",
    vertical_key: str = "",
    draft_source: str = "",
) -> dict[str, Any]:
    words = len([w for w in re.split(r"\s+", (body or "").strip()) if w])
    envelope = "beosystem.com"
    if envelope in (body or "").lower():
        core = (body or "").split("beosystem.com")[0]
        words = len([w for w in re.split(r"\s+", core.strip()) if w])
    named = bool(owner and owner in (body or "")[:120])
    variant = "b" if subject_b and (subject or "").strip() == subject_b.strip() else "a"
    if words <= 55:
        length = "short"
    elif words <= 80:
        length = "medium"
    else:
        length = "long"
    return {
        "vertical": vertical_key or "unknown",
        "product": service or "לא ידוע",
        "subject_style": "question" if "?" in (subject or "") else "pain",
        "subject_variant": variant,
        "named_greeting": named,
        "length": length,
        "draft_source": draft_source or "template",
        "word_count": words,
    }


def infer_vertical(row: dict[str, Any]) -> str:
    key = str(row.get("vertical_key") or "").strip()
    if key:
        return key
    feats = row.get("copy_features") or {}
    if isinstance(feats, dict) and feats.get("vertical"):
        return str(feats["vertical"])
    blob = " ".join(
        str(row.get(k) or "")
        for k in ("score_why", "service", "email_subject", "company")
    )
    checks = (
        ("ביטוח", "insurance"),
        ("יבוא", "import"),
        ("סיטונ", "import"),
        ("תיווך", "realestate"),
        ("נדל", "realestate"),
        ("קליניק", "clinics"),
        ("אסתטי", "clinics"),
        ("משכנת", "mortgage"),
        ("חשבונ", "invoices"),
        ("הצעת מחיר", "invoices"),
        ("רשתות", "social"),
        ("אינסטגרם", "social"),
    )
    for needle, vert in checks:
        if needle in blob:
            return vert
    return "unknown"


def _arm() -> dict[str, Any]:
    return {"sent": 0, "waiting": 0, "wins": 0, "losses": 0, "or_rejected": 0}


def _mean(wins: int, losses: int) -> float:
    return (PRIOR_A + wins) / (PRIOR_A + PRIOR_B + wins + losses)


def _sample(wins: int, losses: int) -> float:
    return random.betavariate(PRIOR_A + wins, PRIOR_B + losses)


def _rate(wins: int, decided: int) -> float | None:
    if decided < MIN_DECIDED:
        return None
    return wins / decided if decided else None


def _outcome(row: dict[str, Any]) -> str | None:
    status = str(row.get("status") or "")
    kind = str(row.get("reply_kind") or "")
    if status == "rejected":
        return "or_rejected"
    if status == "replied" and kind == "not_interested":
        return "not_interested"
    if status == "replied":
        return "human"
    if status == "closed_no_reply":
        return "closed"
    if status == "sent":
        return "waiting"
    return None


def _bump(store: dict[str, dict[str, Any]], key: str, outcome: str) -> None:
    if not key:
        key = "unknown"
    arm = store.setdefault(key, _arm())
    if outcome == "or_rejected":
        arm["or_rejected"] += 1
        return
    arm["sent"] += 1
    if outcome == "waiting":
        arm["waiting"] += 1
    elif outcome == "human":
        arm["wins"] += 1
    elif outcome in {"not_interested", "closed"}:
        arm["losses"] += 1


def _serialize_arms(store: dict[str, dict[str, Any]], labels: dict[str, str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, arm in store.items():
        wins = int(arm["wins"])
        losses = int(arm["losses"])
        decided = wins + losses
        mean = _mean(wins, losses)
        rows.append(
            {
                "key": key,
                "label": labels.get(key, key),
                "sent": int(arm["sent"]),
                "waiting": int(arm["waiting"]),
                "human": wins,
                "no_reply": losses,
                "or_rejected": int(arm["or_rejected"]),
                "decided": decided,
                "rate": _rate(wins, decided),
                "posterior": round(mean, 4),
                "ready": decided >= MIN_DECIDED,
            }
        )
    rows.sort(key=lambda r: (r["posterior"], r["human"], r["sent"]), reverse=True)
    return rows


def _rule_lesson(totals: dict[str, Any], verticals: list[dict[str, Any]], styles: list[dict[str, Any]]) -> str:
    sent = int(totals.get("sent") or 0)
    human = int(totals.get("human") or 0)
    if sent == 0:
        return (
            "עדיין לא נשלח מייל. אחרי אישור ב-Beo OS הלמידה מתחילה: תחום, מוצר, "
            "סגנון כותרת, פנייה בשם, ואורך הגוף."
        )
    if human == 0:
        waiting = int(totals.get("waiting") or 0)
        closed = int(totals.get("closed") or 0)
        return (
            f"נשלחו {sent}, נענו 0. "
            + (f"{waiting} עדיין ממתינים לתשובה. " if waiting else "")
            + (f"{closed} נסגרו בלי מענה. " if closed else "")
            + "אין עדיין אות שוק — ממשיכים לפי גל 1, בלי לשנות ICP לפי מזל."
        )
    ready = [v for v in verticals if v.get("ready")]
    if ready:
        top = ready[0]
        rate = top["rate"]
        rate_txt = f"{round(rate * 100)}%" if isinstance(rate, float) else "—"
        return (
            f"תחום מוביל לפי שוק: {top['label']} "
            f"({top['human']} תשובות מתוך {top['decided']}, {rate_txt}). "
            "מחר החיפוש והציון נוטים לשם, עם רבע מהחיפוש לחקירה."
        )
    style_ready = [s for s in styles if s.get("ready")]
    if style_ready:
        top = style_ready[0]
        return f"סגנון שמתחיל לבלוט: {top['label']}. ממתינים לעוד תשובות לפני שינוי ICP."
    return (
        f"יש {human} תשובות אנושיות מתוך {sent} שליחות. "
        f"מתחת ל-{MIN_DECIDED} החלטות לתא — לא משנים ICP, רק אוספים."
    )


def _llm_lesson(payload: dict[str, Any]) -> str | None:
    key = _env_value("OPENAI_API_KEY")
    if not key:
        return None
    model = _env_value("OPENAI_MODEL") or "gpt-5.6-luna"
    body = {
        "model": model,
        "max_completion_tokens": 400,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "אתה אנליסט של Beo Leads. כתוב עברית מדוברת, עובדתית, בלי סיסמאות. "
                    "החזר JSON עם שדה lesson (2–4 משפטים). "
                    "רק מה שיש במספרים. אסור להמציא אחוזים. "
                    "אם המדגם קטן — תגיד שזה מוקדם. "
                    "אל תצטט גוף מייל או שמות לקוחות."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False)[:6000],
            },
        ],
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45, context=CTX) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        try:
            from leads_usage import record_from_response

            record_from_response(raw, "learn")
        except Exception:
            pass
        text = raw["choices"][0]["message"]["content"].strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text).strip()
            text = re.sub(r"```$", "", text).strip()
        data = json.loads(text)
        lesson = str(data.get("lesson") or "").strip()
        return lesson or None
    except Exception:
        return None


def _prompt_addendum(
    verticals: list[dict[str, Any]],
    products: list[dict[str, Any]],
    styles: list[dict[str, Any]],
    lesson: str,
) -> str:
    lines = ["לקחים משוק אמיתי (רק אם יש מספרים — אחרת התעלם):"]
    lines.append(lesson)
    ready_v = [v for v in verticals if v.get("ready")]
    if ready_v:
        top = ", ".join(v["label"] for v in ready_v[:3])
        lines.append(f"תחומים שעבדו יותר: {top}.")
    weak_v = [v for v in ready_v if (v.get("rate") or 1) == 0 and v["decided"] >= MIN_DECIDED]
    if weak_v:
        lines.append("תחומים בלי מענה אחרי מדגם מספיק: " + ", ".join(v["label"] for v in weak_v[:3]) + ".")
    ready_p = [p for p in products if p.get("ready")]
    if ready_p:
        lines.append(f"מוצר Beo שמוביל: {ready_p[0]['label']}. בחר אותו כשהכאב באמת תואם — אל תדחוף אותו לכל עסק.")
    ready_s = [s for s in styles if s.get("ready")]
    if ready_s:
        lines.append("סגנון שמוביל: " + ", ".join(s["label"] for s in ready_s[:3]) + ".")
    rejected = [s for s in styles if int(s.get("or_rejected") or 0) >= 2]
    if rejected:
        lines.append("אור דחה סגנון זה יותר מפעם: " + ", ".join(s["label"] for s in rejected[:3]) + " — אל תחזור עליו.")
    lines.append("אל תמציא נתונים. אם השורה הזו ריקה ממשמעות — כתוב כמו תמיד.")
    return "\n".join(lines)


def _icp_boost(verticals: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in verticals:
        if not row.get("ready"):
            out[str(row["key"])] = 0
            continue
        mean = float(row.get("posterior") or 0.05)
        out[str(row["key"])] = int(max(-4, min(8, round((mean - 0.05) * 120))))
    return out


def _query_order(verticals: list[dict[str, Any]]) -> list[str]:
    """Thompson sample so we explore, not only exploit."""
    scored = []
    for row in verticals:
        wins = int(row.get("human") or 0)
        losses = int(row.get("no_reply") or 0)
        scored.append((str(row["key"]), _sample(wins, losses)))
    scored.sort(key=lambda x: x[1], reverse=True)
    return [k for k, _ in scored]


def _tomorrow(verticals: list[dict[str, Any]], styles: list[dict[str, Any]], boost: dict[str, int]) -> list[str]:
    notes: list[str] = []
    order = [v for v in verticals if v.get("sent") or v.get("ready")]
    if order:
        top = order[0]
        b = boost.get(str(top["key"]) or "", 0)
        if b > 0:
            notes.append(f"ציון ICP ל{top['label']} עולה ב-{b} מחר.")
        elif b < 0:
            notes.append(f"ציון ICP ל{top['label']} יורד ב-{abs(b)} — השוק לא ענה.")
    ready_s = [s for s in styles if s.get("ready")]
    if ready_s:
        notes.append(f"ברירת מחדל לניסוח: {ready_s[0]['label']}.")
    notes.append(f"{int(EXPLORE_FRAC * 100)}% מהחיפוש נשאר לחקירת תחומים עם מעט נתונים.")
    return notes


def learn(*, with_llm: bool = True) -> dict[str, Any]:
    """Rebuild posteriors from the live pipeline. Idempotent."""
    items = pipeline().get("items") or []
    by_vertical: dict[str, dict[str, Any]] = {}
    by_product: dict[str, dict[str, Any]] = {}
    by_style: dict[str, dict[str, Any]] = {}
    human_n = 0
    not_int = 0
    closed = 0
    waiting = 0
    or_rej = 0
    sent_n = 0

    for row in items:
        outcome = _outcome(row)
        if not outcome:
            continue
        feats = row.get("copy_features")
        if not isinstance(feats, dict) or not feats:
            feats = extract_copy_features(
                subject=str(row.get("email_subject") or ""),
                body=str(row.get("email_body") or ""),
                owner=str(row.get("owner_name") or ""),
                subject_b=str(row.get("email_subject_b") or ""),
                service=str(row.get("service") or ""),
                vertical_key=infer_vertical(row),
                draft_source=str(row.get("draft_source") or ""),
            )
        vertical = infer_vertical({**row, "copy_features": feats})
        product = str(feats.get("product") or row.get("service") or "לא ידוע")
        styles = [
            f"subject:{feats.get('subject_style') or 'pain'}",
            "greeting:named" if feats.get("named_greeting") else "greeting:generic",
            f"length:{feats.get('length') or 'medium'}",
            f"draft:{feats.get('draft_source') or 'template'}",
            f"subject:{feats.get('subject_variant') or 'a'}",
        ]
        _bump(by_vertical, vertical, outcome)
        _bump(by_product, product, outcome)
        for sk in styles:
            _bump(by_style, sk, outcome)
        if outcome == "or_rejected":
            or_rej += 1
            continue
        sent_n += 1
        if outcome == "waiting":
            waiting += 1
        elif outcome == "human":
            human_n += 1
        elif outcome == "not_interested":
            not_int += 1
        elif outcome == "closed":
            closed += 1

    decided = human_n + not_int + closed
    conversion = (human_n / decided) if decided >= MIN_DECIDED else None
    totals_pub = {
        "sent": sent_n,
        "waiting": waiting,
        "human": human_n,
        "not_interested": not_int,
        "closed": closed,
        "or_rejected": or_rej,
        "decided": decided,
        "conversion": conversion,
    }
    verticals = _serialize_arms(by_vertical, VERTICAL_HE)
    products = _serialize_arms(by_product, {k: k for k in by_product})
    styles = _serialize_arms(by_style, STYLE_HE)
    lesson = _rule_lesson(totals_pub, verticals, styles)
    lesson_from_llm = False
    prev = load()
    prev_human = int(((prev.get("totals") or {}).get("human")) or 0)
    if with_llm and (human_n > 0) and (human_n != prev_human or not prev.get("lesson_from_llm")):
        llm = _llm_lesson(
            {
                "totals": totals_pub,
                "verticals": verticals,
                "products": products,
                "styles": styles,
                "min_decided": MIN_DECIDED,
            }
        )
        if llm:
            lesson = llm
            lesson_from_llm = True
    boost = _icp_boost(verticals)
    order = _query_order(verticals) if verticals else list(VERTICAL_HE.keys())
    addendum = _prompt_addendum(verticals, products, styles, lesson) if sent_n else ""
    headline = lesson.split(".")[0].strip() + "." if lesson else lesson
    history = list(prev.get("history") or [])
    snap = {
        "date": today_il(),
        "sent": sent_n,
        "human": human_n,
        "conversion": conversion,
        "headline": headline,
    }
    if not history or history[-1].get("date") != snap["date"] or history[-1].get("human") != human_n:
        history.append(snap)
    history = history[-30:]

    state = {
        "ok": True,
        "updated_at": _now(),
        "learned_at": _now(),
        "date": today_il(),
        "headline": headline,
        "lesson": lesson,
        "lesson_from_llm": lesson_from_llm,
        "prompt_addendum": addendum,
        "totals": totals_pub,
        "by_vertical": verticals,
        "by_product": products,
        "by_style": styles,
        "tomorrow": _tomorrow(verticals, styles, boost),
        "icp_boost": boost,
        "query_order": order,
        "honest": True,
        "min_decided": MIN_DECIDED,
        "explore_frac": EXPLORE_FRAC,
        "history": history,
    }
    _write(state)
    return state


def public_state() -> dict[str, Any]:
    data = load()
    if not data.get("learned_at"):
        return learn(with_llm=False)
    return data


def vertical_icp_boost(vertical_key: str) -> int:
    data = load()
    boosts = data.get("icp_boost") or {}
    try:
        return int(boosts.get(vertical_key) or 0)
    except (TypeError, ValueError):
        return 0


def prompt_addendum() -> str:
    return str(load().get("prompt_addendum") or "")


def ranked_vertical_keys(default: list[str]) -> list[str]:
    data = load()
    order = [k for k in (data.get("query_order") or []) if k in default]
    for key in default:
        if key not in order:
            order.append(key)
    if order and random.random() < EXPLORE_FRAC:
        tail = order[1:]
        random.shuffle(tail)
        return order[:1] + tail
    return order or list(default)
