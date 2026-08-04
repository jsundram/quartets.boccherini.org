// pwa-starter: sw.js @ 3ec3032
// Service worker: offline shell + cache-busting.  (Pattern from pwa-starter / haydn-info-card.)
//
// THE ONE RULE: bump V whenever you change a precached SHELL file. A new V is what evicts the
// stale cache on activate — forget the bump and your fix ships to the repo but never to anyone's
// installed home-screen copy (iOS caches the SW aggressively). tools/sw_lint.py guards this, and
// app.js surfaces a "tap to update" pill so a stuck phone is fixable in one tap.
//
// Strategy, by what the file IS rather than where it lives:
//   HTML/JS + navigations → CACHE-FIRST once installed: paint from the precache with NO network on
//     the critical path, so a load is instant and identical on a fast link, a slow one, or none.
//     Freshness is handled OFF the critical path, because the shell is owned per-generation
//     (cachePut won't overwrite it) and a new deploy MUST bump V anyway (THE ONE RULE): a V bump
//     installs the new shell and lights app.js's update pill. Only an uncached or unbootable
//     request falls through to a bounded network-first fetch, which ALWAYS ends at a real
//     Response. NB this rests on every live url being a SHELL file (it is today — "./",
//     index.html, app.js, d3.v7.min.js): a future NON-shell .html/.js would be served cache-first
//     with no revalidation until a V bump collects the old generation — add such a file to SHELL
//     (and bump V), don't lean on opportunistic caching to refresh it. Bonus: d3.v7.min.js
//     (~280 KB) was fetched network-first on every load only to be DISCARDED by cachePut()'s
//     SHELL refusal; cache-first stops paying that on every launch.
//   JSON → paint from cache now. PRECACHED json (the datasets) is owned by the install, so a V
//     bump is what refreshes it; any other same-origin json is stale-while-revalidate
//   images/SVG and everything else → cache-first for speed; a V bump is what refreshes them
//   cross-origin (IMSLP, quartetroulette, Wikipedia links) → straight through, never cached here

const V = "boccherini-v9";   // <-- BUMP ON EVERY SHELL CHANGE

// "boccherini-v" — the stem shared by every generation. app.js's VER_PREFIX must match.
const V_STEM = V.replace(/\d+$/, "");

// Numeric generation of a cache name, or null if it isn't one of ours. Used to make the collect
// directional: a worker may only delete caches OLDER than its own.
function verNum(name) {
  const tail = name.startsWith(V_STEM) ? name.slice(V_STEM.length) : "";
  return /^\d+$/.test(tail) ? parseInt(tail, 10) : null;
}

const SHELL = [
  "./", "./index.html",
  "./peters.json", "./parts.json", "./opera.json", "./d3.v7.min.js", "./app.js", "./manifest.json",
  "./assets/icon.svg", "./assets/icon-192.png", "./assets/icon-512.png",
  "./assets/icon-512-maskable.png", "./assets/icon-180.png",
];

// Absolute hrefs of the SHELL, resolved once so cachePut()'s check is a Set lookup and not a URL
// parse per request. self.location is the sw.js URL, so "./" resolves to the scope root.
// MUST stay below the SHELL declaration — a const read from its own TDZ throws at script
// evaluation, which kills the whole worker: no install, no precache, blank screen offline.
const SHELL_HREFS = new Set(SHELL.map(u => new URL(u, self.location).href));

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
//
// One parallel batch rather than an await per entry: app.js pings "ensure-shell" on every load,
// every controllerchange, and every foreground, and each ping runs this TWICE (top-up, then the
// re-check below). Serialized, that was ~26 sequential Cache API round trips every time an iOS
// home-screen app came to the foreground with a complete shell and nothing to do.
async function missingFromShell(cache) {
  const c = cache || await caches.open(V);
  const found = await Promise.all(SHELL.map(url => c.match(url)));
  return SHELL.filter((_, i) => !found[i]);
}

// TRANSIENT = a retry could fix it (5xx mid-deploy blip, 408, 429); any other non-ok status is a
// definite server answer. Shared by ensureShellOnce()'s classification and the live branch's
// navigation-error split — one predicate, so the two sites can't drift.
const isTransientStatus = s => s >= 500 || s === 408 || s === 429;

