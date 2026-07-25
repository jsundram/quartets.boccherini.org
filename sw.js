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
async function ensureShell() {
  const c = await caches.open(V);
  const missing = [];
  for (const url of SHELL) {
    if (!(await c.match(url))) missing.push(url);
  }
  await Promise.all(missing.map(url =>
    fetch(url, { cache: "reload" })
      .then(resp => { if (resp.ok || resp.type === "opaque") return c.put(url, resp); })
      .catch(() => {})            // offline / 404: leave it for the next attempt
  ));
  return missing.length;
}

self.addEventListener("install", e => {
  e.waitUntil(ensureShell().then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(caches.keys()
    .then(ks => Promise.all(ks.filter(k => k !== V).map(k => caches.delete(k))))
    .then(() => self.clients.claim())
    .then(() => ensureShell()));   // repair anything install couldn't get
});

// app.js pings this on every online load, so an evicted precache heals on the next launch
// with a connection instead of waiting for the next V bump.
self.addEventListener("message", e => {
  if (e.data === "ensure-shell") e.waitUntil(ensureShell());
});

// Cache-write gate (from pwa-starter, see its CLAUDE.md §Offline). A fetch() only
// REJECTS on a network failure — a 404 or a mid-deploy 502 arrives as a RESOLVED
// response, so an ungated put() overwrites a good cached copy with an error body
// that then survives as the offline fallback until the next V bump.
// Opaque responses (cross-origin no-cors: webfonts, CDN scripts) always report
// ok:false/status:0 no matter how they went, so they're exempt — gating them would
// silently disable font caching and break offline type.
function cachePut(req, resp) {
  if (!resp.ok && resp.type !== "opaque") return;
  const copy = resp.clone();
  caches.open(V).then(c => c.put(req, copy));
}

self.addEventListener("fetch", e => {
  const u = new URL(e.request.url);
  if (u.origin !== location.origin) return;
  if (u.pathname.endsWith("/sw.js")) return;

  // Same-origin JSON → stale-while-revalidate: serve the cached copy IMMEDIATELY,
  // refresh behind it. JSON here is DATA (peters.json, parts.json, opera.json — all
  // committed, precached datasets), and network-first made every cold start block
  // first paint on three round trips even with perfectly good cached copies. The
  // tradeoff is real but small: a JSON change lands one load later than an HTML/JS
  // change. If some .json becomes genuinely code-like and must be live, move it
  // into the `live` test below.
  if (/\.json$/.test(u.pathname)) {
    e.respondWith(caches.match(e.request).then(cached => {
      const net = fetch(e.request).then(resp => { cachePut(e.request, resp); return resp; });
      e.waitUntil(net.catch(() => {}));   // keep the SW alive for the refresh; offline is fine
      return cached || net;               // no cached copy (first run) → wait for the network
    }));
    return;
  }

  // Same-origin: HTML/JS + navigations → network-first; other assets (images) → cache-first.
  const live = e.request.mode === "navigate" || u.pathname.endsWith("/") || /\.(html|js)$/.test(u.pathname);
  if (live) {
    e.respondWith(
      fetch(e.request).then(resp => {
        cachePut(e.request, resp);
        // A 4xx/5xx is a resolved fetch, so .catch() below never sees it — serve
        // the good cached copy instead of handing the app an error page.
        if (!resp.ok) return caches.match(e.request).then(r => r || resp);
        return resp;
      }).catch(async () => {
        // Offline. Try the exact request, then the shell, then give up VISIBLY.
        // Resolving respondWith() to undefined is what produced the original bug:
        // WebKit fails the navigation with "Returned response is null" and iOS paints
        // a blank white screen — no text, no error, nothing to act on.
        return (await caches.match(e.request))
            || (await caches.match("./index.html"))
            || offlineFallback(e.request);
      })
    );
  } else {
    e.respondWith(
      caches.match(e.request).then(r => r || fetch(e.request).then(resp => {
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
