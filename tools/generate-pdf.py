#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "playwright>=1.40.0",
# ]
# ///

"""
Generate light and dark mode PDFs of Boccherini String Quartets visualization

Outputs:
    print.pdf      - light mode
    print-dark.pdf - dark mode

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


def linearize_pdf(temp_path, final_path):
    """Linearize a PDF using qpdf to avoid AirPrint issues."""
    print(f"🔄 Linearizing {final_path} with qpdf...")
    try:
        subprocess.run(
            ['qpdf', '--linearize', temp_path, final_path],
            check=True,
            capture_output=True,
            text=True
        )
        print(f"✓ Linearized PDF saved to: {final_path}")
        os.remove(temp_path)
        print(f"✓ Cleaned up temporary file: {temp_path}")
    except FileNotFoundError:
        print("\n⚠️  qpdf not found.")
        print("\nPlease install qpdf:")
        print("  brew install qpdf  (macOS)")
        print(f"\nTemporary PDF available at: {temp_path}")
        print(f"Run manually: qpdf --linearize {temp_path} {final_path}")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"\n⚠️  qpdf failed: {e.stderr}")
        print(f"Temporary PDF available at: {temp_path}")
        sys.exit(1)


def generate_pdf():
    """Generate light and dark mode PDFs"""
    print("📄 Generating Boccherini Quartets PDFs...")
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
        pdf_options = dict(
            format='Letter',
            print_background=True,  # Enable background graphics
            tagged=False,           # Generate tagged PDF for accessibility?
            # margin=margin,        # Ignored since we are using css below.
            prefer_css_page_size=True  # Use CSS @page size settings
        )

        # Generate light mode PDF
        light_temp = 'boccherini-quartets-temp.pdf'
        page.pdf(path=light_temp, **pdf_options)
        print(f"✓ Light mode PDF captured: {light_temp}")

        # Enable dark mode and generate dark mode PDF
        page.emulate_media(color_scheme='dark')
        page.evaluate("document.documentElement.classList.add('dark-mode')")
        dark_temp = 'boccherini-quartets-dark-temp.pdf'
        page.pdf(path=dark_temp, **pdf_options)
        print(f"✓ Dark mode PDF captured: {dark_temp}")

        browser.close()

    # Linearize both PDFs
    linearize_pdf(light_temp, 'print.pdf')
    linearize_pdf(dark_temp, 'print-dark.pdf')


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
