/* TerraMus service worker - lets the admin app OPEN with no signal (e.g. weighing at the crush pen).
 *
 * What it does: remembers the app's own files (/_next/static, immutable) and the admin page shells, and
 * serves them when the network is down.
 * What it never does: touch /api/ or any other origin. Data always comes live from the server, so this
 * can never show stale farm records or interfere with sign-in. Weights entered offline are queued by
 * the page itself (see src/app/admin/feedlot/offline-queue.ts), not by this file.
 *
 * Bump VERSION to drop old caches after a release. */
const VERSION = "v1";
const STATIC_CACHE = `terramus-static-${VERSION}`;
const PAGE_CACHE = `terramus-pages-${VERSION}`;
const FALLBACK_PAGE = "/admin/feedlot";
const OFFLINE_HTML = '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">' +
  '<title>Offline</title><body style="font-family:sans-serif;max-width:32rem;margin:4rem auto;padding:0 1rem">' +
  '<h1>You are offline</h1><p>This page has not been saved on this device yet. Open it once while you have a connection, ' +
  'then it will be available offline.</p>';

self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) {
      if (key.startsWith("terramus-") && key !== STATIC_CACHE && key !== PAGE_CACHE) await caches.delete(key);
    }
    await self.clients.claim();
  })());
});

async function cacheFirst(request) {
  const cache = await caches.open(STATIC_CACHE);
  const hit = await cache.match(request);
  if (hit) return hit;
  const res = await fetch(request);
  if (res.ok) cache.put(request, res.clone());
  return res;
}

async function networkFirstPage(request) {
  const cache = await caches.open(PAGE_CACHE);
  try {
    const res = await fetch(request);
    // only remember a normal page, never a redirect (e.g. to /login) or an error
    if (res.ok && res.type === "basic" && !res.redirected) cache.put(request, res.clone());
    return res;
  } catch (_) {
    const hit = (await cache.match(request, { ignoreSearch: true })) || (await cache.match(FALLBACK_PAGE));
    return hit || new Response(OFFLINE_HTML, { status: 503, headers: { "Content-Type": "text/html; charset=utf-8" } });
  }
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;       // the API and anything third-party: hands off
  if (url.pathname.startsWith("/api/")) return;
  if (url.pathname.startsWith("/_next/static/")) { event.respondWith(cacheFirst(req)); return; }
  if (req.mode === "navigate" && url.pathname.startsWith("/admin")) { event.respondWith(networkFirstPage(req)); return; }
});

// The page tells us which files it just loaded so that the FIRST visit is already usable offline
// (files fetched before this worker took control would otherwise not be saved until the next visit).
self.addEventListener("message", (event) => {
  if (!event.data || event.data.type !== "CACHE_URLS") return;
  event.waitUntil((async () => {
    for (const raw of event.data.urls || []) {
      try {
        const u = new URL(raw, self.location.origin);
        const isStatic = u.pathname.startsWith("/_next/static/");
        if (u.origin !== self.location.origin || !(isStatic || u.pathname.startsWith("/admin"))) continue;
        const cache = await caches.open(isStatic ? STATIC_CACHE : PAGE_CACHE);
        if (await cache.match(u.href)) continue;
        const res = await fetch(u.href, { credentials: "same-origin" });
        if (res.ok && res.type === "basic" && !res.redirected) await cache.put(u.href, res);
      } catch (_) { /* skip this file; offline support is an extra */ }
    }
  })());
});
