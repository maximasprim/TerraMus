// Shapes returned by /api/v1/weights/* (apps/api/app/modules/weights) and the words/colours used to show them.

export type Stage = "ready" | "nearly_ready" | "growing" | "stalled" | "needs_weights" | "no_target";
export type Band = "excellent" | "on_target" | "approaching_target" | "below_target";

export interface WeightRow {
  id: string; tag: string; name: string | null; species: string; breed: string | null; sex: string;
  status: string; health_status: string; batch_id: string | null; batch: string | null;
  target_kg: number | null; target_source: "animal" | "batch" | null;
  start_kg: number | null; current_kg: number | null; last_weighed: string | null; days_since_weighed: number | null;
  gain_kg: number | null; overall_adg: number | null; recent_adg: number | null; adg: number | null; adg_band: Band | null;
  remaining_kg: number | null; progress_pct: number | null; est_ready_date: string | null; days_to_ready: number | null;
  stage: Stage; hold_reason: string | null; flags: string[]; weigh_count: number;
}

export interface BatchSummary {
  batch_id: string | null; batch: string; head: number; with_target: number; avg_target_kg: number | null;
  avg_current_kg: number | null; avg_adg: number | null; adg_band: Band | null; avg_progress_pct: number | null;
  ready: number; nearly_ready: number;
}

export interface WeightsOverview {
  as_of: string;
  thresholds: { excellent_above: number; on_target_from: number; approaching_from: number; nearly_ready_days: number; recent_window_days: number };
  summary: { head: number; stages: Partial<Record<Stage, number>>; bands: Partial<Record<Band, number>>; avg_adg: number | null; ready_on_hold: number };
  animals: WeightRow[];
  batches: BatchSummary[];
  batch_options: { id: string; label: string | null; target_weight_kg: number | null }[];
}

export interface DailyRow {
  id: string; tag: string; batch: string | null; weight_kg: number; previous_kg: number | null; previous_date: string | null;
  days_between: number | null; change_kg: number | null; adg: number | null; band: Band | null;
  target_kg: number | null; remaining_kg: number | null; stage: Stage;
}
export interface DailyWeights { days: { date: string; head: number }[]; day: string | null; rows: DailyRow[] }

export interface SeriesPoint { date: string; weight_kg: number; change_kg: number | null; days: number | null; adg: number | null; band: Band | null }
export interface AnimalWeights {
  animal: WeightRow;
  series: SeriesPoint[];
  batch_avg: { date: string; avg_kg: number; n: number }[];
  projection: { date: string; weight_kg: number }[] | null;
  thresholds: WeightsOverview["thresholds"];
}

export const STAGE_LABEL: Record<Stage, string> = {
  ready: "Ready for market", nearly_ready: "Nearly ready", growing: "Growing", stalled: "Not gaining",
  needs_weights: "Needs weights", no_target: "No target set",
};
/** Chip colours: text + background classes (the words carry the meaning; colour only helps scanning). */
export const STAGE_CHIP: Record<Stage, string> = {
  ready: "bg-forest text-paper", nearly_ready: "bg-brass/25 text-ink", growing: "bg-sage/20 text-forest",
  stalled: "bg-clay/15 text-clay", needs_weights: "bg-hairline text-muted", no_target: "bg-hairline text-muted",
};
export const BAND_LABEL: Record<Band, string> = { excellent: "Excellent", on_target: "On target", approaching_target: "Approaching target", below_target: "Below target" };
export const BAND_CHIP: Record<Band, string> = {
  excellent: "bg-forest/15 text-forest", on_target: "bg-sage/20 text-forest", approaching_target: "bg-brass/20 text-brass-dark", below_target: "bg-clay/15 text-clay",
};
export const BAND_COLOR: Record<Band, string> = { excellent: "#2C4F3E", on_target: "#6F9A7B", approaching_target: "#D9A84C", below_target: "#A6432E" };

export const kg = (n: number | null | undefined, digits = 1): string => (n == null ? "-" : `${n.toLocaleString("en-US", { maximumFractionDigits: digits })} kg`);
export const adgText = (n: number | null | undefined): string => (n == null ? "-" : `${n.toFixed(2)} kg/day`);
export const shortDate = (iso: string | null | undefined): string => {
  if (!iso) return "-";
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
};
export const fullDate = (iso: string | null | undefined): string =>
  iso ? new Date(`${iso}T00:00:00`).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) : "-";
