"use client";

import { createContext, useCallback, useContext, useLayoutEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import { forgetStoredCycle, readStoredCycle, resolveCycle, setActiveCycle, storeCycle, UNASSIGNED } from "@/lib/cycle-scope";
import type { CyclePreferences, ProductionCycle } from "@/lib/cycle-types";

interface CycleContextValue {
  /** null = all cycles, "unassigned" = records in no cycle, otherwise a cycle id */
  cycleId: string | null;
  setCycleId: (id: string | null) => void;
  cycles: ProductionCycle[];
  /** the selected cycle's record (undefined for "all" / "unassigned" / not loaded) */
  current: ProductionCycle | undefined;
  /** true when the selection comes from the farm's "open on the running cycle" setting, not the person's own choice */
  fromDefault: boolean;
}

const Ctx = createContext<CycleContextValue>({ cycleId: null, setCycleId: () => {}, cycles: [], current: undefined, fromDefault: false });
export const useCycle = () => useContext(Ctx);

// Reference data that does not depend on which cycle is selected, so it is kept across a switch.
const CYCLE_INDEPENDENT = new Set(["me", "catalog", "production-cycles", "farms", "customers", "assets"]);

export function CycleProvider({ children }: { children: React.ReactNode }) {
  const qc = useQueryClient();
  // What this browser remembers (null = never chose). Read synchronously so the first requests already carry it.
  const [stored, setStored] = useState<string | null>(() => {
    const s = readStoredCycle();
    if (s && s !== "all") setActiveCycle(s);
    return s;
  });

  const list = useQuery<ProductionCycle[]>({
    queryKey: ["production-cycles"],
    retry: false,                       // roles without cycles.read just get an empty selector
    staleTime: 60_000,
    queryFn: () => apiFetch<ProductionCycle[]>("/api/v1/production-cycles", { cycleScope: false }),
  });
  // Only people who have never chosen need the farm's default; a failure (no permission, offline) means "all cycles".
  const prefs = useQuery<CyclePreferences>({
    queryKey: ["production-cycles", "preferences"],
    enabled: stored === null,
    retry: false,
    staleTime: 60_000,
    queryFn: () => apiFetch<CyclePreferences>("/api/v1/production-cycles/preferences", { cycleScope: false }),
  });
  const cycles = list.data ?? [];

  // A remembered cycle that no longer exists (deleted, or another organisation) must not silently empty every page.
  const storedGone = !!stored && stored !== "all" && stored !== UNASSIGNED && !!list.data && !list.data.some((c) => c.id === stored);
  const resolved = resolveCycle(storedGone ? null : stored, prefs.data?.default_cycle_id);
  // Wait for the farm default only when it could matter (never chose), so nobody flashes an unfiltered view first.
  const settled = stored !== null || storedGone || !prefs.isPending;

  // Layout effect: runs before any child query starts, so the very first requests carry the right filter.
  useLayoutEffect(() => { setActiveCycle(resolved.cycleId); }, [resolved.cycleId]);
  useLayoutEffect(() => { if (storedGone) { forgetStoredCycle(); setStored(null); } }, [storedGone]);

  const setCycleId = useCallback((id: string | null) => {
    const next = id && id !== "all" ? id : null;
    setActiveCycle(next);               // before invalidating, so the refetches use the new scope
    storeCycle(next);                   // a deliberate choice - including "All cycles" - always beats the farm default
    setStored(next ?? "all");
    qc.resetQueries({ predicate: (q) => !CYCLE_INDEPENDENT.has(String(q.queryKey[0])) });
  }, [qc]);

  const value = useMemo<CycleContextValue>(() => ({
    cycleId: resolved.cycleId, setCycleId, cycles, current: cycles.find((c) => c.id === resolved.cycleId), fromDefault: resolved.fromDefault,
  }), [resolved.cycleId, resolved.fromDefault, setCycleId, cycles]);
  return <Ctx.Provider value={value}>{settled ? children : <p className="p-6 text-sm text-muted">Loading…</p>}</Ctx.Provider>;
}
