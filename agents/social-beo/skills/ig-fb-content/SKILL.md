---
name: ig-fb-content
description: How Beo Social writes Instagram vs Facebook copy, stories vs feed, hashtags, and Telegram previews.
version: 1.1.0
metadata:
  hermes:
    tags: [beo, instagram, facebook, copy]
---

If he already wrote the topic in free Hebrew, skip topic questions. Only `clarify` for platform/format if missing — always offer **שניהם**, and Other for typing. If USER.md already has a default (IG+FB, feed 4:5), skip those questions too.

If he cancels (בטל, טל פוסט, תפסיק, cancel) — stop. No more questions, no visual, no caption.

After he corrects how you talk or what he wants — `memory` with `target=user` in the same turn. If he mentions an older post, `session_search` first.

Need facts (calories, numbers)? `web_search` before writing. Do not invent.

When producing starts, a wait notice is sent automatically. Do not write another “please wait” line.

## Caption — short and sharp

The image is the post. Caption is a punch, not a blog.

Instagram: hook + 1–2 lines + 3–5 hashtags. No bullet list of features.
Facebook: 1–2 sentences. Skip hashtags unless one is useful.

Forbidden: long “רוצים לראות…”, 8 hashtags, two full platform essays in one bubble.

## Telegram shape under the photo

```
הוק חד
שורה אחת.
#תג #תג #BeoSystems
```

## After the last tap

Call `make_beo_visual` once with `headline_he` (the hook) and `format`. Then one Telegram message: `MEDIA:path` plus that short caption. Do not ask approval in the caption — כן / לא arrives after the photo.
