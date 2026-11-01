"use client";

import Link from "next/link";
import { Layers } from "lucide-react";
import { useCycle } from "@/lib/cycle-context";
import { UNASSIGNED } from "@/lib/cycle-scope";

/** Sidebar control: which production cycle every list, total and report on the page is about. */
export function CycleSelector() {
  const { cycleId, setCycleId, cycles } = useCycle();
  const groups = {
    running: cycles.filter((c) => c.status === "running"),
    planned: cycles.filter((c) => c.status === "planned"),
    closed: cycles.filter((c) => c.status === "closed"),
  };
  const Group = ({ label, items }: { label: string; items: typeof cycles }) =>
    items.length ? (
      <optgroup
        label={label}
        className="font-medium"
        style={{
          color: label === "Running" ? "#f59e0b" : label === "Planned" ? "#60a5fa" : "#a78bfa",
          fontWeight: 600,
        }}
      >
        {items.map((c) => (
          <option key={c.id} value={c.id} style={{ color: "inherit" }}>
            {c.name}
          </option>
        ))}
      </optgroup>
    ) : null;
  return (
    <div className="px-4 py-3">
      <label className="mb-1 flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-paper/60" htmlFor="cycle-select">
        <Layers size={12} /> Production cycle
      </label>
      <select
        id="cycle-select"
        value={cycleId ?? "all"}
        onChange={(e) => setCycleId(e.target.value === "all" ? null : e.target.value)}
        className="w-full rounded-md border border-white/20 bg-white/10 px-2 py-1.5 text-sm text-paper focus:outline-none focus:ring-1 focus:ring-white/40"
      >
        <option value="all" className="text-ink">All cycles</option>
        <Group label="Running" items={groups.running} />
        <Group label="Planned" items={groups.planned} />
        <Group label="Closed" items={groups.closed} />
        <option value={UNASSIGNED} className="text-ink">Not in any cycle</option>
      </select>
      {cycles.length === 0 && (
        <Link href="/admin/cycles" className="mt-1 block text-[11px] text-paper/60 hover:text-paper hover:underline">Create your first cycle →</Link>
      )}
    </div>
  );
}

/** Shown above a page whenever a cycle filter is active, so nobody mistakes a slice for the whole farm. */
export function CycleBanner() {
  const { cycleId, current, setCycleId, fromDefault } = useCycle();
  if (!cycleId) return null;
  const label = cycleId === "unassigned" ? "records that are not in any production cycle" : current ? `${current.name} (${current.status})` : "the selected production cycle";
  return (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-md border border-amber-300 bg-amber-50 px-4 py-2 text-sm text-amber-900" role="status">
      <span>
        Showing only <strong>{label}</strong>{fromDefault && " (opened on the running cycle, your farm’s default)"}. Lists, totals and reports on this page are filtered; per-animal costs are unchanged.
        {current?.status === "closed" && " This cycle is closed: new records cannot be added to it."}
      </span>
      <button type="button" onClick={() => setCycleId(null)} className="rounded border border-amber-400 px-2 py-0.5 text-xs font-medium hover:bg-amber-100">Show all cycles</button>
    </div>
  );
}
