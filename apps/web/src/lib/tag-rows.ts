// Pure logic for the "one row per animal: Tag | Weight (| Price per kg)" entry used by Feedlot Sales and by
// "Add animals" on an intake batch. Same idea as lib/weigh-rows.ts (the weigh-day form), with an optional price
// column and stricter duplicate handling: selling or registering a tag twice is a mistake, so it blocks saving.
// No React or browser imports on purpose, so it can be tested on its own (scripts/tag-rows.test.ts).

import { MAX_WEIGHT_KG, parseWeight } from "./weigh-rows";

export interface TagRow { id: number; tag: string; weight: string; price: string }   // numbers stay text while typed
export interface TagEntry { tag: string; weight: number; price?: number }
export interface TagRowProblem { tag?: string; weight?: string; price?: string }

let counter = 0;
export const newTagRow = (tag = "", weight = "", price = ""): TagRow => ({ id: ++counter, tag, weight, price });
export const blankTagRows = (count = 6): TagRow[] => Array.from({ length: count }, () => newTagRow());
export const isBlankTagRow = (r: TagRow): boolean => !r.tag.trim() && !r.weight.trim() && !r.price.trim();

/** Always leave one empty row at the end, so the next animal can be typed straight away. */
export function withTrailingBlankTag(rows: TagRow[]): TagRow[] {
  return rows.length === 0 || !isBlankTagRow(rows[rows.length - 1]) ? [...rows, newTagRow()] : rows;
}

export interface TagRowsAnalysis {
  entries: TagEntry[];                    // every complete, valid row, in order
  problems: Map<number, TagRowProblem>;   // by row id
  blocking: number;                       // rows that must be fixed or cleared before saving
}

export function analyseTagRows(rows: TagRow[], opts: { allowPrice?: boolean } = {}): TagRowsAnalysis {
  const entries: TagEntry[] = [];
  const problems = new Map<number, TagRowProblem>();
  const seen = new Set<string>();
  let blocking = 0;
  for (const r of rows) {
    if (isBlankTagRow(r)) continue;
    const tag = r.tag.trim();
    const weightText = r.weight.trim();
    const priceText = r.price.trim();
    const p: TagRowProblem = {};
    if (!tag) p.tag = "Enter the tag";
    else if (seen.has(tag)) p.tag = "Tag listed twice";
    if (!weightText) p.weight = "Enter the weight";
    else {
      const w = parseWeight(weightText);
      if (w === null || w <= 0) p.weight = "Weight must be a number above 0";
      else if (w > MAX_WEIGHT_KG) p.weight = `Weight must be ${MAX_WEIGHT_KG} kg or less`;
    }
    let price: number | undefined;
    if (opts.allowPrice && priceText) {
      const v = parseWeight(priceText.replace(/\s*(kes|\/kg)$/i, ""));
      if (v === null || v <= 0) p.price = "Price must be a number above 0";
      else price = v;
    } else if (!opts.allowPrice && priceText) {
      p.price = "No price needed here";
    }
    if (tag) seen.add(tag);
    if (p.tag || p.weight || p.price) {
      blocking += 1;
      problems.set(r.id, p);
    } else {
      entries.push({ tag, weight: parseWeight(weightText) as number, price });
    }
  }
  return { entries, problems, blocking };
}

/** Pasted text, one animal per line: "A01 349", "A02, 331.5", "A03<TAB>342 330" (the 3rd item is the price, when
 * a price column is in use). Lines that cannot be understood are returned so nothing is silently dropped. */
export function parseTagList(text: string, allowPrice = false): { rows: TagRow[]; bad: string[] } {
  const rows: TagRow[] = [];
  const bad: string[] = [];
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) continue;
    const parts = line.split(/[\s,;\t]+/).filter(Boolean);
    const nums = parts.slice(1);
    const fits = nums.length >= 1 && nums.length <= (allowPrice ? 2 : 1);
    const good = fits && nums.every((n) => { const v = Number(n); return Number.isFinite(v) && v > 0; });
    if (!good) bad.push(line);
    else rows.push(newTagRow(parts[0], nums[0], allowPrice && nums.length === 2 ? nums[1] : ""));
  }
  return { rows, bad };
}
