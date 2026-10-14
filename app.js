// App boot: service-worker registration + a one-tap "update available" pill.
// (Pattern from pwa-starter / haydn-info-card, trimmed — this app has no cross-origin
// data to poll and its dark mode is media-query-only, so no theme/data plumbing here.)
//
// Self-contained: it injects its own pill element + styles, so index.html doesn't need
// to know about it. Loaded from a plain <script defer src="app.js"></script>.

const VER_PREFIX = "boccherini-v";   // must match the V prefix in sw.js
// THIS bundle's version — the code the page is actually EXECUTING, baked in at parse time and so
// the only honest answer to "what is this device running?". Must be kept equal to sw.js's V:
// app.js is a precached shell file, so the two always ship together on a bump.
const APP_V = "boccherini-v14";

// Build the little pill, hidden until we know the server is ahead of this device.
function ensurePill() {
  let pill = document.getElementById("sw-update");
  if (pill) return pill;
  pill = document.createElement("button");
  pill.id = "sw-update";
  pill.hidden = true;
  pill.textContent = "Update available — tap to refresh";
  Object.assign(pill.style, {
    position: "fixed", left: "12px", bottom: "12px", zIndex: "9999",
    font: "13px/1 'Helvetica Neue', Arial, sans-serif", padding: "9px 13px",
    border: "0", borderRadius: "999px", cursor: "pointer",
    background: "#E91E63", color: "#fff", boxShadow: "0 2px 8px rgba(0,0,0,.25)",
  });
  document.body.appendChild(pill);
  return pill;
}

// Compare the version of the bundle this page is RUNNING against the live sw.js on the
// server. Show the pill only when the server is ahead (so a fix that shipped but got
// stuck behind iOS's aggressive SW cache is fixable in one tap).
async function checkVer() {
  // Is a worker installed AT ALL? That is the only question a cache key can answer honestly, and
  // it is asked for one narrow reason: to keep the pill out of a plain browser tab that has never
  // registered anything. What this device is RUNNING is APP_V — see the comparison below.
  //
  // This used to RANK the keys — highest numeric tail, and only among caches that held something
  // — and treat the winner as "the installed version". A key cannot report that. It describes
  // what is STORED, not what is executing, and after an activation the two differ permanently:
  // sw.js calls skipWaiting() + clients.claim() and topUpThenCollect() drops older generations,
  // so the key set flips to the new version the moment a worker activates while this page keeps
  // running the bundle it parsed at launch — clients.claim() reloads nothing. The comparison then
  // read installed === latest on precisely the device that was a release behind, hid the pill,
  // and removed the one affordance that unsticks it by hand. A home-screen copy that is never
  // force-quit holds that state indefinitely.
  //
  // The non-empty filter went with the ranking, deliberately. Both existed to stop the KEY from
  // lying about currency, which APP_V now settles at the source — and keeping the filter would
  // now do active harm: it hides the pill on a device whose new cache is still the empty
  // placeholder ensureShellOnce() opens before it fetches anything, which is exactly the stranded
  // device the filter was written to protect.
  let installed = false;
  try { installed = (await caches.keys()).some(k => k.startsWith(VER_PREFIX)); } catch {}
  if (!installed) return;                     // nothing installed yet — first visit

  let latest = "";
  try {   // ?_= + no-store dodges both the SW cache and the HTTP cache → the live sw.js
    const src = await (await fetch("./sw.js?_=" + Date.now(), { cache: "no-store" })).text();
    // Read the DECLARATION, not the first prefix-shaped string anywhere in the file. An
    // unanchored /VER_PREFIX\d+/ scan matches whatever comes first, and sw.js's comments now
    // cite version names as examples — so a comment moved above `const V`, or one more worked
    // example, would make `latest` a comment and pin a permanent "Update available" pill that
    // does nothing when tapped (forceUpdate() clears caches, reloads, and re-reads the comment).
    // Same expression as tools/sw-lint.py's ver(); keep the two in agreement.
    latest = (src.match(/const V\s*=\s*"([^"]*)"/) || ["", ""])[1];
  } catch {}                                  // offline: leave latest empty → no false "behind"

  // Compare what is RUNNING against the server. APP_V is baked into this bundle, so a page still
  // executing an old app.js reports the old version no matter how current the cache has become.
  const pill = ensurePill();
  const behind = latest && latest !== APP_V;
  pill.hidden = !behind;
  if (behind) pill.onclick = forceUpdate;
}

async function forceUpdate() {   // drop every cache, reload → SW reinstalls the latest shell
  try { await Promise.all((await caches.keys()).map(k => caches.delete(k))); } catch {}
  location.reload();
}

// Ask the active SW to top up any missing precache entries. iOS can reclaim Cache API
// contents (storage pressure, ~7 idle days) while leaving the registration in place, and
// sw.js only precaches on install — i.e. on a V bump. Without this nudge a device whose
// cache got evicted stays broken offline indefinitely; with it, one online launch repairs it.
function requestShellTopUp() {
  if (!navigator.onLine) return;
  // getRegistration() resolves undefined when there's nothing registered; .ready would just
  // never settle, leaving a pending promise behind on every foreground.
  navigator.serviceWorker.getRegistration()
    .then(reg => { if (reg && reg.active) reg.active.postMessage("ensure-shell"); })
    .catch(() => {});
}

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("./sw.js").catch(() => {});
  checkVer();
  requestShellTopUp();
  // A registration can exist with no ACTIVE worker for a moment — first install, or the swap
  // during an update — and the ping above is fire-and-forget, so it would simply be dropped and
  // nothing would retry until the next launch. That undercuts the whole "open it once with a
  // connection and it repairs itself" promise, so retry when a worker actually takes control.
  navigator.serviceWorker.addEventListener("controllerchange", requestShellTopUp);
  // iOS home-screen apps RESUME rather than reload — re-check on foreground.
  addEventListener("visibilitychange", () => {
    if (!document.hidden) { checkVer(); requestShellTopUp(); }
  });
}
