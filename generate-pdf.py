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
    - qpdf installed (for linearization/optimization)
"""

import sys
import subprocess
import os
from playwright.sync_api import sync_playwright


def generate_pdf():
    """Generate the PDF"""
    print("📄 Generating Boccherini Quartets PDF...")
    print("   Loading http://localhost:8000/index.html")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        # Set viewport size for proper layout (desktop view)
        # Below 1200px width, responsive layout causes wrapping
        page.set_viewport_size({'width': 1400, 'height': 2000})

        # Navigate to the page
        page.goto('http://localhost:8000/index.html', wait_until='networkidle')

        margin = {
            'top': '0in',
            'bottom': '0in',
            'left': '0in',
            'right': '0in'
        }
        outfile = 'boccherini-quartets-temp.pdf'
        # Generate PDF with exact settings
        page.pdf(
            path=outfile,
            format='Letter',
            print_background=True,  # Enable background graphics
            tagged=False,           # Generate tagged PDF for accessibility?
            # margin=margin,        # Ignored since we are using css below.
            prefer_css_page_size=True  # Use CSS @page size settings
        )

        browser.close()

    print(f"✓ Temporary PDF generated: {outfile}")

    # Linearize the PDF using qpdf to avoid AirPrint issues.
    final_pdf = 'boccherini-quartets.pdf'
    print(f"🔄 Linearizing PDF with qpdf...")

    try:
        subprocess.run(
            ['qpdf', '--linearize', outfile, final_pdf],
            check=True,
            capture_output=True,
            text=True
        )
        print(f"✓ Linearized PDF saved to: {final_pdf}")

        # Clean up temporary file
        os.remove(outfile)
        print(f"✓ Cleaned up temporary file: {outfile}")

    except FileNotFoundError:
        print("\n⚠️  qpdf not found.")
        print("\nPlease install qpdf:")
        print("  brew install qpdf  (macOS)")
        print(f"\nTemporary PDF available at: {outfile}")
        print(f"Run manually: qpdf --linearize {outfile} {final_pdf}")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"\n⚠️  qpdf failed: {e.stderr}")
        print(f"Temporary PDF available at: {outfile}")
        sys.exit(1)


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
