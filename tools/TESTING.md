# Test Plan for share-diff.py

This document describes how to test that `share-diff.py` works correctly in new environments (especially sandboxed environments like Claude Code web/mobile).

## Quick Test

Run the automated test script:

```bash
./tools/test-share-diff.sh
```

This will verify all functionality automatically.

## Manual Test Plan

### Prerequisites

1. **GitHub Token**: Set `GH_TOKEN` environment variable with a token that has `gist` scope
   ```bash
   export GH_TOKEN=your_github_token_here
   ```

2. **Check token is valid**:
   ```bash
   curl -H "Authorization: Bearer $GH_TOKEN" https://api.github.com/user
   ```
   Should return your GitHub user info without prompting.

### Test Cases

#### Test 1: Environment Setup ✓

**Purpose**: Verify the environment has required dependencies

**Steps**:
1. Check `GH_TOKEN` is set: `echo $GH_TOKEN`
2. Check uv is available: `uv --version`
3. Check Python 3.11+: `python3 --version`

**Expected**: All commands succeed

---

#### Test 2: Authentication Without Prompting ✓

**Purpose**: Verify script uses `GH_TOKEN` without prompting user

**Steps**:
1. Ensure `GH_TOKEN` is set
2. Run: `uv run tools/share-diff.py --help`
3. Observe no authentication prompt appears

**Expected**: Help text appears immediately, no interactive prompt

---

#### Test 3: Light Mode Report Sharing ✓

**Purpose**: Verify light mode reports upload to correct gist

**Steps**:
1. Run visual-diff.py to generate a light mode report:
   ```bash
   uv run tools/visual-diff.py test index.html
   ```
2. Share the report (no flag = light mode):
   ```bash
   uv run tools/share-diff.py
   ```
3. Note the GitHack URL in output

**Expected**:
- Script uses light mode by default (no "dark mode" label in output)
- Updates gist `836fc17f088e333c8387200498a1e434`
- Outputs: "Visual Diff Report Shared!"
- Provides GitHack URL

**Verify**:
- Visit the GitHack URL - should display the visual diff report
- Visit https://gist.github.com/jsundram/836fc17f088e333c8387200498a1e434
- Confirm gist was updated (check "Updated X minutes ago")

---

#### Test 4: Dark Mode Report Sharing ✓

**Purpose**: Verify dark mode reports upload to separate gist

**Steps**:
1. Run visual-diff.py to generate a dark mode report:
   ```bash
   uv run tools/visual-diff.py test index.html --dark
   ```
2. Share the report with `--dark` flag:
   ```bash
   uv run tools/share-diff.py --dark
   ```
3. Note the GitHack URL in output

**Expected**:
- Script uses dark mode (shows "dark mode" label)
- Updates gist `88dbd41e583cac61762e2c4e562c046f`
- Outputs: "Visual Diff Report Shared (dark mode)!"
- Provides GitHack URL

**Verify**:
- Visit the GitHack URL - should display the dark mode visual diff report
- Visit https://gist.github.com/jsundram/88dbd41e583cac61762e2c4e562c046f
- Confirm gist was updated (check "Updated X minutes ago")
- Verify light mode gist was NOT updated (timestamp should be older)

---

#### Test 5: Multiple Updates ✓

**Purpose**: Verify repeated runs update the same gist (no new gists created)

**Steps**:
1. Note the current number of your public gists:
   ```bash
   gh gist list | wc -l
   ```
2. Run `uv run tools/share-diff.py` multiple times
3. Check gist count again

**Expected**:
- Gist count remains the same (no new gists created)
- Existing gists show updated timestamps

---

#### Test 6: Error Handling ✓

**Purpose**: Verify graceful error handling

**Test 6a - No report exists**:
```bash
rm -rf diffs/report*.html
uv run tools/share-diff.py
```
**Expected**: Clear error message about missing report

**Test 6b - Invalid token** (optional, will prompt):
```bash
GH_TOKEN=invalid_token uv run tools/share-diff.py
```
**Expected**: Warning about token validation, but proceeds to try update

---

#### Test 7: Fresh Environment Simulation ✓

**Purpose**: Verify it works in a brand new environment

**Steps**:
1. Start fresh shell session: `bash`
2. Set only `GH_TOKEN`: `export GH_TOKEN=your_token`
3. Generate and share a report
4. Exit shell: `exit`

**Expected**: Everything works without any manual setup beyond `GH_TOKEN`

---

## Success Criteria

All tests pass, and:

1. ✓ Script reads `GH_TOKEN` from environment without prompting
2. ✓ Light mode reports update gist `836fc17f088e333c8387200498a1e434`
3. ✓ Dark mode reports update gist `88dbd41e583cac61762e2c4e562c046f`
4. ✓ Each mode maintains its own separate gist
5. ✓ No new gists are created on subsequent runs
6. ✓ GitHack URLs display reports correctly
7. ✓ Works in fresh environment with only `GH_TOKEN` set

## Troubleshooting

### "Token authentication failed"
- Check token is valid: `curl -H "Authorization: Bearer $GH_TOKEN" https://api.github.com/user`
- Check token has `gist` scope at https://github.com/settings/tokens

### "Gist not found (404)"
- The hard-coded gist IDs in `share-diff.py` may have been deleted
- Check lines 47-48 in `tools/share-diff.py` for current gist IDs
- Verify gists exist at:
  - https://gist.github.com/jsundram/836fc17f088e333c8387200498a1e434
  - https://gist.github.com/jsundram/88dbd41e583cac61762e2c4e562c046f

### Script prompts for token even though GH_TOKEN is set
- This should no longer happen after the authentication fix
- If it does, check that `GH_TOKEN` is actually exported: `env | grep GH_TOKEN`
- Try passing token explicitly: `uv run tools/share-diff.py --token $GH_TOKEN`

## Automated Testing

The automated test script (`test-share-diff.sh`) runs all the above tests and validates:
- Environment setup
- Token authentication
- Gist existence
- Light mode upload
- Dark mode upload
- Content verification
- Proper gist separation

Run it whenever testing in a new environment:
```bash
./tools/test-share-diff.sh
```
