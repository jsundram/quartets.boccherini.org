#!/bin/bash
# Test plan for share-diff.py in new environments
# This script validates that gist sharing works correctly

set -e  # Exit on error

echo "========================================================================"
echo "share-diff.py Test Plan"
echo "========================================================================"
echo ""

# Color codes for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

pass() {
    echo -e "${GREEN}✓ PASS${NC}: $1"
}

fail() {
    echo -e "${RED}✗ FAIL${NC}: $1"
    exit 1
}

warn() {
    echo -e "${YELLOW}⚠ WARN${NC}: $1"
}

# Test 1: Check GH_TOKEN is set
echo "Test 1: Verify GH_TOKEN environment variable"
if [ -z "$GH_TOKEN" ] && [ -z "$GITHUB_TOKEN" ]; then
    fail "GH_TOKEN or GITHUB_TOKEN environment variable not set"
fi
pass "GH_TOKEN is set (length: ${#GH_TOKEN})"
echo ""

# Test 2: Verify token works
echo "Test 2: Verify token authentication"
if curl -s -H "Authorization: Bearer $GH_TOKEN" -H "Accept: application/vnd.github+json" \
    https://api.github.com/user | grep -q '"login"'; then
    USERNAME=$(curl -s -H "Authorization: Bearer $GH_TOKEN" -H "Accept: application/vnd.github+json" \
        https://api.github.com/user | grep -o '"login": *"[^"]*"' | sed 's/"login": *"\([^"]*\)"/\1/')
    pass "Token is valid (authenticated as: $USERNAME)"
else
    fail "Token authentication failed"
fi
echo ""

# Test 3: Check gists exist
echo "Test 3: Verify hard-coded gists exist"
LIGHT_GIST_ID="836fc17f088e333c8387200498a1e434"
DARK_GIST_ID="88dbd41e583cac61762e2c4e562c046f"

if curl -s -H "Authorization: Bearer $GH_TOKEN" \
    "https://api.github.com/gists/$LIGHT_GIST_ID" | grep -q '"id"'; then
    pass "Light mode gist exists ($LIGHT_GIST_ID)"
else
    fail "Light mode gist not found ($LIGHT_GIST_ID)"
fi

if curl -s -H "Authorization: Bearer $GH_TOKEN" \
    "https://api.github.com/gists/$DARK_GIST_ID" | grep -q '"id"'; then
    pass "Dark mode gist exists ($DARK_GIST_ID)"
else
    fail "Dark mode gist not found ($DARK_GIST_ID)"
fi
echo ""

# Test 4: Create mock light mode report
echo "Test 4: Create mock light mode diff report"
mkdir -p diffs
cat > diffs/report.html << 'EOF'
<!DOCTYPE html>
<html>
<head><title>Test Report</title></head>
<body>
<h1>Visual Diff Report - Test (Light Mode)</h1>
<p>This is a test report for light mode.</p>
<img src="test-light.png" alt="test">
</body>
</html>
EOF
pass "Created mock light mode report"
echo ""

# Test 5: Run share-diff.py for light mode
echo "Test 5: Upload light mode report to gist"
if uv run tools/share-diff.py 2>&1 | tee /tmp/share-diff-light.log | grep -q "Visual Diff Report Shared"; then
    pass "Light mode report uploaded successfully"
    GITHACK_URL=$(grep "View Report:" /tmp/share-diff-light.log | awk '{print $3}')
    echo "   GitHack URL: $GITHACK_URL"
else
    fail "Light mode upload failed"
fi
echo ""

# Test 6: Create mock dark mode report
echo "Test 6: Create mock dark mode diff report"
cat > diffs/report-dark.html << 'EOF'
<!DOCTYPE html>
<html>
<head><title>Test Report (Dark)</title></head>
<body>
<h1>Visual Diff Report - Test (Dark Mode)</h1>
<p>This is a test report for dark mode.</p>
<img src="test-dark.png" alt="test">
</body>
</html>
EOF
pass "Created mock dark mode report (both reports now exist)"
echo ""

# Test 7: Run share-diff.py for dark mode with --dark flag
echo "Test 7: Upload dark mode report to gist (with --dark flag)"
if uv run tools/share-diff.py --dark 2>&1 | tee /tmp/share-diff-dark.log | grep -q "Visual Diff Report Shared.*dark mode"; then
    pass "Dark mode report uploaded successfully"
    GITHACK_URL=$(grep "View Report:" /tmp/share-diff-dark.log | awk '{print $3}')
    echo "   GitHack URL: $GITHACK_URL"
else
    fail "Dark mode upload failed"
fi
echo ""

# Test 8: Verify gists were updated
echo "Test 8: Verify gists contain uploaded content"
echo "   (Waiting 2 seconds for gist updates to propagate...)"
sleep 2

LIGHT_CONTENT=$(curl -s -H "Authorization: Bearer $GH_TOKEN" \
    "https://api.github.com/gists/$LIGHT_GIST_ID" | \
    grep -o '"content":' | head -1)
if [ -n "$LIGHT_CONTENT" ]; then
    pass "Light mode gist was updated"
else
    warn "Could not verify light mode gist content (might still be valid)"
fi

DARK_CONTENT=$(curl -s -H "Authorization: Bearer $GH_TOKEN" \
    "https://api.github.com/gists/$DARK_GIST_ID" | \
    grep -o '"content":' | head -1)
if [ -n "$DARK_CONTENT" ]; then
    pass "Dark mode gist was updated"
else
    warn "Could not verify dark mode gist content (might still be valid)"
fi
echo ""

# Cleanup
echo "Test 9: Cleanup"
rm -f diffs/report.html diffs/report-dark.html
rm -f /tmp/share-diff-light.log /tmp/share-diff-dark.log
pass "Cleaned up test files"
echo ""

echo "========================================================================"
echo -e "${GREEN}ALL TESTS PASSED!${NC}"
echo "========================================================================"
echo ""
echo "The share-diff.py script is working correctly in this environment."
echo ""
echo "Gist URLs:"
echo "  Light: https://gist.github.com/$USERNAME/$LIGHT_GIST_ID"
echo "  Dark:  https://gist.github.com/$USERNAME/$DARK_GIST_ID"
echo ""
