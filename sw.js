// pwa-starter: sw.js @ 8d54c48
// Service worker: offline shell + cache-busting.  (Pattern from pwa-starter / haydn-info-card.)
//
// THE ONE RULE: bump V whenever you change a precached SHELL file. A new V is what evicts the
// stale cache on activate — forget the bump and your fix ships to the repo but never to anyone's
// installed home-screen copy (iOS caches the SW aggressively). tools/sw_lint.py guards this, and
// app.js surfaces a "tap to update" pill so a stuck phone is fixable in one tap.
//
// Strategy, by what the file IS rather than where it lives:
//   HTML/JS + navigations → network-first (a push is visible on the next reload without waiting
//     for a SW swap; falls back to cache offline)
//   JSON → stale-while-revalidate (it's data: paint from cache now, refresh behind it)
//   images/SVG and everything else → cache-first for speed; a V bump is what refreshes them
//   cross-origin (IMSLP, quartetroulette, Wikipedia links) → straight through, never cached here

const V = "boccherini-v8";   // <-- BUMP ON EVERY SHELL CHANGE
const SHELL = [
  "./", "./index.html",
  "./peters.json", "./parts.json", "./opera.json", "./d3.v7.min.js", "./app.js", "./manifest.json",
  "./assets/icon.svg", "./assets/icon-192.png", "./assets/icon-512.png",
  "./assets/icon-512-maskable.png", "./assets/icon-180.png",
];

// Precache top-up. Deliberately NOT cache.addAll(): addAll is atomic, so a single 404
// (a shell file renamed and the list not updated, or a mid-deploy blip) rejects the whole
// install and the device ends up with NO cache at all — offline then shows a blank screen.
// Per-file puts degrade instead: whatever fetched is cached, the rest retries next boot.
//
// It also only fetches what's MISSING, which makes it safe to call repeatedly — that's how
// an evicted cache repairs itself. iOS reclaims script-writable storage (Cache API included)
// under pressure and after ~7 idle days, and it can leave the cache NAME behind while
// dropping the contents. install only runs on a V bump, so without this top-up a
// once-evicted cache stays empty forever and the app is permanently blank offline.

// Which SHELL entries this version's cache is missing. No network — pure cache reads.
async function missingFromShell(cache) {
  const c = cache || await caches.open(V);
  const missing = [];
  for (const url of SHELL) {
    if (!(await c.match(url))) missing.push(url);
  }
  return missing;
}

// Returns the number of SHELL entries STILL missing when it's done — 0 means the precache is
// complete. topUpThenCollect() keys the old-cache collect off that, so the count has to mean
// "not cached", not "attempted".
//
// KNOWN LIMITATION: a put() that fails for QUOTA is counted the same as a 404, which keeps the
// old cache and so keeps consuming the quota that just ran out. Harmless at this shell's size
// (~350 KB) and it self-clears once a bump completes, but a larger shell should treat quota
// failure differently — evict the old version to make room rather than holding both.
async function ensureShellOnce() {
  const c = await caches.open(V);
  const missing = await missingFromShell(c);
  const failed = await Promise.all(missing.map(url =>
    fetch(url, { cache: "reload" })
      // A redirected response can't satisfy a navigation (the SW spec rejects it), so caching one
      // would be another route to a blank screen. 206 is here because resp.ok is true for a
      // partial and put() then throws. Skip both rather than poison the entry.
      .then(resp => {
        if (!resp.ok || resp.redirected || resp.status === 206) return 1;
        return c.put(url, resp).then(() => 0, () => 1);
      })
      .catch(() => 1)             // offline / 404: leave it for the next attempt
  ));
  return failed.reduce((a, b) => a + b, 0);
}

// install, activate, and the "ensure-shell" message can all fire close together; without this a
// V bump would fetch the whole shell 2-3x on a cellular connection. Callers that arrive mid-run
// join it instead of starting their own.
let shellRun = null;
function ensureShell() {
  return shellRun ??= ensureShellOnce().finally(() => { shellRun = null; });
}

self.addEventListener("install", e => {
  e.waitUntil(ensureShell().then(() => self.skipWaiting()));
});

