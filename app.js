// App boot: service-worker registration + a one-tap "update available" pill.
// (Pattern from pwa-starter / haydn-info-card, trimmed — this app has no cross-origin
// data to poll and its dark mode is media-query-only, so no theme/data plumbing here.)
//
// Self-contained: it injects its own pill element + styles, so index.html doesn't need
// to know about it. Loaded from a plain <script defer src="app.js"></script>.

const VER_PREFIX = "boccherini-v";   // must match the V prefix in sw.js

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

// Compare the cache version installed on this device against the live sw.js on the
// server. Show the pill only when the server is ahead (so a fix that shipped but got
// stuck behind iOS's aggressive SW cache is fixable in one tap).
async function checkVer() {
  // HIGHEST version, not the first key: two caches can legitimately coexist for a while (sw.js
  // keeps the old one as a net until the new precache is complete), and caches.keys() is in
  // creation order — so find() would report the OLD version as installed and show a permanent
  // "update available" pill on an already-current device.
  //
  // But only among caches that actually HOLD something. sw.js's ensureShellOnce() calls
  // caches.open(V) before it fetches anything, so a bumped version exists as an EMPTY cache the
  // moment an install starts — and per-file precaching means that worker activates even if every
  // shell fetch failed. Ranking on names alone then reads the empty placeholder as "installed",
  // concludes the device is current, and hides the pill on a device that is still serving the
  // PREVIOUS release out of the old cache — killing the one affordance that unsticks it by hand.
  // A partly-filled new cache still reads as installed; that state repairs itself on the next
  // top-up, whereas the empty one can persist.
  let installed = "";
  try {
    const keys = (await caches.keys()).filter(k => k.startsWith(VER_PREFIX));
    const sized = await Promise.all(
      keys.map(async k => [(await (await caches.open(k)).keys()).length, k]));
    installed = sized
      .filter(([n]) => n > 0)
      .map(([, k]) => [parseInt(k.slice(VER_PREFIX.length), 10) || 0, k])
      .sort((a, b) => a[0] - b[0])
      .map(([, k]) => k)
      .pop() || "";
  } catch {}
  if (!installed) return;                     // nothing installed yet — first visit

  let latest = "";
  try {   // ?_= + no-store dodges both the SW cache and the HTTP cache → the live sw.js
    const src = await (await fetch("./sw.js?_=" + Date.now(), { cache: "no-store" })).text();
    // Read the DECLARATION, not the first prefix-shaped string anywhere in the file. An
    // unanchored /VER_PREFIX\d+/ scan matches whatever comes first, and sw.js's comments now
    // cite version names as examples — so a comment moved above `const V`, or one more worked
    // example, would make `latest` a comment and pin a permanent "Update available" pill that
    // does nothing when tapped (forceUpdate() clears caches, reloads, and re-reads the comment).
    // Same expression as tools/sw_lint.py's ver(); keep the two in agreement.
    latest = (src.match(/const V\s*=\s*"([^"]*)"/) || ["", ""])[1];
  } catch {}                                  // offline: leave latest empty → no false "behind"

  const pill = ensurePill();
  const behind = latest && latest !== installed;
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
