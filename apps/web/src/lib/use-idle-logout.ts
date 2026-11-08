"use client";

import { useEffect, useState } from "react";
import { clearTokens, keepSessionAlive, SIGNOUT_REASON_KEY } from "@/lib/api";
import { getWorkspaceSession } from "@/lib/impersonation";
import { idleStatus, keepAliveEveryMs, secondsLeft } from "@/lib/idle";

const ACTIVITY_KEY = "farm.last_activity";     // shared by every open tab, so activity in one keeps all of them signed in
const KEEPALIVE_KEY = "farm.last_keepalive";
const EVENTS = ["mousedown", "mousemove", "keydown", "touchstart", "scroll", "pointerdown"] as const;

const read = (k: string): number => { try { return Number(localStorage.getItem(k)) || 0; } catch { return 0; } };
const write = (k: string, v: number) => { try { localStorage.setItem(k, String(v)); } catch { /* storage unavailable */ } };

/** Signs the user out after `idleMinutes` without activity on the dashboard (0 / undefined = off).
 * Returns the seconds left once the final-warning window starts, otherwise null.
 * Offline it does nothing (the offline queue must survive); the server enforces the limit when the
 * connection returns. Superadmin workspace sessions are untouched. */
export function useIdleLogout(idleMinutes: number | undefined): number | null {
  const [left, setLeft] = useState<number | null>(null);

  useEffect(() => {
    const minutes = idleMinutes ?? 0;
    if (!minutes || getWorkspaceSession()) { setLeft(null); return; }

    // Opening or reloading the dashboard is itself activity. This also discards a stale time left over from an
    // earlier session; the server still refuses a login that really was idle too long, so nothing is bypassed.
    write(ACTIVITY_KEY, Date.now());
    let lastWrite = 0;
    const touch = () => {
      const now = Date.now();
      if (now - lastWrite < 5000) return;      // throttle: mousemove fires constantly
      lastWrite = now;
      write(ACTIVITY_KEY, now);
    };

    const check = () => {
      const now = Date.now();
      const last = read(ACTIVITY_KEY) || now;
      const state = idleStatus(now, last, minutes);
      if (state === "expired") {
        if (typeof navigator !== "undefined" && navigator.onLine === false) return;
        try { sessionStorage.setItem(SIGNOUT_REASON_KEY, `idle:${minutes}`); } catch { /* ignore */ }
        clearTokens();
        window.location.assign("/login");
        return;
      }
      setLeft(state === "warning" ? secondsLeft(now, last, minutes) : null);
      // Still active: renew the session now and then so the server's own clock keeps sliding.
      if (state === "active" && now - read(KEEPALIVE_KEY) >= keepAliveEveryMs(minutes) && navigator.onLine !== false) {
        write(KEEPALIVE_KEY, now);
        void keepSessionAlive();
      }
    };

    EVENTS.forEach((e) => window.addEventListener(e, touch, { passive: true }));
    document.addEventListener("visibilitychange", check);
    window.addEventListener("online", check);
    const timer = window.setInterval(check, 15_000);
    check();
    return () => {
      EVENTS.forEach((e) => window.removeEventListener(e, touch));
      document.removeEventListener("visibilitychange", check);
      window.removeEventListener("online", check);
      window.clearInterval(timer);
    };
  }, [idleMinutes]);

  return left;
}
