#!/usr/bin/env python3
"""Catch a shell change that forgot to bump the service-worker cache version.

sw.js precaches the app SHELL. An edit to any precached file only reaches installed clients when
V changes (a new V evicts the old cache on activate). Forget the bump and the fix ships to the repo
but never to anyone's home-screen copy — the single most common PWA deploy bug.

So: if this commit stages any SHELL file but leaves V identical to HEAD's, warn.

Paths in sw.js's SHELL are repo-root-relative here ("./index.html" -> index.html,
"./assets/icon-192.png" -> assets/icon-192.png), unlike the haydn/pwa-starter layout where they
sit under web/. Adapted from those repos' sw_lint.py.

The pre-commit hook runs it warn-only; run it in CI with a real exit code. By hand:
    uv run tools/sw_lint.py     (or: python3 tools/sw_lint.py)
"""
import re
import subprocess
import sys

SW = "sw.js"


def sh(*a):
    return subprocess.run(a, capture_output=True, text=True)


def ver(src):
    m = re.search(r'const V\s*=\s*"([^"]*)"', src)
    return m.group(1) if m else None


def shell_paths(src):
    m = re.search(r"const SHELL\s*=\s*\[(.*?)\]", src, re.S)
    if not m:
        return set()
    # Strip line comments before counting quoted strings: a commented-out or merely mentioned
    # filename inside the array would otherwise register as a shell entry. Same guard as
    # tools/test-pwa-offline.py's shell_size(); the two parsers should agree.
    body = re.sub(r"//[^\n]*", "", m.group(1))
    # "./index.html" -> "index.html"; drop the bare "./" root entry.
    return {p.lstrip("./") for p in re.findall(r'"([^"]+)"', body) if p.strip("./")}


def main():
    idx = sh("git", "show", f":{SW}")            # staged sw.js
    if idx.returncode != 0:
        return 0                                  # no sw.js staged / not a repo
    src = idx.stdout
    shell = shell_paths(src)
    staged = set(sh("git", "diff", "--cached", "--name-only").stdout.split())
    touched = sorted((staged & shell) - {SW})
    if not touched:
        return 0
    head = sh("git", "show", f"HEAD:{SW}")
    old = ver(head.stdout) if head.returncode == 0 else None
    new = ver(src)
    if old is None or new != old:                 # first commit, or V already bumped — fine
        return 0
    print(f'  {SW}: V is still "{new}" but this commit changes precached shell files:')
    for f in touched:
        print(f"           {f}")
    print(f"  Bump V in {SW} or installed clients keep the cached version.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
