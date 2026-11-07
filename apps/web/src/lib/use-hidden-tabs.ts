"use client";

import { useCallback, useEffect, useState } from "react";
import { useMe } from "@/lib/use-auth";

/** Tabs that can never be hidden, so the page always has something to show. */
export const ALWAYS_SHOWN_TABS: readonly string[] = ["Overview"];

const KEY_PREFIX = "terramus.animalTabs.hidden.v1.";   // one entry per signed-in user, on this device

function read(key: string): string[] {
  try {
    const raw = window.localStorage.getItem(key);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((t): t is string => typeof t === "string") : [];
  } catch {
    return [];   // blocked storage or a damaged entry must never break the page: just show every tab
  }
}

/** Which animal-page tabs this person has chosen to hide. A display preference only: nothing is deleted
 * and no permission changes. Remembered per login on this device. */
export function useHiddenTabs() {
  const userId = useMe().data?.user.id;
  const [hidden, setHidden] = useState<string[]>([]);

  useEffect(() => {
    if (!userId) return;
    setHidden(read(KEY_PREFIX + userId).filter((t) => !ALWAYS_SHOWN_TABS.includes(t)));
  }, [userId]);

  const persist = useCallback((next: string[]) => {
    setHidden(next);
    if (!userId) return;
    try { window.localStorage.setItem(KEY_PREFIX + userId, JSON.stringify(next)); } catch { /* storage blocked: lasts until reload */ }
  }, [userId]);

  const toggle = useCallback((tab: string) => {
    if (ALWAYS_SHOWN_TABS.includes(tab)) return;
    persist(hidden.includes(tab) ? hidden.filter((t) => t !== tab) : [...hidden, tab]);
  }, [hidden, persist]);

  const reset = useCallback(() => persist([]), [persist]);

  return { hidden, toggle, reset };
}