// REPAIR BEFORE COLLECT, and only collect once THIS version's cache is complete.
//
// addAll's atomicity was a liability (one 404 lost the whole precache) but it was also a guard:
// a failed install meant this SW never activated, so the previous cache kept serving. Per-file
// puts removed that guard — install now always resolves — so collecting first would let a V bump
// on a dead connection trade a working stale offline copy for an empty new one.
//
// "Complete" here means ALL 13 SHELL URLS ARE PRESENT — it does NOT mean they came from the same
// deploy. cachePut() writes network responses into caches.open(V), and V is whatever the current
// worker declares, so a shell file whose bytes change on the server gets overwritten in the
// CURRENT cache one file at a time while the rest keep their older entries. Measured, no V bump
// needed: after redeploying only index.html, boccherini-v8 held '/' from the new deploy alongside
// '/index.html' and '/app.js' from the old one. So the net this keeps is complete by entry count
// and may span generations. Harmless in this app — index.html carries the render logic and app.js
// is only SW plumbing, so skew can't break the page — but see PROPAGATE notes before porting: a
// document coupled to its scripts skews into confusing bugs. The upstream fix is for cachePut()
// to skip SHELL urls entirely, leaving each generation's shell to ensureShellOnce(), which is
// what "a V bump is what refreshes them" already implies.
//
// Keeping the old cache is NOT free, which is why this has to be re-runnable rather than a
// one-shot in activate: CacheStorage.match() iterates caches in CREATION order, so while an old
// version lingers it ANSWERS FIRST and shadows the current shell. Verified in both engines —
// caches ['boccherini-v8','boccherini-v9'] both holding a URL resolve to the v8 copy. So a
// lingering old cache means the device serves the previous release offline, and app.js's
// checkVer() reads the wrong installed version. Both persist until something collects, and
// activate fires once per SW version — hence the retry from the message handler below, which is
// the only hook that runs after activation.
async function topUpThenCollect() {
  const stillMissing = await ensureShell();
  if (stillMissing > 0) return stillMissing;        // keep the old cache as a net, try again later

  // Re-verify rather than trusting that count. ensureShell() dedupes concurrent callers, so a
  // joiner receives a completeness reading taken BEFORE it joined — if eviction landed mid-run,
  // "complete" is already false and we'd collect the net out from under a broken shell. Cheap
  // (cache reads only) and it makes the collect depend on current state, not a stale promise.
  const recheck = (await missingFromShell()).length;
  if (recheck > 0) return recheck;

  // Don't collect while another version is mid-install. From this worker's perspective the
  // incoming release's cache is merely "not V", so deleting it would throw away a precache that
  // is being built right now — and app.js pings us on load, which is exactly when an update
  // installs. Whichever worker activates next runs this same step and collects then.
  const reg = self.registration;
  if (reg && (reg.installing || reg.waiting)) return 0;

  const ks = await caches.keys();
  await Promise.all(ks.filter(k => k !== V).map(k => caches.delete(k)));
  return 0;
}

self.addEventListener("activate", e => {
  e.waitUntil(topUpThenCollect().then(() => self.clients.claim()));
});

// app.js pings this on every online load, so an evicted precache heals on the next launch with a
// connection instead of waiting for the next V bump — and a collect deferred at activate time
// (incomplete shell, or an install in flight) gets retried here.
//
// NB: the collect deliberately lives here and not inside ensureShellOnce(), which also runs during
// install — deleting the old cache then would strand pages still controlled by the previous worker.
self.addEventListener("message", e => {
  if (e.data === "ensure-shell") e.waitUntil(topUpThenCollect());
});

// Cache-write gate (from pwa-starter, see its CLAUDE.md §Offline). A fetch() only
// REJECTS on a network failure — a 404 or a mid-deploy 502 arrives as a RESOLVED
// response, so an ungated put() overwrites a good cached copy with an error body
// that then survives as the offline fallback until the next V bump.
// Opaque responses (cross-origin no-cors: webfonts, CDN scripts) always report
// ok:false/status:0 no matter how they went, so they're exempt — gating them would
// silently disable font caching and break offline type.
// A redirected response can't be used to satisfy a navigation, so caching one is another way to
// end up with a blank screen. Cheap insurance: if "./" ever grows a redirect, don't store it.
//
// 206 needs its own clause because resp.ok is TRUE for a partial (verified in both engines), so
// the gate above lets it through and cache.put() then throws "Partial response is unsupported".
// Irrelevant to this app's JSON and icons; immediately relevant to any sibling caching audio or
// video, where range requests are normal.
function cachePut(req, resp) {
  if (resp.redirected || resp.status === 206) return;
  if (!resp.ok && resp.type !== "opaque") return;
  const copy = resp.clone();
  // The one unguarded promise in the file until now. Non-GET requests, 206s, and quota
  // exhaustion all surface here, and an uncaught rejection in a SW is just noise in a log
  // nobody reads — the caller's response has already been returned either way.
  caches.open(V).then(c => c.put(req, copy)).catch(() => {});
}

// Read the CURRENT version first, then fall back to the whole store.
//
// CacheStorage.match() scans caches in CREATION order, so a lingering old version outranks the
// current one — that's the shadowing bug from the previous round, and collecting promptly only
// closes it by timing. Scoping the first lookup to V closes it by construction: the old cache can
// still fill a gap (it's the net that makes a failed V bump survivable) but it can no longer
// outrank a complete current shell. Verified in both engines:
//   bare caches.match -> STALE-v8 | scoped-first -> FRESH-v9 | old-only entry -> still reachable
async function cacheLookup(req) {
  const c = await caches.open(V);
  return (await c.match(req)) || (await caches.match(req));
}

