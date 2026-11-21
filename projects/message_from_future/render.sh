#!/usr/bin/env bash
# Re-render "I Received a Message From My Future Self" (about 5-10 min on a 4-core CPU).
set -euo pipefail
cd "$(dirname "$0")"
python3 ../../.claude/skills/phone-horror-short/scripts/render_story.py story.json --out build "$@"
