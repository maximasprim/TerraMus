import { ApiError } from "@/lib/api";

export interface FarmOption { id: string; name: string }
export interface IntakeBatch {
  id: string; batch_number: number; name: string; delivered_on: string; farm_id: string | null; source: string | null; sex_class: string;
  head_purchased: number; landed_cost: number; landed_cost_per_head: number; head_registered: number; head_active: number;
}
export interface SaleBatch {
  id: string; batch_number: number; sold_on: string; price_per_kg: string | null; buyer_name: string | null;
  head_sold: number; total_weight_kg: number; total_amount: number;
}
export interface ActiveAnimal {
  animal_id: string; tag: string; intake_batch: number | null; latest_weight: number | null; status: string; days_on_farm: number;
}

export const kes = (n: number | null | undefined) => (n == null ? "-" : new Intl.NumberFormat("en-KE", { maximumFractionDigits: 0 }).format(n));
export const errMsg = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback);
export const todayIso = () => new Date().toISOString().slice(0, 10);
export const FIELD = "w-full rounded border border-hairline bg-white px-2 py-1 text-sm focus:border-brass focus:outline-none";

export interface ParsedLine { tag: string; weight: number; price?: number }

/** "A01 349", "A02, 331.5" or "A03<TAB>342 330": a tag, then a weight (kg), then optionally a price per kg. */
export function parseTagLines(text: string, allowPrice = false): { rows: ParsedLine[]; bad: string[] } {
  const rows: ParsedLine[] = [];
  const bad: string[] = [];
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    const parts = line.split(/[\s,;\t]+/).filter(Boolean);
    const nums = parts.slice(1).map(Number);
    const okNums = nums.length >= 1 && nums.length <= (allowPrice ? 2 : 1) && nums.every((n) => Number.isFinite(n) && n > 0);
    if (!okNums) { bad.push(line); continue; }
    rows.push({ tag: parts[0], weight: nums[0], price: allowPrice && nums.length === 2 ? nums[1] : undefined });
  }
  const seen = new Set<string>();
  const dup = rows.filter((r) => (seen.has(r.tag) ? true : (seen.add(r.tag), false))).map((r) => `${r.tag} (listed twice)`);
  return { rows, bad: [...bad, ...dup] };
}
