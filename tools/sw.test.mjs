#!/usr/bin/env node
// Behavioral tests for sw.js's fetch handler — the offline / "lie-fi" contract (ported from
// pwa-starter, see its scripts/sw.test.mjs). sw.js is dense with invariant-carrying prose; this
// is the executable half. The Playwright harnesses in this directory test the real browser; this
// one tests the handler's decision table deterministically, timeout bounds included.
//
// It loads sw.js UNMODIFIED under mocked Service Worker globals (self, caches, fetch, Response,
// URL) and a FAKE clock, so the network-timeout bounds (NET_TIMEOUT_MS / NET_TIMEOUT_COLD_MS) are
// exercised deterministically and instantly instead of by real waiting. No dependencies.
//
//     node tools/sw.test.mjs
//
// Exits non-zero on any failed assertion, so it drops straight into CI.
import { readFileSync } from "node:fs";

// ---- fake clock ------------------------------------------------------------
// sw.js's withTimeout() is the only timer user; the rest of the code is microtask-driven. A "slow"
// fetch simply never settles, so advancing this clock past a bound is what fires the timeout.
let now = 0;
let nextTimer = 1;
const timers = new Map();
const fakeSetTimeout = (fn, ms) => { const id = nextTimer++; timers.set(id, { at: now + (ms || 0), fn }); return id; };
const fakeClearTimeout = (id) => { timers.delete(id); };
const flush = async (n = 60) => { for (let i = 0; i < n; i++) await Promise.resolve(); };
async function tick(ms) {
  const target = now + ms;
  await flush();
  for (;;) {
    let dueId = null, dueAt = Infinity;
    for (const [id, t] of timers) if (t.at <= target && t.at < dueAt) { dueId = id; dueAt = t.at; }
    if (dueId === null) break;
    const t = timers.get(dueId);
    timers.delete(dueId);
    now = t.at;
    t.fn();
    await flush();
  }
  now = target;
  await flush();
}

// ---- mocked SW environment -------------------------------------------------
const ORIGIN = "https://quartets.boccherini.org";
const BASE = ORIGIN + "/";
const b = (p) => BASE + p;

let fetchMode = "ok";        // "ok" | "slow" | "offline" | "offline-heal" | "redirect"
let fetchStatus = 200;       // status for "ok" mode
let fetchCalls = 0;
let healEntry = null;        // [url, response] inserted by "offline-heal" before it rejects
const CACHE = new Map();     // url -> response

const makeResponse = (body, { status = 200, redirected = false, type = "basic" } = {}) => ({
  _body: body, status, ok: status >= 200 && status < 300, redirected, type,
  clone() { return makeResponse(body, { status, redirected, type }); },
});
const href = (r) => (typeof r === "string" ? new URL(r, self.location).href : r.url);
const req = (url, mode = "no-cors") => ({ url, method: "GET", mode });

const self = {
  location: new URL(BASE + "sw.js"),
  registration: {},
  clients: { claim: async () => {} },
  skipWaiting: async () => {},
  _listeners: {},
  addEventListener(t, fn) { (this._listeners[t] ||= []).push(fn); },
};
const location = self.location;
const ResponseCtor = function (body, init = {}) { return makeResponse(body, { status: init.status || 200 }); };

const cacheApi = {
  async match(r) { return CACHE.get(href(r)); },
  async put(r, resp) { CACHE.set(href(r), resp); },
  async keys() { return [...CACHE.keys()].map((url) => ({ url })); },
};
const caches = {
  async open() { return cacheApi; },
  async match(r) { return CACHE.get(href(r)); },
  async keys() { return ["boccherini-v9"]; },
  async delete() { return true; },
};
const fetchImpl = async (r) => {
  fetchCalls++;
  if (fetchMode === "offline") throw new Error("offline");
  if (fetchMode === "offline-heal") { if (healEntry) CACHE.set(href(healEntry[0]), healEntry[1]); throw new Error("offline"); }
  if (fetchMode === "slow") return new Promise(() => {});   // never settles → only a timeout ends it
  // A navigation's redirect mode is "manual": the browser hands the SW an opaqueredirect
  // (status 0, ok false) that respondWith must pass back for the browser to follow.
  if (fetchMode === "redirect") return makeResponse("", { status: 0, type: "opaqueredirect" });
  return makeResponse("NET:" + href(r), { status: fetchStatus });
};

