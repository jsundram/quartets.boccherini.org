#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "playwright>=1.40.0",
#     "pillow>=10.0.0",
# ]
# ///
"""
Helper script to install Playwright browsers using the same dependencies as visual-diff.py.

This ensures that browsers are installed for the correct Playwright version that
visual-diff.py will actually use.
"""

import subprocess
import sys

def main():
    """Install Chromium and WebKit browsers for Playwright."""
    try:
        # Run playwright install using the current Python environment
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium", "webkit"],
            capture_output=False,
            check=True
        )
        return result.returncode
    except subprocess.CalledProcessError as e:
        print(f"Warning: Failed to install browsers: {e}", file=sys.stderr)
        return e.returncode
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
