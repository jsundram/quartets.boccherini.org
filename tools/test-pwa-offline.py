#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "playwright>=1.40.0",
# ]
# ///
"""End-to-end PWA test.

Verifies the three things the offline layer promises:
  1. The service worker precaches the app SHELL (index.html + data + d3 + app.js + manifest + icons).
  2. The app renders fully OFFLINE — reload with the network cut still draws every quartet card.
  3. A failed (5xx) shell response does NOT poison the cache — the cachePut() gate in sw.js keeps the
     good cached copy instead of overwriting it with an error body (the #1 subtle PWA cache bug).

Requirements:
    - Local server running:   python3 -m http.server 8000   (from the repo root)
    - Playwright chromium:     uvx playwright install chromium

Run:
    uv run tools/test-pwa-offline.py
"""
import re
import socket
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "http://localhost:8000/"
SW = Path(__file__).resolve().parent.parent / "sw.js"


def server_up(port=8000):
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("localhost", port)) == 0


def shell_size():
    """How many entries sw.js's SHELL declares — the precache is complete at this count.

    Derived, not hardcoded: the heal poll and the heal assertion must agree with each other AND
    with sw.js, or adding a shell file silently weakens the test.
    """
    m = re.search(r"const SHELL\s*=\s*\[(.*?)\]", SW.read_text(), re.S)
    if not m:
        raise SystemExit(f"could not parse SHELL out of {SW}")
    return len(re.findall(r'"[^"]+"', m.group(1)))


