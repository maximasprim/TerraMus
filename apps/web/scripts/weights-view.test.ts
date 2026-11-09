// Run: npx tsx scripts/weights-view.test.ts   (pure logic test for the Weights page filters and sorting)
import { filterWeightRows, NO_WEIGHT_FILTERS, sortWeightRows } from "../src/lib/weights-view";
import { scopePath } from "../src/lib/cycle-scope";
import type { WeightRow } from "../src/lib/weights-types";
let pass = 0, fail = 0;
const ok = (c: boolean, m: string) => { c ? pass++ : (fail++, console.log("FAIL:", m)); };

const mk = (tag: string, o: Partial<WeightRow> = {}): WeightRow => ({
  id: tag, tag, name: null, species: "cattle", breed: null, sex: "male", status: "active", health_status: "healthy",
  batch_id: null, batch: null, target_kg: 450, target_source: "batch", start_kg: 300, current_kg: 400, last_weighed: "2026-11-01",
  days_since_weighed: 7, gain_kg: 100, overall_adg: 1, recent_adg: 1, adg: 1, adg_band: "on_target", remaining_kg: 50,
  progress_pct: 66, est_ready_date: null, days_to_ready: 50, stage: "growing", hold_reason: null, flags: [], weigh_count: 3, ...o });
const rows = [
  mk("B10", { batch_id: "b1", batch: "Batch 1 · BATCH 1", stage: "ready", current_kg: 455, adg: 1.5, days_to_ready: 0, progress_pct: 100 }),
  mk("B2", { batch_id: "b1", batch: "Batch 1 · BATCH 1", stage: "nearly_ready", current_kg: 440, adg: 0.9, days_to_ready: 11, progress_pct: 93 }),
  mk("A1", { stage: "no_target", target_kg: null, adg: null, days_to_ready: null, progress_pct: null, current_kg: 210, breed: "Boran" }),
  mk("C5", { batch_id: "b2", batch: "Batch 2 · BATCH 2", stage: "stalled", adg: -0.2, days_to_ready: null, current_kg: 380 }),
];
const tags = (l: WeightRow[]) => l.map((r) => r.tag).join(",");

ok(tags(filterWeightRows(rows, { ...NO_WEIGHT_FILTERS, stage: "ready" })) === "B10", "stage filter");
ok(tags(filterWeightRows(rows, { ...NO_WEIGHT_FILTERS, batch: "b1" })) === "B10,B2", "batch filter");
ok(tags(filterWeightRows(rows, { ...NO_WEIGHT_FILTERS, batch: "none" })) === "A1", "'no batch' filter");
ok(tags(filterWeightRows(rows, { ...NO_WEIGHT_FILTERS, q: "boran" })) === "A1", "search by breed");
ok(tags(filterWeightRows(rows, { ...NO_WEIGHT_FILTERS, q: "batch 2" })) === "B2,C5", "search by batch, every word (B2 matches on its tag)");
ok(filterWeightRows(rows, NO_WEIGHT_FILTERS).length === 4, "no filters shows all");

ok(tags(sortWeightRows(rows, "tag", "asc")) === "A1,B2,B10,C5", "natural tag order (B2 before B10)");
ok(tags(sortWeightRows(rows, "weight", "desc")) === "B10,B2,C5,A1", "weight descending");
ok(tags(sortWeightRows(rows, "adg", "desc")) === "B10,B2,C5,A1" && tags(sortWeightRows(rows, "adg", "asc")).endsWith("A1"), "missing values always last");
ok(tags(sortWeightRows([{ ...rows[0], days_to_ready: null }, rows[1], rows[2], rows[3]], "ready", "asc")).startsWith("B10,B2"), "ready animals (no days figure) come first");
ok(tags(sortWeightRows(rows, "ready", "asc")) === "B10,B2,A1,C5", "soonest ready first, unknown last (ties by tag)");
ok(scopePath("/api/v1/weights/overview", "GET", "c2").endsWith("?production_cycle_id=c2"), "weights overview follows the selected production cycle");
ok(scopePath("/api/v1/weights/daily?day=2026-07-28", "GET", "c2").endsWith("&production_cycle_id=c2"), "weights daily follows the selected production cycle");
ok(scopePath("/api/v1/weights/overview", "GET", null) === "/api/v1/weights/overview", "no cycle selected: unchanged");
console.log(`weights-view: ${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
