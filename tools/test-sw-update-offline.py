#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "playwright>=1.40.0",
# ]
# ///
"""Test the SW UPDATE path: a V bump that can't fetch the new shell must not lose the old cache.

This is the failure mode that per-file precaching introduces. `cache.addAll()` was atomic, which
was a liability (one 404 lost the whole precache) but also a guard: a failed install meant the SW
never activated, so the previous complete cache kept serving. Per-file puts remove that guard --
install now always resolves -- so `activate` must repair BEFORE it purges, and must keep the old
cache whenever the new one is still incomplete. Otherwise a V bump on a dead connection trades a
complete offline copy for an empty one.

Three phases, all inside ONE browser session (Cache Storage contents do not survive a WebKit
restart under Playwright's persistent-context, so a quit-and-relaunch harness can only observe
which cache NAMES survived, not whether they still serve):

  1. normal server                -> boccherini-vN installs complete
  2. V bumped, every shell file 500s except /, /index.html, /sw.js, then reload
     -> the new version's install fails; the old cache must survive
  3. server killed outright
     -> the app must still render, from the surviving old cache

Unlike test-pwa-offline.py this spins up its own server (it needs one that can fail selected
paths), so it takes no setup:

    uv run tools/test-sw-update-offline.py
"""
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PORT = 8281
BASE = f"http://127.0.0.1:{PORT}"

# Files the app needs to boot. Copied to a scratch dir so the test can rewrite sw.js's V without
# touching the working tree.
APP_FILES = ["index.html", "app.js", "sw.js", "manifest.json",
             "opera.json", "parts.json", "peters.json", "d3.v7.min.js"]

# A server that can 500 on demand. Everything except the SW script and the shell document fails,
# which is what an install on a dead/flaky connection looks like.
SERVER_SRC = '''
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
BREAK = len(sys.argv) > 2 and sys.argv[2] == "break"
ALLOW = ("/", "/index.html", "/sw.js")
class H(SimpleHTTPRequestHandler):
    def _special(self):
        p = self.path.split("?")[0]
        # A real 206. SimpleHTTPRequestHandler ignores Range, so the cache-write gate can only be
        # tested against a partial the server actually produces.
        if p == "/range-probe":
            body = b"partial-body"
            self.send_response(206)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Range", "bytes 0-%d/%d" % (len(body) - 1, len(body) + 10))
            self.send_header("Content-Length", str(len(body)))
            self.end_headers(); self.wfile.write(body)
            return True
        if p == "/post-probe":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", "2")
            self.end_headers(); self.wfile.write(b"ok")
            return True
        return False
    def do_GET(self):
        if self._special(): return
        if BREAK and self.path.split("?")[0] not in ALLOW:
            self.send_error(500, "broken on purpose"); return
        super().do_GET()
    def do_POST(self):
        self._special()
    def log_message(self, *a): pass
ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
'''

PROBE = """async () => {
  const names = (await caches.keys()).sort();
  const counts = {};
  for (const n of names) counts[n] = (await (await caches.open(n)).keys()).length;
  return { names, counts };
}"""