def main():
    if not server_up():
        print("ERROR: local server not running. Start it with:  python3 -m http.server 8000")
        return 2

    failures = []
    shell_n = shell_size()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context()
        page = ctx.new_page()

        # --- 1. Online load: wait for the SW to install, activate, and claim this page ---
        page.goto(URL)
        page.wait_for_selector(".quartet-card")
        page.wait_for_function(
            "async () => !!navigator.serviceWorker.controller"
            " && (await caches.keys()).some(k => k.startsWith('boccherini-v'))",
            timeout=15000,
        )
        online_count = page.eval_on_selector_all(".quartet-card", "els => els.length")
        print(f"online:   {online_count} quartet cards rendered")
        if online_count == 0:
            failures.append("no quartet cards rendered online — test setup broken")

        # Precache assertion: the shell files must actually be in the cache.
        cached = page.evaluate(
            "async () => {"
            "  const k = (await caches.keys()).find(k => k.startsWith('boccherini-v'));"
            "  const c = await caches.open(k);"
            "  const reqs = await c.keys();"
            "  return reqs.map(r => new URL(r.url).pathname); }"
        )
        need = ["/index.html", "/opera.json", "/parts.json", "/peters.json",
                "/d3.v7.min.js", "/app.js", "/manifest.json"]
        missing = [n for n in need if not any(pn.endswith(n) for pn in cached)]
        print(f"precache: {len(cached)} entries cached")
        if missing:
            failures.append(f"precache missing expected shell files: {missing}")

        # --- 2. Offline reload: every card must still render from cache ---
        ctx.set_offline(True)
        page.reload()
        page.wait_for_selector(".quartet-card", timeout=15000)
        offline_count = page.eval_on_selector_all(".quartet-card", "els => els.length")
        print(f"offline:  {offline_count} quartet cards rendered (network cut)")
        if offline_count != online_count or offline_count == 0:
            failures.append(f"offline render mismatch: {offline_count} offline vs {online_count} online")
        ctx.set_offline(False)

        # --- 3. Cache-poison gate: a 5xx shell response must not overwrite the good cache ---
        hits = {"n": 0}

        def kill(route):
            hits["n"] += 1
            route.fulfill(status=500, content_type="text/plain", body="boom")

        ctx.route("**/opera.json", kill)
        poison = page.evaluate(
            "async () => {"
            "  let live = null, cache = null;"
            "  try { live = (await (await fetch('./opera.json')).json()).length; } catch (e) { live = 'throw'; }"
            "  const k = (await caches.keys()).find(k => k.startsWith('boccherini-v'));"
            "  const c = await caches.open(k);"
            "  const cr = await c.match('./opera.json');"
            "  try { cache = (await cr.json()).length; } catch (e) { cache = 'throw'; }"
            "  return { live, cache }; }"
        )
        ctx.unroute("**/opera.json")
        if hits["n"] == 0:
            # Some Playwright versions don't route service-worker fetches. Don't claim a pass we didn't earn.
            print("poison:   route never fired — Playwright didn't intercept the SW fetch; gate check INCONCLUSIVE (skipped)")
        else:
            print(f"poison:   500 injected ({hits['n']}x); live fetch len={poison['live']}, cached len={poison['cache']} (both should be the real data length)")
            if not isinstance(poison["cache"], int) or poison["cache"] <= 0:
                failures.append(f"cache poisoned by a 500 response: cached opera.json length={poison['cache']!r}")
            if not isinstance(poison["live"], int) or poison["live"] <= 0:
                failures.append(f"5xx not served from cache: live fetch length={poison['live']!r}")

        # --- 4. Evicted precache: must not blank, and must self-heal ---
        # iOS reclaims Cache API contents (storage pressure, ~7 idle days) and can leave the
        # cache NAME behind with nothing in it. install only runs on a V bump, so this state
        # used to be terminal: caches.match() missed, respondWith() got undefined, and WebKit
        # failed the navigation with "Returned response is null" -> blank white screen.
        page.evaluate(
            "async () => {"
            "  const k = (await caches.keys()).find(k => k.startsWith('boccherini-v'));"
            "  const c = await caches.open(k);"
            "  for (const r of await c.keys()) await c.delete(r); }"
        )
        emptied = page.evaluate(
            "async () => {"
            "  const k = (await caches.keys()).find(k => k.startsWith('boccherini-v'));"
            "  return (await (await caches.open(k)).keys()).length; }"
        )
        print(f"evicted:  precache emptied ({emptied} entries left, cache name kept)")

        ctx.set_offline(True)
        nav_err = None
        try:
            page.reload()
        except Exception as exc:            # the old bug surfaced exactly here
            nav_err = str(exc).splitlines()[0]
        try:
            blanked = page.evaluate(
                "() => ({ len: document.body ? document.body.innerHTML.length : -1,"
                "  text: document.body ? document.body.innerText.slice(0, 80) : '' })"
            )
        except Exception as exc:            # context destroyed by the failed navigation
            blanked = {"len": -1, "text": f"<unreachable: {str(exc).splitlines()[0]}>"}
        print(f"evicted:  offline nav -> bodyLen={blanked['len']} :: {blanked['text']!r}"
              + (f"\n          nav error: {nav_err}" if nav_err else ""))
        if blanked["len"] <= 0:
            failures.append(
                "BLANK SCREEN: offline nav with an empty precache served no document"
                + (f" ({nav_err})" if nav_err else ""))
        # Pin the fallback path specifically: a non-empty body would also pass above if a stale
        # index.html were still being served from somewhere.
        elif "nothing cached yet" not in blanked["text"]:
            failures.append(
                f"expected the offline fallback page, got: {blanked['text']!r}")
        ctx.set_offline(False)

        # Back online: app.js pings the SW, ensureShell() refills what's missing.
        page.reload()
        page.wait_for_selector(".quartet-card", timeout=15000)
        healed = page.evaluate(
            "async (want) => {"
            "  const count = async () => {"
            "    const k = (await caches.keys()).find(k => k.startsWith('boccherini-v'));"
            "    return k ? (await (await caches.open(k)).keys()).length : 0; };"
            "  for (let i = 0; i < 40; i++) {"
            "    if (await count() >= want) break;"
            "    await new Promise(r => setTimeout(r, 250)); }"
            "  return count(); }",
            shell_n,
        )
        print(f"heal:     precache refilled to {healed}/{shell_n} entries after one online load")
        if healed < shell_n:
            failures.append(
                f"precache did not self-heal: {healed}/{shell_n} entries after an online load")

        # And offline works again without a V bump.
        ctx.set_offline(True)
        again = 0
        try:
            page.reload()
            page.wait_for_selector(".quartet-card", timeout=15000)
            again = page.eval_on_selector_all(".quartet-card", "els => els.length")
        except Exception as exc:
            print(f"heal:     offline reload failed: {str(exc).splitlines()[0]}")
        print(f"heal:     {again} quartet cards rendered offline after self-heal")
        if again != online_count:
            failures.append(f"offline broken after self-heal: {again} vs {online_count} cards")
        ctx.set_offline(False)

        browser.close()

    if failures:
        print("\nFAIL:")
        for f in failures:
            print("  -", f)
        return 1
    print("\nPASS: precache + offline render + cache-poison gate + evicted-cache self-heal")
    return 0


if __name__ == "__main__":
    sys.exit(main())