// ---- load sw.js under those globals ----------------------------------------
const src = readFileSync(new URL("../sw.js", import.meta.url), "utf8");
new Function("self", "location", "caches", "fetch", "Response", "URL", "setTimeout", "clearTimeout", src)(
  self, location, caches, fetchImpl, ResponseCtor, URL, fakeSetTimeout, fakeClearTimeout,
);
const fetchHandler = self._listeners.fetch[0];

// Drive one request through the handler; returns a promise for whatever respondWith() settles to.
function start(request) {
  let settle;
  const done = new Promise((res) => (settle = res));
  fetchHandler({ request, respondWith: (p) => Promise.resolve(p).then(settle), waitUntil() {} });
  return done;
}
// Fire the handler and report whether it claimed the request at all (respondWith called).
async function intercepts(request) {
  let called = false;
  fetchHandler({ request, respondWith: () => { called = true; }, waitUntil() {} });
  await flush();
  return called;
}
const bodyOf = (r) => (r ? (r._body ?? "(generated page)") : "(undefined!)");
const isPending = async (p) => (await Promise.race([p.then(() => false), flush().then(() => true)]));

// ---- assertions ------------------------------------------------------------
// Seed a FAILING exit code up front. The suite runs inside an async IIFE; if the fetch handler
// ever HANGS (e.g. a regression back to unbounded network-first), that IIFE never settles, and with
// only the fake clock there's no real timer keeping the process alive — node would drain the event
// loop and exit 0, staying green on the exact hang this suite exists to catch. The explicit
// process.exit() at the very end is the ONLY sanctioned way to reach a clean exit.
process.exitCode = 1;

let pass = 0, fail = 0;
const ok = (name, cond, detail = "") => { if (cond) { pass++; console.log("  ok   -", name); } else { fail++; console.log("  FAIL -", name, detail); } };
function reset(mode = "ok", status = 200) { CACHE.clear(); fetchMode = mode; fetchStatus = status; fetchCalls = 0; healEntry = null; now = 0; timers.clear(); }
// This app's bootability case: NAV_DEPS is ["./d3.v7.min.js"] — index.html without d3 renders a
// bare <h1> over an empty chart.
const seedBootableShell = () => {
  CACHE.set(BASE, makeResponse("CACHED_ROOT"));
  CACHE.set(b("index.html"), makeResponse("CACHED_INDEX"));
  CACHE.set(b("d3.v7.min.js"), makeResponse("CACHED_D3"));
  CACHE.set(b("app.js"), makeResponse("CACHED_APP"));
};