def serve(root, mode=""):
    (root / "_serve.py").write_text(SERVER_SRC)
    p = subprocess.Popen([sys.executable, str(root / "_serve.py"), str(PORT), mode],
                         cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        time.sleep(0.1)
        with socket.socket() as s:
            s.settimeout(0.3)
            if s.connect_ex(("127.0.0.1", PORT)) == 0:
                return p
    p.kill()
    raise RuntimeError(f"server never came up on {PORT}")


def main():
    root = Path(tempfile.mkdtemp(prefix="sw-update-"))
    for f in APP_FILES:
        shutil.copy(ROOT / f, root / f)
    shutil.copytree(ROOT / "assets", root / "assets")

    failures = []
    srv = serve(root)
    try:
        with sync_playwright() as p:
            browser = p.webkit.launch()          # WebKit: the engine iOS actually uses
            page = browser.new_context().new_page()

            # --- 1. clean install ---
            page.goto(BASE + "/", wait_until="load")
            page.wait_for_selector(".quartet-card", timeout=20000)
            page.wait_for_function(
                "async () => !!navigator.serviceWorker.controller"
                " && (await caches.keys()).some(k => k.startsWith('boccherini-v'))", timeout=20000)
            time.sleep(1.5)
            before = page.evaluate(PROBE)
            cards = page.eval_on_selector_all(".quartet-card", "e => e.length")
            print(f"install:  {before['counts']}  ({cards} cards)")

            # --- cache-write invariants: a non-GET request and a 206 never enter the cache ---
            # SCOPE, stated plainly: sw.js's method !== "GET" guard and its 206 gate exist to keep
            # cache.put() from REJECTING, and that rejection happens in service-worker scope, which
            # a page-scope 'unhandledrejection' listener cannot observe. So this pins the
            # user-visible invariant (request succeeds, nothing lands in the cache) and does NOT
            # discriminate against removing the guards -- confirmed by direct Cache API probe
            # instead: put() throws "Request method is not GET" / "Response is a 206 partial" in
            # both engines, and resp.ok is TRUE for a 206 so the ok-gate alone lets it through.
            guards = page.evaluate(
                "async () => {"
                "  const post = await fetch('./post-probe', {method: 'POST', body: 'x'})"
                "    .then(r => r.status).catch(e => 'threw: ' + e);"
                "  const range = await fetch('./range-probe').then(r => r.status)"
                "    .catch(e => 'threw: ' + e);"
                "  await new Promise(r => setTimeout(r, 600));"   # let any rejection surface
                "  let cachedPost = false, cachedRange = false;"
                "  for (const n of await caches.keys()) {"
                "    const c = await caches.open(n);"
                "    if (await c.match('./post-probe')) cachedPost = true;"
                "    if (await c.match('./range-probe')) cachedRange = true; }"
                "  return { post, range, cachedPost, cachedRange }; }")
            print(f"guards:   POST->{guards['post']} 206->{guards['range']} "
                  f"cached={guards['cachedPost']}/{guards['cachedRange']} (invariant only)")
            if guards["post"] != 200:
                failures.append(f"non-GET request did not succeed: {guards['post']!r}")
            if guards["range"] != 206:
                failures.append(f"206 probe did not return a partial: {guards['range']!r}")
            if guards["cachedPost"]:
                failures.append("a non-GET request was written to the cache")
            if guards["cachedRange"]:
                failures.append("a 206 partial was written to the cache")
            if not before["names"]:
                print("ERROR: nothing precached — test setup broken")
                return 2
            old = before["names"][0]

            # --- 2. V bump that cannot fetch its shell ---
            srv.terminate(); srv.wait()
            sw = root / "sw.js"
            cur = re.search(r'const V = "([^"]+)"', sw.read_text()).group(1)
            # A real numeric bump, not a "-test" suffix: app.js's checkVer() ranks versions by
            # their numeric tail, so a synthetic name would exercise a shape that never ships.
            stem, n = re.match(r"(.*?)(\d+)$", cur).groups()
            new = f"{stem}{int(n) + 1}"
            sw.write_text(sw.read_text().replace(f'const V = "{cur}"', f'const V = "{new}"'))
            srv = serve(root, "break")
            print(f"bump:     {cur} -> {new}, every shell file 500s except /, /index.html, /sw.js")
            # Force the update check explicitly instead of relying on a navigation to trigger one.
            # Waiting on a plain reload is flaky here — WebKit doesn't reliably re-fetch sw.js on
            # every navigation in this harness, and a fixed sleep plus "the old cache survived"
            # passes trivially when the bump never happened at all. registration.update() is the
            # deterministic path, and the assertion below proves the scenario actually ran.
            page.reload(wait_until="load")
            page.evaluate(
                "async () => { const r = await navigator.serviceWorker.getRegistration();"
                "  if (r) { try { await r.update(); } catch {} } }")
            try:
                page.wait_for_function(
                    "async (n) => (await caches.keys()).includes(n)", arg=new, timeout=25000)
            except Exception:
                pass
            after = page.evaluate(PROBE)
            print(f"bumped:   {after['counts']}")
            if new not in after["names"]:
                failures.append(f"new version {new} never installed — the bump scenario never ran")
            if old not in after["names"]:
                failures.append(
                    f"collected the complete old cache {old} while the new one was incomplete")
            elif after["counts"].get(old, 0) < before["counts"].get(old, 0):
                failures.append(f"old cache {old} lost entries: "
                                f"{before['counts'].get(old)} -> {after['counts'].get(old)}")

            # --- 3. network gone: the survivor must still serve ---
            srv.terminate(); srv.wait(); srv = None
            time.sleep(0.6)
            try:
                page.reload(wait_until="load", timeout=25000)
            except Exception as exc:
                print(f"          offline reload error: {str(exc).splitlines()[0]}")
            try:
                page.wait_for_selector(".quartet-card", timeout=10000)
            except Exception:
                pass
            got = page.eval_on_selector_all(".quartet-card", "e => e.length")
            print(f"offline:  {got} quartet cards rendered with the server down")
            if got != cards:
                failures.append(f"offline render lost after a bad bump: {got} vs {cards} cards")

            # --- 4. network recovers: the top-up completes AND the stale cache is collected ---
            # Keeping the old cache is not free. CacheStorage.match() iterates in CREATION order,
            # so a lingering old version answers first and shadows the current shell -- the device
            # would serve the previous release offline, and checkVer() would read the old version
            # and show a permanent "update available" pill. activate() fires once per SW version,
            # so the collect has to be retried post-activation (sw.js does it from the message
            # handler, which app.js pings on load and on foreground).
            srv = serve(root)
            print(">>> network restored")
            page.reload(wait_until="load")
            page.wait_for_selector(".quartet-card", timeout=20000)
            try:
                page.wait_for_function(
                    "async (n) => { const ks = await caches.keys();"
                    "  return ks.length === 1 && ks[0] === n; }", arg=new, timeout=25000)
            except Exception:
                pass
            healed = page.evaluate(PROBE)
            print(f"healed:   {healed['counts']}")
            if healed["counts"].get(new, 0) < before["counts"].get(old, 0):
                failures.append(f"new precache never completed: {healed['counts']}")
            elif old in healed["names"]:
                failures.append(
                    f"stale cache {old} never collected though {new} is complete — it shadows the "
                    f"current shell (creation-order match) and skews checkVer()")

            # Exactly one versioned cache must remain. That's the root invariant: while two
            # coexist, the older one shadows reads AND app.js's checkVer() can report the wrong
            # installed version. Asserting the cache set rather than re-deriving checkVer()'s
            # answer here keeps this from testing a copy of the fixed logic instead of the code.
            versioned = [n for n in healed["names"] if n.startswith("boccherini-v")]
            print(f"caches:   {versioned} remaining")
            if len(versioned) != 1:
                failures.append(f"expected exactly one versioned cache after healing, got {versioned}")

            # --- 5. version-scoped reads: an older cache must not outrank the current one ---
            # CacheStorage.match() scans in CREATION order, so an old cache created FIRST answers
            # first. cacheLookup() reads V before falling back to the whole store, which is what
            # makes a lingering old generation harmless. Staged by rebuilding the store in that
            # order: sentinel cache first, real one second -- so a bare caches.match() would serve
            # the sentinel and the app would not render.
            current = versioned[0] if versioned else new
            staged = page.evaluate(
                "async (cur) => {"
                "  const c = await caches.open(cur);"
                "  const saved = [];"
                "  for (const r of await c.keys()) saved.push([r.url, await (await c.match(r)).text()]);"
                "  for (const n of await caches.keys()) await caches.delete(n);"
                # created FIRST -> wins a bare CacheStorage.match()
                "  const stale = await caches.open('boccherini-v1');"
                "  const body = '<!doctype html><title>x</title><body>SENTINEL-STALE-SHELL';"
                "  for (const [url] of saved) {"
                "    if (new URL(url).pathname === '/' || new URL(url).pathname === '/index.html')"
                "      await stale.put(url, new Response(body, "
                "        {headers: {'Content-Type': 'text/html; charset=utf-8'}})); }"
                # created SECOND -> loses a bare match, must win a scoped read
                "  const fresh = await caches.open(cur);"
                "  for (const [url, text] of saved) {"
                "    const ct = url.endsWith('.json') ? 'application/json'"
                "      : url.endsWith('.js') ? 'text/javascript'"
                "      : (new URL(url).pathname === '/' || url.endsWith('.html')) ? 'text/html; charset=utf-8'"
                "      : 'application/octet-stream';"
                "    await fresh.put(url, new Response(text, {headers: {'Content-Type': ct}})); }"
                "  const bare = await (await caches.match('/')).text();"
                "  return { order: await caches.keys(),"
                "           bareServes: bare.includes('SENTINEL') ? 'SENTINEL' : 'real' }; }",
                current)
            print(f"scoped:   caches {staged['order']}, bare caches.match('/') -> "
                  f"{staged['bareServes']}")
            if staged["bareServes"] != "SENTINEL":
                print("scoped:   could not stage a shadowing cache; scoped-read check INCONCLUSIVE")
            else:
                srv.terminate(); srv.wait(); srv = None
                time.sleep(0.5)
                try:
                    page.reload(wait_until="load", timeout=25000)
                    page.wait_for_selector(".quartet-card", timeout=10000)
                except Exception:
                    pass
                res = page.evaluate(
                    "() => ({ cards: document.querySelectorAll('.quartet-card').length,"
                    "  sentinel: document.body ? document.body.innerText.includes('SENTINEL') : false })")
                print(f"scoped:   offline nav -> {res['cards']} cards, "
                      f"sentinel_served={res['sentinel']}")
                if res["sentinel"] or res["cards"] != cards:
                    failures.append(
                        "a shadowing older cache outranked the current version: offline nav served "
                        f"{'the sentinel' if res['sentinel'] else str(res['cards']) + ' cards'} "
                        "— cacheLookup() is not reading V first")
            browser.close()
    finally:
        if srv and srv.poll() is None:
            srv.kill()
        shutil.rmtree(root, ignore_errors=True)

    if failures:
        print("\nFAIL:")
        for f in failures:
            print("  -", f)
        return 1
    print("\nPASS: a failed V bump keeps the old cache and the app still works offline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
