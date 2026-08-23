---
name: beo-visuals
description: gpt-image-2 for Beo Social. Official logo is always in brand/logo-beo.png and must be painted into the scene, never pasted as a sticker.
version: 1.1.0
metadata:
  hermes:
    tags: [beo, image, gpt-image-2, logo]
---

# Visuals

Model: OpenAI `gpt-image-2` (config.yaml). Not DALL·E. Not Flux.

## Logo library

Always `make_beo_visual` — it loads `brand/logo-beo.png` itself. Do not use `image_generate`.

Hebrew headline goes **on** the graphic (`headline_he`). Caption in Telegram is extra (hook/body/CTA/hashtags), not a replacement for on-image type.

## Integrate, do not sticker

Pass the file as the image-gen **reference**.
Prompt the mark as a physical thing in the frame: frosted on glass, painted on a wall, lit as neon, sitting on a device, reflected. Same purple `#5828A0`. Same circular lockup.

Forbidden: corner watermark, fake transparency overlay, extra ring, stretched logo, white box behind the logo.

## Canvas

Stories: 9:16, type and mark in the vertical center.
Feed 4:5 / 1:1: mark can be hero or supporting — still in the world of the image.
Facebook cover: 1640×624 feel, mark away from the left profile overlap.

## After generate

Send the image in Telegram. `save_social_pack` with `image_path`.
Copy into `home/media/` when you can.
