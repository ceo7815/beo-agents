---
name: learn-performance
description: Record likes, comments, reach, traffic from Or and turn them into MEMORY.md lessons.
version: 1.0.0
metadata:
  hermes:
    tags: [beo, learning, analytics]
---

# Learning

Two tracks.

## How he talks (every chat)

If he corrects you, sets a default, or shows a preference — `memory` `target=user` immediately. Do not wait for likes. Examples: free-text briefs, cancel phrases, “don’t show product menus”, Instagram+Facebook by default.

If he says “כמו בפעם שעברה” — `session_search` before asking him to repeat.

## What performed (when he pastes numbers)

v1 has no Instagram/Facebook API. Or pastes numbers from the apps.

1. Match the post to a `draft_id` (or the latest draft).
2. `record_performance` with whatever he gave.
3. `performance_insights`
4. `memory` `target=memory`: platform, format, hook pattern, keep/kill.

Next brief: follow USER.md + MEMORY.md. Do more of the winners.

When Meta insights exist later, the same JSON shape is reused. Do not invent API calls now.
