// Run: node scripts/sw.test.mjs
// Loads public/sw.js into a simulated service-worker scope and checks the rules that matter.
import fs from "node:fs";
import vm from "node:vm";

const ORIGIN = "https://farm.example";
const code = fs.readFileSync(new URL("../public/sw.js", import.meta.url), "utf8");
let pass = 0, fail = 0;
const ok = (c, m) => { c ? pass++ : (fail++, console.log("FAIL:", m)); };

// Browsers give same-origin fetches type "basic"; Node's `new Response()` is "default". Make fakes realistic.
const mk = (body, init = {}, props = {}) => {
  const r = new Response(body, init);
  for (const [k, v] of Object.entries({ type: "basic", redirected: false, ...props })) Object.defineProperty(r, k, { value: v, configurable: true });
  return r;
};

function makeWorld() {
  const store = new Map();                       // cacheName -> Map(url -> Response)
  const handlers = {};
  const net = { online: true, calls: [], routes: new Map() };
  const keyOf = (r, ignoreSearch) => { const u = new URL(typeof r === "string" ? r : r.url, ORIGIN); if (ignoreSearch) u.search = ""; return u.href.split("#")[0]; };
  const caches = {
    async open(name) {
      if (!store.has(name)) store.set(name, new Map());
      const m = store.get(name);
      return { async match(r, o) { const k = keyOf(r, o?.ignoreSearch); for (const [u, v] of m) if (keyOf(u, o?.ignoreSearch) === k) return v.clone(); },
               async put(r, res) { m.set(keyOf(r), res); } };
    },
    async keys() { return [...store.keys()]; },
    async delete(n) { return store.delete(n); },
  };
  const self = { location: new URL(ORIGIN), addEventListener: (t, h) => { handlers[t] = h; }, skipWaiting() {}, clients: { claim: async () => {} } };
  const fetchFn = async (r) => {
    const url = typeof r === "string" ? r : r.url; net.calls.push(url);
    if (!net.online) throw new TypeError("Failed to fetch");
    const route = net.routes.get(new URL(url, ORIGIN).pathname);
    return route ? route() : mk("ok", { status: 200 });
  };
  const ctx = vm.createContext({ self, caches, fetch: fetchFn, Response, Request, URL, console });
  vm.runInContext(code, ctx);
  const fire = (request) => { let p = null; handlers.fetch({ request, respondWith: (x) => { p = x; } }); return p; };
  const req = (path, mode = "cors", method = "GET", origin = ORIGIN) => { const r = new Request(origin + path, { method }); Object.defineProperty(r, "mode", { value: mode }); return r; };
  return { handlers, store, net, fire, req, caches, self };
}

