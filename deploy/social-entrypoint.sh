#!/bin/sh
# Copy git-tracked Adi files into the named volume, then start Hermes.
# The git tree stays read-only so xCloud can pull.
set -e
SRC="${BEO_SOCIAL_SRC:-/opt/beo-src}"
DEST="${HERMES_HOME:-/opt/data}"
mkdir -p "$DEST"
if [ -d "$SRC" ]; then
  for item in SOUL.md USER.md IDENTITY.md HEARTBEAT.md AGENTS.md config.yaml profile.yaml distribution.yaml .env.example .no-bundled-skills plugins brand skills; do
    if [ -d "$SRC/$item" ]; then
      mkdir -p "$DEST/$item"
      cp -a "$SRC/$item/." "$DEST/$item/"
    elif [ -f "$SRC/$item" ]; then
      cp -a "$SRC/$item" "$DEST/$item"
    fi
  done
fi
exec gateway run
