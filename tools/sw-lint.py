#!/usr/bin/env python3
"""Catch a shell change that forgot to bump the service-worker cache version.

sw.js precaches the app SHELL. An edit to any precached file only reaches installed clients when
V changes (a new V evicts the old cache on activate). Forget the bump and the fix ships to the repo
but never to anyone's home-screen copy — the single most common PWA deploy bug.

So: if this commit stages any SHELL file but leaves V identical to HEAD's, warn.

Paths in sw.js's SHELL are repo-root-relative here ("./index.html" -> index.html,
"./assets/icon-192.png" -> assets/icon-192.png), unlike the haydn/pwa-starter layout where they
sit under web/. Adapted from those repos' sw-lint.py.

The pre-commit hook runs it warn-only; run it in CI with a real exit code. By hand:
    uv run tools/sw-lint.py     (or: python3 tools/sw-lint.py)
"""
import re
import subprocess
import sys
from pathlib import Path

SW = "sw.js"
ROOT = Path(__file__).resolve().parent.parent


def sh(*a):
    return subprocess.run(a, capture_output=True, text=True)


def ver(src):
    m = re.search(r'const V\s*=\s*"([^"]*)"', src)
    return m.group(1) if m else None


def shell_paths(src):
    m = re.search(r"const SHELL\s*=\s*\[(.*?)\]", src, re.S)
    if not m:
        return set()
    # Skip line comments, so a commented-out or merely mentioned filename inside the array doesn't
    # register as a shell entry -- but do it with an ALTERNATION, not a strip pass. Deleting
    # r"//[^\n]*" first also eats the "//" inside a URL and every entry after it on that line, and
    # sw.js packs six entries per line: one "https://..." shell entry would silently drop itself
    # plus its line-mates from the set this lint guards, which fails open on the exact deploy bug
    # the lint exists to catch. Scanning left to right, a quoted string is consumed by the string
    # branch before a "//" inside it can open a comment, and a real comment swallows any quoted
    # filename that follows it. Comment matches yield an empty group 1 and drop out.
    # Same guard as tools/test-pwa-offline.py's shell_size(); the two parsers should agree.
    paths = [p for p in re.findall(r'"([^"]*)"|//[^\n]*', m.group(1)) if p]
    # "./index.html" -> "index.html"; drop the bare "./" root entry.
    return {p.lstrip("./") for p in paths if p.strip("./")}


def main():
    idx = sh("git", "show", f":{SW}")            # staged sw.js
    if idx.returncode != 0:
        return 0                                  # no sw.js staged / not a repo
    src = idx.stdout

    # V must end in digits. That numeric tail is load-bearing in three places -- sw.js's collect
    # (which only deletes strictly-older generations) and the bump logic in both test harnesses.
    # It used to order app.js's checkVer() ranking too; that ranking is gone (pwa-starter#17 --
    # checkVer() compares APP_V, the version baked into the running bundle, not a cache key).
    # A non-numeric V doesn't fail anywhere: the collect just stops happening, silently, until two
    # generations have piled up on the device. Upstream's CLAUDE.md invites renaming this prefix,
    # so the contract has to be checked rather than assumed.
    v = ver(src)
    if v is not None and not re.search(r"\d+$", v):
        print(f'  {SW}: V is "{v}", which does not end in digits.')
        print("  The numeric tail orders cache generations — sw.js only collects strictly")
        print("  older ones, so a non-numeric V stops collection silently. Rename to e.g. "
              f'"{v}1" or restore the suffix.')
        return 1

    # app.js's APP_V must EQUAL V. APP_V is the version the running bundle reports about itself,
    # and it is what checkVer() compares against the deployed sw.js -- a cache key describes what
    # is stored, not what the page is executing, so after skipWaiting()/clients.claim() the two
    # diverge permanently and a key-based check goes quiet on exactly the stranded device
    # (pwa-starter#17). Let the pair drift and the comparison reads the wrong number: the pill
    # never appears, silently, on the release it exists to rescue. Nothing else guards this, so
    # without this check the contract is a comment. Read from the INDEX to match the rest of the
    # lint -- it judges what is being committed, not what is on disk.
    app = sh("git", "show", ":app.js")
    if v is not None and app.returncode == 0:
        m = re.search(r'const APP_V\s*=\s*"([^"]*)"', app.stdout)
        if m and m.group(1) != v:
            print(f'  app.js: APP_V is "{m.group(1)}" but {SW}\'s V is "{v}".')
            print("  checkVer() reports APP_V as the version this device is RUNNING, so a drifted")
            print("  pair compares the wrong number and the update pill goes quiet on a stale")
            print("  client. Bump both together.")
            return 1

    shell = shell_paths(src)

    # Every SHELL path must actually exist. A renamed or typo'd entry can never be fetched, and
    # sw.js's collect only runs once the precache is complete -- so on a real device that entry
    # pins BOTH cache generations on disk forever and the stale one keeps answering for anything
    # the new one lacks. sw.js now classifies a 404 as permanent so the collect isn't held hostage,
    # but that is damage control; the deploy is still broken. Catching it here is the actual fix,
    # and it costs one stat() per entry at commit time.
    #
    # ASSUMES A STATIC SITE -- every SHELL entry is a file on disk at a repo-root-relative path.
    # True for this repo and for pwa-starter/haydn-info-card (modulo their web/ prefix), but a
    # SHELL entry served by a route rather than a file would be a false positive here. Anything
    # adopting this check with a server needs an exemption list.
    # Cross-origin entries are their own bug and get their own message: sw.js's fetch handler
    # returns early for any origin but its own, so a precached CDN URL is written but never read.
    foreign = sorted(p for p in shell if "://" in p)
    absent = sorted(p for p in shell if "://" not in p and not (ROOT / p).exists())
    if foreign or absent:
        if absent:
            print(f"  {SW}: SHELL lists files that do not exist:")
            for f in absent:
                print(f"           {f}")
        if foreign:
            print(f"  {SW}: SHELL lists cross-origin URLs:")
            for f in foreign:
                print(f"           {f}")
            print("  sw.js's fetch handler skips other origins, so these cache but never serve.")
        print("  Fix the path or drop the entry — an unfetchable SHELL entry never precaches.")
        return 1

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
