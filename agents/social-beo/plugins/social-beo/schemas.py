"""Tool schemas for Beo Social."""

GET_BRAND_ASSETS = {
    "name": "get_brand_assets",
    "description": (
        "Return the Beo Systems logo path from this agent's brand library. "
        "Call before every image so the mark is painted into the picture, not pasted as a sticker."
    ),
    "parameters": {"type": "object", "properties": {}},
}

GET_PLATFORM_SPECS = {
    "name": "get_platform_specs",
    "description": (
        "Return exact Instagram/Facebook image sizes and notes. "
        "Call before writing a post or generating an image so the canvas is correct."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "platform": {
                "type": "string",
                "description": "instagram, facebook, or empty for all",
            }
        },
    },
}

SAVE_SOCIAL_PACK = {
    "name": "save_social_pack",
    "description": (
        "Save a ready-to-send Instagram or Facebook pack (copy + size + image path) "
        "under home/drafts. Use after the Telegram preview is written."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "platform": {"type": "string", "description": "instagram or facebook"},
            "format": {
                "type": "string",
                "description": "feed_4x5, feed_1x1, story, landscape, cover",
            },
            "hook": {"type": "string"},
            "body": {"type": "string"},
            "cta": {"type": "string"},
            "hashtags": {"type": "array", "items": {"type": "string"}},
            "story_line": {"type": "string"},
            "image_prompt": {"type": "string"},
            "image_path": {"type": "string"},
            "language": {"type": "string"},
            "status": {"type": "string"},
            "notes": {"type": "string"},
            "id": {"type": "string"},
        },
        "required": ["platform", "format", "hook", "body"],
    },
}

RECORD_PERFORMANCE = {
    "name": "record_performance",
    "description": (
        "Store real post results from Or (likes, comments, reach, clicks). "
        "This is how the agent learns until Meta insights are connected."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "draft_id": {"type": "string"},
            "platform": {"type": "string"},
            "impressions": {"type": "number"},
            "reach": {"type": "number"},
            "likes": {"type": "number"},
            "comments": {"type": "number"},
            "shares": {"type": "number"},
            "saves": {"type": "number"},
            "profile_visits": {"type": "number"},
            "link_clicks": {"type": "number"},
            "notes": {"type": "string"},
        },
        "required": ["draft_id"],
    },
}

PERFORMANCE_INSIGHTS = {
    "name": "performance_insights",
    "description": "Rank stored results so the next post copies what worked.",
    "parameters": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "description": "How many best/worst rows to return"},
        },
    },
}

MAKE_BEO_VISUAL = {
    "name": "make_beo_visual",
    "description": (
        "Create ONE branded Beo graphic: official logo from brand/logo-beo.png "
        "plus Hebrew headline painted in the image. Call this once after the brief. "
        "Do not use image_generate. Do not make a second image."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "headline_he": {
                "type": "string",
                "description": "Short Hebrew hook rendered large on the graphic (RTL)",
            },
            "sub_he": {
                "type": "string",
                "description": "Optional second Hebrew line on the graphic",
            },
            "format": {
                "type": "string",
                "description": "feed_4x5, feed_1x1, story, landscape, cover",
            },
        },
        "required": ["headline_he", "format"],
    },
}
