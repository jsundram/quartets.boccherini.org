#!/usr/bin/env bash
# Rasterize assets/og.svg -> assets/og.png (1200x630). The OG image MUST be a raster at an ABSOLUTE
# https URL (iMessage/WhatsApp/Slack reject relative paths and won't render SVG) and must stay small —
# this hard-fails if the card lands over MAX_BYTES, a margin under WhatsApp's ~300 KB scrape cutoff
# (a too-big card previews as a silent grey box). Edit assets/og.svg, then rerun.
set -euo pipefail
cd "$(dirname "$0")/../assets"
svg="${1:-og.svg}"
png="${svg%.svg}.png"

if command -v rsvg-convert >/dev/null; then
  rsvg-convert -w 1200 -h 630 "$svg" -o "$png"
else
  for c in chromium chromium-browser google-chrome "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"; do
    command -v "$c" >/dev/null 2>&1 || [ -x "$c" ] || continue
    "$c" --headless --no-sandbox --hide-scrollbars --force-device-scale-factor=1 \
         --window-size=1200,630 --screenshot="$png" "file://$PWD/$svg" 2>/dev/null
    break
  done
fi

# Compress to shave the file — scrapers skip an oversized card. pngquant preferred; oxipng is a
# lossless fallback. Neither installed -> the size gate below still runs and fails loud.
if command -v pngquant >/dev/null; then
  pngquant --force --skip-if-larger --output "$png" "$png" 2>/dev/null || true
elif command -v oxipng >/dev/null; then
  oxipng -o4 --quiet "$png" 2>/dev/null || true
fi

MAX_BYTES=250000   # keep in sync with scripts/og-lint.py
bytes=$(wc -c < "$png" | tr -d ' ')
if [ "$bytes" -gt "$MAX_BYTES" ]; then
  echo "ERROR: assets/$png is $bytes bytes (> $MAX_BYTES). Install pngquant, simplify $svg, or shrink the palette." >&2
  exit 1
fi
echo "wrote assets/$png ($bytes bytes)"
