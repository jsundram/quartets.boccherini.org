#!/bin/bash
#
# Environment setup script for Claude Code web
#
# Installs all dependencies needed to work with this repository:
# - Playwright browsers (Chromium and WebKit)
# - WebKit system dependencies
# - GitHub CLI (gh)
# - qpdf (for PDF linearization)
#
# Usage:
#   ./tools/setup-environment.sh
#
# This script is idempotent - safe to run multiple times.
#

set -e

# Get the project root directory (parent of tools/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# -----------------------------------------------------------------------------
# Only run in cloud sandbox environments (not on local machines)
# -----------------------------------------------------------------------------
# Cloud sandboxes typically run as root with /home/user as the workspace.
# Skip setup on local machines where the user has their own environment.

if [ "$(id -u)" != "0" ] || [ ! -d "/home/user" ]; then
    echo "Skipping setup (not in cloud sandbox environment)"
    exit 0
fi

echo "Setting up environment for Boccherini Quartets development..."
echo ""

# Track what was installed
INSTALLED=()
SKIPPED=()

# -----------------------------------------------------------------------------
# 1. GitHub CLI (gh)
# -----------------------------------------------------------------------------
echo "Checking GitHub CLI..."
if command -v gh &> /dev/null; then
    SKIPPED+=("gh (already installed: $(gh --version | head -1))")
else
    echo "  Installing gh..."
    apt-get update -qq
    apt-get install -y -qq gh
    INSTALLED+=("gh")
fi

# -----------------------------------------------------------------------------
# 2. qpdf (for PDF linearization)
# -----------------------------------------------------------------------------
echo "Checking qpdf..."
if command -v qpdf &> /dev/null; then
    SKIPPED+=("qpdf (already installed: $(qpdf --version | head -1))")
else
    echo "  Installing qpdf..."
    apt-get update -qq
    apt-get install -y -qq qpdf
    INSTALLED+=("qpdf")
fi

# -----------------------------------------------------------------------------
# 3. WebKit system dependencies (must be installed before browsers)
# -----------------------------------------------------------------------------
echo "Checking WebKit system dependencies..."

# Test if WebKit can launch by checking for missing libs
# We do this by running playwright's dependency check using Python playwright via uv
if uv run --with playwright python -m playwright install-deps webkit --dry-run 2>&1 | grep -q "apt-get install"; then
    echo "  Installing WebKit system dependencies..."
    uv run --with playwright python -m playwright install-deps webkit
    INSTALLED+=("WebKit system dependencies")
else
    SKIPPED+=("WebKit system dependencies (already satisfied)")
fi

# -----------------------------------------------------------------------------
# 4. Playwright browsers (using Python playwright via uv)
# -----------------------------------------------------------------------------
# Note: We use uv to run playwright install because the Python scripts
# (visual-diff.py, generate-pdf.py) use uv's inline script dependencies,
# which may be a different playwright version than the system Node.js one.

echo "Installing Playwright browsers for Python tools..."
echo "  (This ensures browsers match the playwright version used by visual-diff.py)"

# Install browsers using the SAME playwright version that visual-diff.py uses
# We use a helper script with identical dependencies to ensure version match
uv run "$PROJECT_ROOT/tools/install-playwright-browsers.py" 2>&1 | grep -E "(Downloading|downloaded|already installed)" || true

INSTALLED+=("Playwright browsers (matching visual-diff.py version)")

# -----------------------------------------------------------------------------
# 5. Start HTTP server if not running
# -----------------------------------------------------------------------------
echo "Checking HTTP server..."

if nc -z localhost 8000 2>/dev/null; then
    SKIPPED+=("HTTP server (already running on port 8000)")
else
    echo "  Starting HTTP server on port 8000..."
    # Start server in background, detached from this script
    cd "$PROJECT_ROOT"
    nohup python3 -m http.server 8000 > /dev/null 2>&1 &
    sleep 1
    if nc -z localhost 8000 2>/dev/null; then
        INSTALLED+=("HTTP server (started on port 8000)")
    else
        echo "  WARNING: Failed to start HTTP server"
    fi
fi

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
echo ""
echo "========================================"
echo "Environment setup complete!"
echo "========================================"

if [ ${#INSTALLED[@]} -gt 0 ]; then
    echo ""
    echo "Installed:"
    for item in "${INSTALLED[@]}"; do
        echo "  + $item"
    done
fi

if [ ${#SKIPPED[@]} -gt 0 ]; then
    echo ""
    echo "Already present:"
    for item in "${SKIPPED[@]}"; do
        echo "  - $item"
    done
fi

echo ""
echo "You can now run:"
echo "  uv run tools/visual-diff.py test index.html"
echo "  uv run tools/generate-pdf.py"
echo ""