// Returns { transient, permanent }: HOW MANY entries failed in a way a retry could fix, and WHICH
// entries failed in a way no retry ever will. topUpThenCollect() keys the old-cache collect off
// that split, so both have to mean "not cached", not "attempted".
//
// Why the split: the collect waits for a complete precache, so a SHELL entry that can never be
// fetched — a file renamed without updating SHELL, a typo'd path — used to keep it waiting
// FOREVER. Both cache generations then lived on the device permanently, and the old one kept
// answering (via cacheLookup's whole-store fallback) for anything absent from the new one. A 404
// is a bug in the SHELL list that no amount of retrying repairs, so it must not hold the collect
// hostage; everything genuinely retryable still does. tools/sw_lint.py catches the repo-side
// version of this at commit time, before it can ship.
//
// Deliberately CONSERVATIVE about what counts as permanent, because guessing wrong trades a
// working offline copy for an empty one. A REDIRECT is transient — a captive portal redirects
// everything, and that is a mobile-normal state, not a broken shell list. 5xx is transient (a
// mid-deploy blip). 408/429 are transient by definition. Only a definite "this URL is not on the
// server" — 4xx other than those — is permanent.
//
// KNOWN LIMITATION: a put() that fails for QUOTA is counted transient, which keeps the old cache
// and so keeps consuming the quota that just ran out. Harmless at this shell's size (~350 KB) and
// it self-clears once a bump completes, but a larger shell should treat quota failure differently
// — evict the old version to make room rather than holding both.
// NOT MEMOIZED: `missing` is recomputed from the cache every run, so an entry classified permanent
// is re-requested on the next load, controllerchange and foreground — futile by definition, one 404
// each time. Deliberate. A module-scope memo would only hold for a single worker lifetime (iOS kills
// idle workers aggressively), it would have to be invalidated whenever the entry finally appeared,
// and the state costs more than the request it saves. tools/sw_lint.py is the real answer: it stops
// an unfetchable SHELL entry from shipping at all, which makes this path damage control for a case
// that should not reach a device.
async function ensureShellOnce() {
  try {
    const c = await caches.open(V);
    const missing = await missingFromShell(c);
    const outcome = await Promise.all(missing.map(url =>
      fetch(url, { cache: "reload" })
        // A redirected response can't satisfy a navigation (the SW spec rejects it), so caching
        // one would be another route to a blank screen. 206 is here because resp.ok is true for a
        // partial and put() then throws. Skip both rather than poison the entry.
        .then(resp => {
          // 206 is TRANSIENT: a partial means the file IS on the server and something in the
          // path (a proxy, a CDN edge) answered a plain GET with a range. Calling that permanent
          // would let one misbehaving hop exclude the entry, collect the last cache holding a good
          // copy, and — if it were d3.v7.min.js — leave bootable() failing and the offline
          // fallback showing forever with no way back. Only "this URL is not on the server" is
          // permanent, and a 206 says the opposite.
          if (resp.redirected || resp.status === 206) return "transient";
          if (!resp.ok) {
            return isTransientStatus(resp.status) ? "transient" : "permanent";
          }
          return c.put(url, resp).then(() => "ok", () => "transient");
        })
        .catch(() => "transient")   // offline: leave it for the next attempt
    ));
    return {
      transient: outcome.filter(r => r === "transient").length,
      permanent: missing.filter((_, i) => outcome[i] === "permanent"),
    };
  } catch {
    // CacheStorage itself is unavailable — site data blocked, storage corrupt. Transient by
    // definition, and reporting the whole shell as retryable keeps the old cache as the net.
    return { transient: SHELL.length, permanent: [] };
  }
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
// "Complete" here means EVERY FETCHABLE SHELL URL IS PRESENT. It also means they came from the
// SAME deploy, now that cachePut() refuses to write SHELL urls (see the note there): each
// generation's shell is fetched once, by the install that created it, so the net this keeps is
// coherent rather than merely complete by entry count. That was not true before — a redeploy with
// no V bump used to overwrite shell files one at a time inside the current cache.
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
  const { transient, permanent } = await ensureShell();
  if (transient > 0) return transient;              // keep the old cache as a net, try again later

  try {
    // Re-verify rather than trusting that count. ensureShell() dedupes concurrent callers, so a
    // joiner receives a completeness reading taken BEFORE it joined — if eviction landed mid-run,
    // "complete" is already false and we'd collect the net out from under a broken shell. Cheap
    // (cache reads only) and it makes the collect depend on current state, not a stale promise.
    //
    // Entries this run proved PERMANENTLY unfetchable are excluded: they are missing by definition
    // and always will be, so counting them here would re-wedge the collect that the transient/
    // permanent split above exists to unwedge.
    const recheck = (await missingFromShell()).filter(u => !permanent.includes(u)).length;
    if (recheck > 0) return recheck;

    // Don't collect while another version is mid-install. From this worker's perspective the
    // incoming release's cache is merely "not V", so deleting it would throw away a precache that
    // is being built right now — and app.js pings us on load, which is exactly when an update
    // installs. Whichever worker activates next runs this same step and collects then.
    const reg = self.registration;
    if (reg && (reg.installing || reg.waiting)) return 0;

    // ...but that guard alone is not enough, so the collect is also DIRECTIONAL: only strictly
    // OLDER generations, never "everything that isn't me". An incoming worker calls skipWaiting()
    // as soon as its install resolves, at which point it is `active` and both installing and
    // waiting are null — so an outgoing worker still finishing a slow top-up sails past the guard
    // above and deletes the new version's freshly built precache. Observed directly: the update
    // phase of tools/test-sw-update-offline.py left the incoming cache stuck at 7-9 of 13 entries
    // while the old complete one survived, because it was being deleted mid-fill. Comparing
    // generations makes that impossible from either side regardless of who runs when.
    //
    // Caches that aren't ours (verNum → null) are left alone rather than swept: this worker has no
    // claim on them, and "delete everything unfamiliar" is how a SW eats a sibling app's storage.
    // V MUST END IN DIGITS. The numeric tail is load-bearing in four places — this collect,
    // app.js's checkVer() ranking, and both test harnesses' bump logic — and without the guard a
    // rename to a non-numeric V makes verNum(V) null, `n < null` false for every cache, and
    // collection silently stops with no error and no symptom until two generations have piled up.
    // tools/sw_lint.py rejects that shape at commit time; this is the runtime half of the contract.
    const mine = verNum(V);
    if (mine === null) return 0;

    const ks = await caches.keys();
    await Promise.all(ks
      .filter(k => { const n = verNum(k); return n !== null && n < mine; })
      .map(k => caches.delete(k)));
  } catch {
    // Storage went away mid-collect. Keep the old cache and retry on the next ping rather than
    // rejecting: this runs inside install's and the message handler's waitUntil().
    return SHELL.length;
  }
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
  // SHELL entries are owned by ensureShellOnce() and by nothing else. Letting opportunistic
  // request traffic write them too is what produced mixed-generation caches: V is whatever the
  // CURRENT worker declares, so a shell file whose bytes changed on the server got overwritten in
  // the current cache one file at a time while its neighbours kept their older entries. Measured,
  // no V bump needed — after redeploying only index.html, the cache held '/' from the new deploy
  // beside '/index.html' and '/app.js' from the old one, and reported itself complete by entry
  // count. Skipping them here makes "a V bump is what refreshes them" literally true: each
  // generation's shell is fetched once, together, by the install that created it. Harmless in this
  // app (index.html carries the render logic, app.js is only SW plumbing) but a document coupled
  // to its scripts skews into confusing bugs, which is why this is closed by construction.
  if (SHELL_HREFS.has(req.url)) return;
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
//
// NEVER REJECTS. This is called from inside the offline catch handler, which is the last stop
// before offlineFallback() — a throw there escapes as a rejected respondWith(), and WebKit paints
// the same blank white screen this file exists to prevent. The old bare caches.match() couldn't
// throw because it required no cache to exist; caches.open(V) can (site data blocked in Safari,
// corrupt or evicted storage). Resolve undefined instead and let the caller reach the fallback.
async function cacheLookup(req) {
  try {
    const c = await caches.open(V);
    const hit = await c.match(req);
    if (hit) return hit;
  } catch {}
  try {
    return await caches.match(req);
  } catch {
    return undefined;
  }
}

// Subresources a cached document cannot BOOT without. Per-file precaching means the cache can
// legitimately hold index.html while d3.v7.min.js is still missing (a 500 on that one file during
// install), and the shell fallback below is navigation-only by design — so offline, the document
// is served, the script request gets an empty 504, and index.html's inline boot throws "d3 is not
// defined" before its own .catch() can render anything. The user sees a bare <h1> over an empty
// chart: no cards, no error, no hint. Serving the honest fallback instead is strictly better —
// it says what to do, and one online launch repairs the precache.
//
// app.js is deliberately NOT in this list even though it is precached: it only adds the update
// pill and the top-up ping, so the page renders all 91 cards without it. Gating on it would
// replace a working offline page with an error page.
const NAV_DEPS = ["./d3.v7.min.js"];

// Uses cacheLookup(), not a scoped read: a dep that only exists in the previous generation's cache
// will still be SERVED from there, so it counts as present. The gate has to model what the
// subresource request will actually get, or it fires on pages that would have booted fine.
async function bootable() {
  return (await Promise.all(NAV_DEPS.map(u => cacheLookup(u)))).every(Boolean);
}

// The FALLBACK network fetch is BOUNDED by these timers. Cache-first (the live branch) means the
// common, fully-cached load never reaches them; they run only when the cache can't answer — a
// first run, or an evicted/partial shell — where a slow-but-alive link ("lie-fi": a weak cell
// signal, a captive portal that half-answers) would otherwise hang respondWith() on a fetch that
// never settles: the very blank screen this file fights, now with no end. Bounding turns that into
// an eventual real Response.
//
// TWO bounds, because a timeout costs differently in the two states:
//   WARM (a cached copy in hand — even a non-bootable one to fall back to): short. There's a real
//     page one lookup away, so a stale-but-instant paint beats waiting on a dead-slow link.
//   COLD (NOTHING cached — a first run, or a shell iOS evicted under storage pressure / after ~7
//     idle days, the routine case ensureShellOnce() documents): longer, because the only fallback
//     is offlineFallback()'s "try again" page and a working-but-slow link that would have delivered
//     the real app at 8s shouldn't be cut off at 3s. But NOT unbounded: an evicted shell on a weak
//     signal is exactly the reported failure, and an eventual honest page beats a permanent blank.
const NET_TIMEOUT_MS = 3000;
const NET_TIMEOUT_COLD_MS = 15000;

// Reject `promise` if it hasn't settled within `ms`, so a timeout routes into the offline catch
// rather than stranding respondWith() on a fetch that never settles. The underlying fetch is
// untouched — racing a timer against it doesn't abort it — so the caller keeps it alive under
// waitUntil. clearTimeout on settle so a resolved fetch doesn't hold a pending timer (and the SW)
// awake for the remainder of the window.
function withTimeout(promise, ms) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("network timeout")), ms);
    promise.then(
      v => { clearTimeout(timer); resolve(v); },
      err => { clearTimeout(timer); reject(err); }
    );
  });
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

  // Same-origin JSON → serve the cached copy IMMEDIATELY instead of blocking first paint on a
  // round trip. JSON here is DATA (peters.json, parts.json, opera.json — all committed, precached
  // datasets), and network-first made every cold start wait on three round trips even with
  // perfectly good cached copies.
  //
  // PRECACHED json is NOT revalidated. cachePut() refuses to write SHELL urls, so revalidating one
  // would fetch it and discard the response — measured: redeploying opera.json with V unchanged
  // re-fetched it on the next load and left the cached bytes untouched, ~65 KB of cellular spent
  // for nothing on every launch. These files belong to ensureShellOnce(), so a V bump is what
  // refreshes them, which THE ONE RULE already requires. Any OTHER same-origin .json — not in
  // SHELL, so cachePut() will actually store it — still gets true stale-while-revalidate, and for
  // those the tradeoff is the usual one: a change lands one load later.
  //
  // If some .json becomes genuinely code-like and must be live, move it into the `live` test above.
  if (!live && /\.json$/.test(u.pathname)) {
    e.respondWith(cacheLookup(e.request).then(cached => {
      if (cached && SHELL_HREFS.has(e.request.url)) return cached;
      const net = fetch(e.request).then(resp => { cachePut(e.request, resp); return resp; });
      e.waitUntil(net.catch(() => {}));   // keep the SW alive for the refresh; offline is fine
      // No cached copy (first run) → wait for the network, but END AT A RESPONSE. This was the
      // one branch that could still settle respondWith() with a REJECTION: first run offline (or
      // a dataset evicted between the shell nav and the data fetch) gave d3.json() a bare network
      // error, which is exactly the undefined-response failure the rest of this file prevents.
      return cached || net.catch(() => offlineFallback(e.request));
    }));
    return;
  }

  // Same-origin: HTML/JS + navigations → CACHE-FIRST; other assets (images) → cache-first too.
  //
  // The old strategy here was network-first, and it hid a mobile-common failure: fetch() only
  // rejects on a real failure, so a connection that is UP but crawling ("lie-fi" — a weak cell
  // signal, a captive portal that half-answers) makes the fetch hang rather than reject. The
  // offline catch never fired, respondWith() stayed pending, and WebKit painted a blank screen —
  // "internet, but too slow to answer." Cache-first paints straight from the precache; the network
  // is touched only when the cache CAN'T answer, and that fetch is bounded so even it can't hang.
  // Freshness is off this path: a V bump installs the new shell and lights the pill.
  //
  // This also closes the old KNOWN ASYMMETRY (a nav 5xx serving a cached-but-unbootable document
  // while online): a navigation's transient error now throws into the catch, which re-checks
  // bootable() and ends at the honest fallback.
  if (live) {
    e.respondWith((async () => {
      const cached = await cacheLookup(e.request);

      // Serve the cached copy immediately. A navigation must also be BOOTABLE — a cached
      // index.html whose d3.v7.min.js is missing renders a bare <h1> over an empty chart, worse
      // than the honest fallback — so a non-bootable navigation drops through to the network path.
      if (cached && (e.request.mode !== "navigate" || await bootable())) {
        return cached;
      }

      // No usable cached copy: first run, or an evicted/partial shell. Go to the network, bounded
      // EITHER WAY (see the try below): short when a fallback page is in hand, longer
      // (NET_TIMEOUT_COLD_MS) on a true first run where offlineFallback() is the only floor — but
      // never unbounded, so it always ends at a real Response.
      const net = fetch(e.request).then(resp => {
        cachePut(e.request, resp);   // a no-op for SHELL urls; repair is ensureShell()'s job
        // A navigation's fetch runs with redirect mode "manual", so a server 301/302 arrives as
        // an OPAQUEREDIRECT — status 0, ok FALSE, but a healthy answer the browser must be handed
        // back so it can follow it. Treating it as an error would show the offline page while
        // fully online. Subresources never see one (their redirect mode is "follow").
        if (resp.type === "opaqueredirect") return resp;
        if (!resp.ok) {
          // A 4xx/5xx is a RESOLVED fetch, not a rejection. For a subresource, a good cached copy
          // beats handing the app an error body. For a NAVIGATION, split by whether a retry could
          // ever fix it — isTransientStatus(), the same judgment ensureShellOnce() applies:
          //   TRANSIENT (5xx mid-deploy, 408, 429) → throw into the catch. The only cached copy
          //     reachable here already FAILED bootable() (cache-first would have served it
          //     otherwise), so the honest try-again page beats both it and a raw error body.
          //   PERMANENT (other 4xx — a typo'd link, a deleted page) → serve the server's answer.
          //     The offline page would LIE to an online user ("open it once with a connection")
          //     behind a Try Again loop that can never win; the real 404 is actionable.
          if (e.request.mode === "navigate") {
            if (isTransientStatus(resp.status)) throw new Error("http " + resp.status);
            return resp;
          }
          return cacheLookup(e.request).then(r => r || resp);
        }
        return resp;
      });
      try {
        // Bounded either way (see NET_TIMEOUT_*): WARM has a page to fall back to, COLD has only
        // offlineFallback — but NEITHER may hang. A timeout, an offline rejection, or a navigation
        // 5xx (thrown above) all land in the catch.
        return await withTimeout(net, cached ? NET_TIMEOUT_MS : NET_TIMEOUT_COLD_MS);
      } catch {
        // Park the in-flight fetch under waitUntil: a timeout doesn't abort it, so this swallows
        // its eventual rejection instead of leaking an unhandled one (and lets a late success for
        // any non-SHELL live url still land in the cache). Resolving respondWith() to undefined
        // is the original blank-screen bug — WebKit fails the navigation with "Returned response
        // is null" and iOS paints a blank white page — so every branch below ends at a real
        // Response.
        e.waitUntil(net.catch(() => {}));

        // A document we cannot actually boot is worse than an honest fallback. Re-checked LIVE
        // (not from the pre-network snapshot): an "ensure-shell" repair can land inside the
        // timeout window and flip this true.
        if (e.request.mode === "navigate" && !(await bootable())) {
          return offlineFallback(e.request);
        }
        // The shell is a NAVIGATION fallback only: `live` also matches .js, and handing
        // index.html to an uncached app.js / d3.v7.min.js request would make the script
        // fail to parse instead of failing cleanly. (Single-page app, so unlike the skeleton
        // there's no root-only gate — any navigation belongs to index.html.)
        const shell = e.request.mode === "navigate"
          ? await cacheLookup("./index.html") : null;
        // Re-read the cache rather than trusting the pre-network snapshot: an "ensure-shell"
        // repair (app.js pings it on every load) can land during the timeout window, and the
        // fresh copy should win over the snapshot when it does.
        return (await cacheLookup(e.request)) || cached || shell || offlineFallback(e.request);
      }
    })());
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
