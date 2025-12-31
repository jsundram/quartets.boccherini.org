#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "playwright>=1.40.0",
# ]
# ///

"""
Generate PDF of Boccherini String Quartets visualization

Usage:
    uv run generate-pdf.py

First-time setup (install Playwright browsers):
    uvx playwright install chromium

Requirements:
    - uv installed (https://docs.astral.sh/uv/)
    - Local server running at http://localhost:8000
"""

import sys
from playwright.sync_api import sync_playwright


def generate_pdf():
    """Generate the PDF with exact settings"""
    print("📄 Generating Boccherini Quartets PDF...")
    print("   Loading http://localhost:8000/index.html")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        # Navigate to the page
        page.goto('http://localhost:8000/index.html', wait_until='networkidle')

        # Generate PDF with exact settings
        page.pdf(
            path='boccherini-quartets.pdf',
            format='Letter',
            print_background=True,  # Enable background graphics
            margin={
                'top': '0.25in',    # Top margin for spacing
                'bottom': '0in',    # Minimum margins
                'left': '0in',
                'right': '0in'
            },
            prefer_css_page_size=True  # Use CSS @page size settings
        )

        browser.close()

    print("✓ PDF saved to: boccherini-quartets.pdf")


if __name__ == "__main__":
    try:
        generate_pdf()
    except Exception as e:
        if "Executable doesn't exist" in str(e) or "browserType.launch" in str(e):
            print("\n⚠️  Playwright browsers not installed.")
            print("\nPlease run this command first:")
            print("  uvx playwright install chromium")
            sys.exit(1)
        else:
            raise
