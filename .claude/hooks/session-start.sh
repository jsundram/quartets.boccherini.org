#!/bin/bash
#
# SessionStart hook for Claude Code on the web
#
# This hook ensures all dependencies are installed before the session begins:
# - GitHub CLI (gh) for gist uploads
# - qpdf for PDF linearization
# - WebKit system dependencies
# - Playwright browsers (Chromium and WebKit)
# - HTTP server on port 8000
#
# The hook runs synchronously to guarantee dependencies are ready before
# Claude attempts to run tests or visual regression checks.
#

set -euo pipefail

# Only run in remote environments (Claude Code on the web)
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# Run the existing setup script
bash "$CLAUDE_PROJECT_DIR/tools/setup-environment.sh"
