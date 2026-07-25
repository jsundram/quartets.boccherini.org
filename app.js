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
  let installed = "";
  try { installed = (await caches.keys()).find(k => k.startsWith(VER_PREFIX)) || ""; } catch {}
  if (!installed) return;                     // nothing installed yet — first visit

  let latest = "";
  try {   // ?_= + no-store dodges both the SW cache and the HTTP cache → the live sw.js
    const src = await (await fetch("./sw.js?_=" + Date.now(), { cache: "no-store" })).text();
    latest = (src.match(new RegExp(VER_PREFIX + "\\d+")) || [""])[0];
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
  // iOS home-screen apps RESUME rather than reload — re-check on foreground.
  addEventListener("visibilitychange", () => {
    if (!document.hidden) { checkVer(); requestShellTopUp(); }
  });
}
