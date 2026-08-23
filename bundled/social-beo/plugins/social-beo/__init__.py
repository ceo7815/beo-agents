"""Beo Social — Hermes plugin registration."""

from . import gateway_cancel, preparing, publish_demo, schemas, tools


def register(ctx):
    ctx.register_tool(
        name="get_brand_assets",
        toolset="social-beo",
        schema=schemas.GET_BRAND_ASSETS,
        handler=tools.get_brand_assets,
    )
    ctx.register_tool(
        name="get_platform_specs",
        toolset="social-beo",
        schema=schemas.GET_PLATFORM_SPECS,
        handler=tools.get_platform_specs,
    )
    ctx.register_tool(
        name="save_social_pack",
        toolset="social-beo",
        schema=schemas.SAVE_SOCIAL_PACK,
        handler=tools.save_social_pack,
    )
    ctx.register_tool(
        name="make_beo_visual",
        toolset="social-beo",
        schema=schemas.MAKE_BEO_VISUAL,
        handler=tools.make_beo_visual,
    )
    ctx.register_tool(
        name="record_performance",
        toolset="social-beo",
        schema=schemas.RECORD_PERFORMANCE,
        handler=tools.record_performance,
    )
    ctx.register_tool(
        name="performance_insights",
        toolset="social-beo",
        schema=schemas.PERFORMANCE_INSIGHTS,
        handler=tools.performance_insights,
    )
    ctx.register_hook("pre_gateway_dispatch", gateway_cancel.on_pre_gateway_dispatch)
    ctx.register_hook("pre_llm_call", gateway_cancel.on_pre_llm_call)
    ctx.register_hook("pre_tool_call", preparing.on_pre_tool_call)
    ctx.register_hook("transform_llm_output", publish_demo.on_transform_llm_output)
