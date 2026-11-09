// Pure search / filter / sort for the Weights page table (no React or browser imports: scripts/weights-view.test.ts).
import type { Stage, WeightRow } from "./weights-types";

export type WeightSortKey = "tag" | "weight" | "progress" | "adg" | "ready";
export interface WeightFilters { q: string; stage: Stage | ""; batch: string }
export const NO_WEIGHT_FILTERS: WeightFilters = { q: "", stage: "", batch: "" };

export function filterWeightRows(rows: WeightRow[], f: WeightFilters): WeightRow[] {
  const words = f.q.toLowerCase().split(/\s+/).filter(Boolean);
  return rows.filter((r) => {
    if (f.stage && r.stage !== f.stage) return false;
    if (f.batch === "none" ? r.batch_id !== null : f.batch && r.batch_id !== f.batch) return false;
    if (!words.length) return true;
    const hay = [r.tag, r.name, r.breed, r.species, r.batch].filter(Boolean).join(" ").toLowerCase();
    return words.every((w) => hay.includes(w));
  });
}

const naturalTag = (a: string, b: string) => a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" });
const num = (v: number | null, dir: 1 | -1) => (v == null ? (dir === 1 ? Infinity : -Infinity) : v);

/** Missing values always sort last, in either direction. */
export function sortWeightRows(rows: WeightRow[], key: WeightSortKey, dir: "asc" | "desc"): WeightRow[] {
  const m = dir === "asc" ? 1 : -1;
  const pick = (r: WeightRow): number | null =>
    key === "weight" ? r.current_kg : key === "progress" ? r.progress_pct : key === "adg" ? r.adg : key === "ready" ? (r.stage === "ready" ? -1 : r.days_to_ready) : null;
  return [...rows].sort((a, b) => {
    if (key === "tag") return m * naturalTag(a.tag, b.tag);
    const av = pick(a), bv = pick(b);
    if (av == null && bv == null) return naturalTag(a.tag, b.tag);
    if (av == null) return 1;
    if (bv == null) return -1;
    return av === bv ? naturalTag(a.tag, b.tag) : m * (av - bv);
  });
}