(async () => {
  // --- cache-first happy path: instant, zero network -----------------------
  reset("slow"); seedBootableShell();
  let r = await start(req(BASE, "navigate"));
  ok("cached+bootable nav → cache, 0 fetches", bodyOf(r) === "CACHED_ROOT" && fetchCalls === 0, `body=${bodyOf(r)} fetches=${fetchCalls}`);

  reset("slow"); seedBootableShell();
  r = await start(req(b("d3.v7.min.js")));
  ok("cached d3 subresource → cache, 0 fetches (no 280 KB re-fetch)", bodyOf(r) === "CACHED_D3" && fetchCalls === 0, `fetches=${fetchCalls}`);

  // --- first run ------------------------------------------------------------
  reset("ok");
  r = await start(req(BASE, "navigate"));
  ok("first-run online nav → network response", bodyOf(r) === "NET:" + BASE && fetchCalls === 1);

  reset("offline");
  r = await start(req(BASE, "navigate"));
  ok("first-run offline nav → real fallback page", r && r.status === 503, `status=${r && r.status}`);

  reset("offline");
  r = await start(req(b("assets/icon-192.png")));
  ok("uncached image offline → real 504", r && r.status === 504, `status=${r && r.status}`);

  reset("offline");
  r = await start(req(b("app.js")));
  ok("uncached script offline → real 504, not HTML", r && r.status === 504, `status=${r && r.status}`);

  // single-page shell fallback: an offline nav to any path serves index.html (bootable required)
  reset("offline");
  CACHE.set(b("index.html"), makeResponse("CACHED_INDEX"));
  CACHE.set(b("d3.v7.min.js"), makeResponse("CACHED_D3"));
  r = await start(req(b("some-shared-link.html"), "navigate"));
  ok("offline nav to other path → index.html shell (single-page)", bodyOf(r) === "CACHED_INDEX", `body=${bodyOf(r)}`);

  // --- the COLD (no-cache) path must be BOUNDED, not infinite ---------------
  reset("slow");   // nothing cached + lie-fi: the previously-unbounded path
  let p = start(req(BASE, "navigate"));
  await tick(3001);
  ok("cold lie-fi nav still pending at 3s (WARM bound must not apply)", await isPending(p));
  await tick(14000);   // now ~17s total, past the 15s COLD bound
  r = await p;
  ok("cold lie-fi nav → bounded, honest fallback", r && r.status === 503, `status=${r && r.status}`);

  // --- WARM bound: cached-but-unbootable + lie-fi resolves at 3s ------------
  reset("slow");
  CACHE.set(BASE, makeResponse("CACHED_ROOT"));   // doc cached, d3 absent → not bootable
  p = start(req(BASE, "navigate"));
  await tick(2999);
  ok("warm lie-fi nav still pending just before 3s", await isPending(p));
  await tick(3);
  r = await p;
  ok("warm lie-fi nav → fallback at ~3s (does NOT wait 15s)", r && r.status === 503, `status=${r && r.status}`);

  // --- a navigation 5xx must NOT serve the unbootable cached doc ------------
  reset("ok", 500);
  CACHE.set(BASE, makeResponse("CACHED_UNBOOTABLE_ROOT"));   // cached but d3 absent
  r = await start(req(BASE, "navigate"));
  ok("nav + server 500 → honest fallback, not bare doc", r && r.status === 503 && bodyOf(r) !== "CACHED_UNBOOTABLE_ROOT", `status=${r && r.status} body=${bodyOf(r)}`);

  reset("ok", 500);
  r = await start(req(b("app.js")));
  ok("subresource + server 500 → returns the response (unchanged)", r && r.status === 500, `status=${r && r.status}`);

  // a PERMANENT 4xx is the server's honest answer, not the offline lie
  reset("ok", 404);
  r = await start(req(b("typo.html"), "navigate"));
  ok("online nav + 404 → server's 404, not the offline lie", r && r.status === 404, `status=${r && r.status}`);

  // an OPAQUEREDIRECT is a healthy answer the browser must get back to follow
  reset("redirect");
  r = await start(req(b("somewhere"), "navigate"));
  ok("online nav + 301 → opaqueredirect passed back, not offline page", r && r.type === "opaqueredirect", `type=${r && r.type} status=${r && r.status}`);

  // --- the catch re-reads the cache, catching a mid-window repair -----------
  reset("offline-heal");
  CACHE.set(b("d3.v7.min.js"), makeResponse("CACHED_D3"));      // so bootable() passes in the catch
  healEntry = [BASE, makeResponse("REPAIRED_ROOT")];   // "ensure-shell" repairs during the fetch
  r = await start(req(BASE, "navigate"));
  ok("catch re-reads cache → serves mid-window repair", bodyOf(r) === "REPAIRED_ROOT", `body=${bodyOf(r)}`);

  // --- app-specific branches ------------------------------------------------
  // Precached JSON (the datasets) is served without revalidation: the refresh would be discarded
  // by cachePut()'s SHELL refusal, so fetching it is pure cellular waste (~65 KB per launch).
  reset("slow");
  CACHE.set(b("opera.json"), makeResponse("CACHED_OPERA"));
  r = await start(req(b("opera.json")));
  ok("precached json → cache, 0 fetches (no discarded revalidate)", bodyOf(r) === "CACHED_OPERA" && fetchCalls === 0, `fetches=${fetchCalls}`);

  // Non-shell JSON is stale-while-revalidate: cached copy now, one background refresh.
  reset("ok");
  CACHE.set(b("extra.json"), makeResponse("CACHED_EXTRA"));
  r = await start(req(b("extra.json")));
  ok("non-shell json → cached copy + background refresh", bodyOf(r) === "CACHED_EXTRA" && fetchCalls === 1, `body=${bodyOf(r)} fetches=${fetchCalls}`);

  // The SW must never intercept its own script (checkVer's ./sw.js?_=<ts> probe) or non-GETs.
  reset("ok");
  ok("sw.js version probe → not intercepted", !(await intercepts(req(b("sw.js?_=123"), "no-cors"))));
  reset("ok");
  ok("POST → not intercepted", !(await intercepts({ url: BASE, method: "POST", mode: "navigate" })));

  console.log(`\n${pass} passed, ${fail} failed`);
  process.exit(fail ? 1 : 0);
})();
