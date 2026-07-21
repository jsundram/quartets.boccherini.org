#!/usr/bin/env bash
# Rasterize assets/icon.svg -> home-screen / PWA PNGs, and assets/icon-maskable.svg -> the maskable PNG.
# assets/icon.svg is the SINGLE SOURCE OF TRUTH (square + opaque, so the apple-touch-icon isn't
# double-masked). Edit the SVG(s), then rerun this — never hand-edit the PNGs.
#   180 = apple-touch-icon   192/512 = manifest icons   512-maskable = Android adaptive (padded safe zone)
# Prefers rsvg-convert (librsvg); falls back to headless Chrome/Chromium.
set -euo pipefail
cd "$(dirname "$0")/../assets"

render() { # svg size out
  local svg="$1" size="$2" out="$3"
  if command -v rsvg-convert >/dev/null; then
    rsvg-convert -w "$size" -h "$size" "$svg" -o "$out"
    return
  fi
  for c in chromium chromium-browser google-chrome "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"; do
    command -v "$c" >/dev/null 2>&1 || [ -x "$c" ] || continue
    "$c" --headless --no-sandbox --hide-scrollbars --force-device-scale-factor=1 \
         --window-size="$size,$size" --screenshot="$out" "file://$PWD/$svg" 2>/dev/null
    return
  done
  echo "ERROR: need rsvg-convert or Chrome/Chromium to rasterize $svg" >&2
  exit 1
}

render icon.svg          180 icon-180.png
render icon.svg          192 icon-192.png
render icon.svg          512 icon-512.png
render icon-maskable.svg 512 icon-512-maskable.png
echo "wrote assets/icon-{180,192,512}.png and icon-512-maskable.png"
