"use client";

import { useEffect } from "react";

/** Registers the offline service worker (production only) and hands it the files this page just loaded,
 * so that opening the app once online is enough for it to open offline afterwards. */
export function SwRegister() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production" || !("serviceWorker" in navigator)) return;
    let cancelled = false;
    const run = async () => {
      try {
        await navigator.serviceWorker.register("/sw.js", { scope: "/" });
        const ready = await navigator.serviceWorker.ready;
        if (cancelled) return;
        const urls = performance.getEntriesByType("resource").map((e) => e.name).filter((n) => n.includes("/_next/static/"));
        if (location.pathname.startsWith("/admin")) urls.push(location.href);
        ready.active?.postMessage({ type: "CACHE_URLS", urls });
      } catch {
        /* offline support is an extra, never a requirement */
      }
    };
    if (document.readyState === "complete") void run();
    else window.addEventListener("load", () => void run(), { once: true });
    return () => { cancelled = true; };
  }, []);
  return null;
}
