"""Tool schemas for Beo Leads."""

LEADS_OVERVIEW = {
    "name": "leads_overview",
    "description": "Today's pipeline counts for Beo Leads (pending approvals, skipped, sent).",
    "parameters": {"type": "object", "properties": {}},
}

LEADS_PIPELINE = {
    "name": "leads_pipeline",
    "description": "List pipeline rows. Optional status filter.",
    "parameters": {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "description": "pending_approval, skipped_no_email, sent, closed_no_reply, replied, rejected, approved",
            }
        },
    },
}

RECORD_LEAD_CANDIDATE = {
    "name": "record_lead_candidate",
    "description": (
        "Save one researched company into the Beo OS pipeline. "
        "If email is empty, status must be skipped_no_email. Never invent an email."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "company": {"type": "string"},
            "website": {"type": "string"},
            "email": {"type": "string"},
            "phone": {"type": "string"},
            "score": {"type": "number"},
            "score_why": {"type": "string"},
            "service": {"type": "string"},
            "email_subject": {"type": "string"},
            "email_body": {"type": "string"},
            "skip": {"type": "boolean"},
        },
        "required": ["company", "website"],
    },
}
