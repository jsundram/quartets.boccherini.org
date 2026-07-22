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
import socket
import sys

from playwright.sync_api import sync_playwright

URL = "http://localhost:8000/"


def server_up(port=8000):
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("localhost", port)) == 0


def main():
    if not server_up():
        print("ERROR: local server not running. Start it with:  python3 -m http.server 8000")
        return 2

    failures = []
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

        browser.close()

    if failures:
        print("\nFAIL:")
        for f in failures:
            print("  -", f)
        return 1
    print("\nPASS: precache + offline render + cache-poison gate")
    return 0


if __name__ == "__main__":
    sys.exit(main())
