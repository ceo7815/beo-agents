"""Beo Leads — Hermes plugin registration."""

from . import schemas, tools


def register(ctx):
    ctx.register_tool(
        name="leads_overview",
        toolset="leads-beo",
        schema=schemas.LEADS_OVERVIEW,
        handler=tools.leads_overview,
    )
    ctx.register_tool(
        name="leads_pipeline",
        toolset="leads-beo",
        schema=schemas.LEADS_PIPELINE,
        handler=tools.leads_pipeline,
    )
    ctx.register_tool(
        name="record_lead_candidate",
        toolset="leads-beo",
        schema=schemas.RECORD_LEAD_CANDIDATE,
        handler=tools.record_lead_candidate,
    )
