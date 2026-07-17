#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["playwright>=1.40.0"]
# ///
"""Generate the Open Graph share image (index-preview.png, 2400x1260 @2x = 1200x630).

Captures the top of the desktop layout (header + first rows of quartet cards), which
is what a link-preview card should show. Run with the local server on :8000:

    python3 -m http.server 8000 &
    uv run tools/make-og.py
"""
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path(__file__).parent.parent / "index-preview.png"
W, H, SCALE = 1200, 630, 2

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=SCALE)
    pg.goto("http://localhost:8000/", wait_until="networkidle")
    pg.wait_for_selector(".quartets-container", timeout=15000)
    pg.wait_for_timeout(500)
    pg.screenshot(path=str(OUT), clip={"x": 0, "y": 0, "width": W, "height": H})
    b.close()

print(f"✓ wrote {OUT} ({W*SCALE}x{H*SCALE})")
