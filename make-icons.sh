#!/bin/bash
# Regenerate PNG icons from the SVG sources. Requires librsvg (rsvg-convert) + pngquant.
#   brew install librsvg pngquant
# Run from the repo root:  ./make-icons.sh
set -euo pipefail
cd "$(dirname "$0")"

gen() {  # gen <size> <src.svg> <out.png>
  rsvg-convert -w "$1" -h "$1" "$2" -o "$3"
  pngquant --force --skip-if-larger --output "$3" -- "$3" || true
}

gen 16  favicon.svg        favicon-16.png
gen 32  favicon.svg        favicon-32.png
gen 180 favicon.svg        apple-touch-icon.png
gen 192 favicon.svg        icon-192.png
gen 512 favicon.svg        icon-512.png
gen 512 icon-maskable.svg  icon-maskable-512.png

echo "✓ icons regenerated"
