// Service worker: offline shell + cache-busting.  (Pattern from pwa-starter / haydn-info-card.)
//
// THE ONE RULE: bump V whenever you change a precached SHELL file. A new V is what evicts the
// stale cache on activate — forget the bump and your fix ships to the repo but never to anyone's
// installed home-screen copy (iOS caches the SW aggressively). tools/sw_lint.py guards this, and
// app.js surfaces a "tap to update" pill so a stuck phone is fixable in one tap.
//
// Strategy: shell HTML/JS/JSON is network-first (a push is visible on the next reload without
// waiting for a SW swap; falls back to cache offline); images/SVG stay cache-first for speed — a
// V bump refreshes them. Cross-origin (IMSLP, quartetroulette, Wikipedia links) passes through.

const V = "boccherini-v2";   // <-- BUMP ON EVERY SHELL CHANGE
const SHELL = [
  "./", "./index.html",
  "./peters.json", "./parts.json", "./opera.json", "./d3.v7.min.js", "./app.js", "./manifest.json",
  "./assets/icon.svg", "./assets/icon-192.png", "./assets/icon-512.png",
  "./assets/icon-512-maskable.png", "./assets/icon-180.png",
];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(V).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(caches.keys()
    .then(ks => Promise.all(ks.filter(k => k !== V).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
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

  const live = e.request.mode === "navigate" || u.pathname.endsWith("/") || /\.(html|js|json)$/.test(u.pathname);
  if (live) {
    e.respondWith(
      fetch(e.request).then(resp => {
        cachePut(e.request, resp);
        // A 4xx/5xx is a resolved fetch, so .catch() below never sees it — serve
        // the good cached copy instead of handing the app an error page.
        if (!resp.ok) return caches.match(e.request).then(r => r || resp);
        return resp;
      }).catch(() => caches.match(e.request).then(r => r || caches.match("./index.html")))
    );
  } else {
    e.respondWith(
      caches.match(e.request).then(r => r || fetch(e.request).then(resp => {
        cachePut(e.request, resp);
        return resp;
      }))
    );
  }
});