self.addEventListener("fetch", e => {
  const u = new URL(e.request.url);
  // cache.put() rejects for anything but GET ("Request method is not GET"), and a form POST is
  // mode === "navigate" — so without this it would walk straight into the live branch and
  // cachePut(). This app has no POSTs; a template inevitably meets one.
  if (e.request.method !== "GET") return;
  if (u.origin !== location.origin) return;
  if (u.pathname.endsWith("/sw.js")) return;

  // Navigations are decided FIRST, ahead of the .json test below. A document request must always
  // end at a real page — including a direct navigation to a .json URL, which the SWR branch would
  // otherwise answer with a rejected respondWith (a bare network error) instead of the fallback.
  const live = e.request.mode === "navigate" || u.pathname.endsWith("/") || /\.(html|js)$/.test(u.pathname);

  // Same-origin JSON → stale-while-revalidate: serve the cached copy IMMEDIATELY,
  // refresh behind it. JSON here is DATA (peters.json, parts.json, opera.json — all
  // committed, precached datasets), and network-first made every cold start block
  // first paint on three round trips even with perfectly good cached copies. The
  // tradeoff is real but small: a JSON change lands one load later than an HTML/JS
  // change. If some .json becomes genuinely code-like and must be live, move it
  // into the `live` test above.
  if (!live && /\.json$/.test(u.pathname)) {
    e.respondWith(cacheLookup(e.request).then(cached => {
      const net = fetch(e.request).then(resp => { cachePut(e.request, resp); return resp; });
      e.waitUntil(net.catch(() => {}));   // keep the SW alive for the refresh; offline is fine
      return cached || net;               // no cached copy (first run) → wait for the network
    }));
    return;
  }

  // Same-origin: HTML/JS + navigations → network-first; other assets (images) → cache-first.
  if (live) {
    e.respondWith(
      fetch(e.request).then(resp => {
        cachePut(e.request, resp);
        // A 4xx/5xx is a resolved fetch, so .catch() below never sees it — serve
        // the good cached copy instead of handing the app an error page.
        if (!resp.ok) return cacheLookup(e.request).then(r => r || resp);
        return resp;
      }).catch(async () => {
        // Offline. Try the exact request, then the shell, then give up VISIBLY.
        // Resolving respondWith() to undefined is what produced the original bug:
        // WebKit fails the navigation with "Returned response is null" and iOS paints
        // a blank white screen — no text, no error, nothing to act on.
        //
        // The shell is a NAVIGATION fallback only: `live` also matches .js, and handing
        // index.html to an uncached app.js / d3.v7.min.js request would make the script
        // fail to parse instead of failing cleanly.
        const shell = e.request.mode === "navigate"
          ? await cacheLookup("./index.html") : null;
        return (await cacheLookup(e.request)) || shell || offlineFallback(e.request);
      })
    );
  } else {
    e.respondWith(
      cacheLookup(e.request).then(r => r || fetch(e.request).then(resp => {
        cachePut(e.request, resp);
        return resp;
      }).catch(() => offlineFallback(e.request)))
    );
  }
});

// Terminal fallback: always a real Response, never undefined. Navigations get a readable
// page (the precache is empty — the one thing that fixes it is one online launch, which
// ensureShell() then uses to repair itself); subresources get a plain 504.
function offlineFallback(req) {
  if (req.mode !== "navigate") {
    return new Response("", { status: 504, statusText: "Offline" });
  }
  return new Response(
    `<!doctype html><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Offline — Boccherini Quartets</title>
<style>
  body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
       background:#f5f5f5;color:#222;font:16px/1.5 'Helvetica Neue',Arial,sans-serif}
  main{max-width:22em;padding:2em;text-align:center}
  h1{font-size:1.15em;margin:0 0 .6em}
  p{margin:.6em 0;color:#555}
  button{margin-top:1.2em;border:0;border-radius:999px;padding:.7em 1.3em;
         background:#E91E63;color:#fff;font-size:1em;cursor:pointer}
  @media (prefers-color-scheme:dark){
    body{background:#1a1a1a;color:#eee} p{color:#aaa}
  }
</style>
<main>
  <h1>Offline, and nothing cached yet</h1>
  <p>The offline copy of this app hasn't been stored on this device — or the system
     reclaimed it to free up space.</p>
  <p>Open it once with a connection and it will rebuild itself for offline use.</p>
  <button onclick="location.reload()">Try again</button>
</main>`,
    { status: 503, headers: { "Content-Type": "text/html; charset=utf-8" } }
  );
}