(async () => {
  let w = makeWorld();
  // 1. never touches the API, other origins, or non-GET
  ok(w.fire(w.req("/api/backend/livestock")) === null, "API calls are NOT intercepted");
  ok(w.fire(w.req("/api/v1/auth/me")) === null, "/api/v1 is NOT intercepted");
  ok(w.fire(w.req("/x.js", "cors", "GET", "https://cdn.other.com")) === null, "cross-origin NOT intercepted");
  ok(w.fire(w.req("/admin/feedlot", "navigate", "POST")) === null, "POST NOT intercepted");
  ok(w.fire(w.req("/shop/some-farm", "navigate")) === null, "public shop pages are NOT intercepted (only /admin)");

  // 2. static assets: cache-first (second request never hits the network)
  const a = w.req("/_next/static/chunks/app-1.js");
  await (await w.fire(a)); const n1 = w.net.calls.length;
  await (await w.fire(w.req("/_next/static/chunks/app-1.js")));
  ok(w.net.calls.length === n1, "static asset served from cache the second time");
  w.net.online = false;
  ok((await (await w.fire(w.req("/_next/static/chunks/app-1.js"))).text()) === "ok", "static asset available offline");

  // 3. pages: network-first, saved, then served offline
  w = makeWorld();
  w.net.routes.set("/admin/feedlot", () => mk("<html>FEEDLOT</html>", { status: 200 }));
  ok((await (await w.fire(w.req("/admin/feedlot", "navigate"))).text()).includes("FEEDLOT"), "online navigation passes through");
  w.net.online = false;
  ok((await (await w.fire(w.req("/admin/feedlot", "navigate"))).text()).includes("FEEDLOT"), "offline: the saved page is served");
  const other = await (await w.fire(w.req("/admin/livestock", "navigate"))).text();
  ok(other.includes("FEEDLOT"), "offline + unsaved admin page -> falls back to the offline-capable feedlot page");

  // 4. nothing saved yet -> a clear offline message, not a browser error
  w = makeWorld(); w.net.online = false;
  const empty = await w.fire(w.req("/admin/feedlot", "navigate"));
  ok(empty.status === 503 && (await empty.text()).includes("You are offline"), "no saved page -> friendly 503 page");

  // 5. never remembers redirects (e.g. to /login) or errors
  w = makeWorld();
  w.net.routes.set("/admin/feedlot", () => mk("login", { status: 200 }, { redirected: true }));
  await w.fire(w.req("/admin/feedlot", "navigate")); w.net.online = false;
  ok((await (await w.fire(w.req("/admin/feedlot", "navigate"))).status) === 503, "a redirected response is not cached");
  w = makeWorld(); w.net.routes.set("/admin/feedlot", () => mk("boom", { status: 500 }));
  await w.fire(w.req("/admin/feedlot", "navigate")); w.net.online = false;
  ok((await (await w.fire(w.req("/admin/feedlot", "navigate"))).status) === 503, "an error response is not cached");

  w = makeWorld(); w.net.routes.set("/admin/feedlot", () => mk("opaque", { status: 200 }, { type: "opaque" }));
  await w.fire(w.req("/admin/feedlot", "navigate")); w.net.online = false;
  ok((await (await w.fire(w.req("/admin/feedlot", "navigate"))).status) === 503, "a non-basic (opaque/cors) response is not cached");

  // 6. warm-up message: only same-origin static + /admin files are fetched; junk ignored
  w = makeWorld(); let waited = null;
  w.handlers.message({ data: { type: "CACHE_URLS", urls: [`${ORIGIN}/_next/static/a.js`, `${ORIGIN}/admin/feedlot`, "https://evil.com/_next/static/x.js", `${ORIGIN}/api/v1/secret`, `${ORIGIN}/shop/x`, "not a url ::"] }, waitUntil: (p) => { waited = p; } });
  await waited;
  ok(w.net.calls.length === 2 && w.net.calls.every((u) => u.startsWith(ORIGIN) && !u.includes("/api/") && !u.includes("/shop/")), "warm-up fetches only allowed same-origin files");
  const before = w.net.calls.length;
  w.handlers.message({ data: { type: "CACHE_URLS", urls: [`${ORIGIN}/_next/static/a.js`] }, waitUntil: (p) => { waited = p; } }); await waited;
  ok(w.net.calls.length === before, "already-saved files are not fetched again");
  w.handlers.message({ data: { type: "SOMETHING_ELSE" }, waitUntil: () => { throw new Error("should not be called"); } });
  ok(true, "unknown messages ignored");

  // 7. activate removes only OLD terramus caches
  w = makeWorld(); await w.caches.open("terramus-static-v0"); await w.caches.open("other-app-cache"); await w.caches.open("terramus-static-v1");
  let act = null; w.handlers.activate({ waitUntil: (p) => { act = p; } }); await act;
  const keys = await w.caches.keys();
  ok(!keys.includes("terramus-static-v0") && keys.includes("other-app-cache") && keys.includes("terramus-static-v1"), "activate prunes only old terramus caches");

  console.log(`service worker tests: ${pass} passed, ${fail} failed`); process.exit(fail ? 1 : 0);
})();
