// Pure logic for the weigh-day form's "one row per animal: Tag | Weight" entry.
// No React or browser imports on purpose, so it can be tested on its own (scripts/weigh-rows.test.ts).

export interface WeighRow { id: number; tag: string; weight: string }   // weight stays text while it is being typed
export interface WeighEntry { animal_number: string; weight_kg: number }
export interface RowProblem { tag?: string; weight?: string; warning?: string }

export const MAX_WEIGHT_KG = 2000;   // the API rejects anything above this

let counter = 0;
export const newRow = (tag = "", weight = ""): WeighRow => ({ id: ++counter, tag, weight });
export const blankRows = (count = 6): WeighRow[] => Array.from({ length: count }, () => newRow());
export const isBlankRow = (r: WeighRow): boolean => !r.tag.trim() && !r.weight.trim();

/** Always leave one empty row at the end, so the next animal can be typed straight away. */
export function withTrailingBlank(rows: WeighRow[]): WeighRow[] {
  return rows.length === 0 || !isBlankRow(rows[rows.length - 1]) ? [...rows, newRow()] : rows;
}

/** "349", "331.5", "331,5", "349 kg" -> a number; anything else (letters, "1e3", "3.3.3", empty) -> null. */
export function parseWeight(text: string): number | null {
  const t = text.trim().replace(/\s*kg$/i, "").replace(",", ".");
  if (!/^(\d+(\.\d*)?|\.\d+)$/.test(t)) return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}

export interface RowsAnalysis {
  entries: WeighEntry[];                  // what would be sent: every complete row, in order
  problems: Map<number, RowProblem>;      // by row id
  blocking: number;                       // rows that must be fixed before saving (missing/invalid tag or weight)
  ready: number;                          // distinct animals that are complete and valid
}

export function analyseRows(rows: WeighRow[]): RowsAnalysis {
  const entries: WeighEntry[] = [];
  const problems = new Map<number, RowProblem>();
  const seen = new Set<string>();
  let blocking = 0;
  for (const r of rows) {
    if (isBlankRow(r)) continue;
    const tag = r.tag.trim();
    const weightText = r.weight.trim();
    const p: RowProblem = {};
    if (!tag) p.tag = "Enter the tag";
    if (!weightText) p.weight = "Enter the weight";
    else {
      const w = parseWeight(weightText);
      if (w === null || w <= 0) p.weight = "Weight must be a number above 0";
      else if (w > MAX_WEIGHT_KG) p.weight = `Weight must be ${MAX_WEIGHT_KG} kg or less`;
    }
    if (p.tag || p.weight) {
      blocking += 1;
    } else {
      // The server keeps the first and reports later copies as duplicates, so this is a warning, not a blocker.
      if (seen.has(tag)) p.warning = "Listed twice: only the first one is kept";
      seen.add(tag);
      entries.push({ animal_number: tag, weight_kg: parseWeight(weightText) as number });
    }
    if (p.tag || p.weight || p.warning) problems.set(r.id, p);
  }
  return { entries, problems, blocking, ready: seen.size };
}

/** Pasted text, one animal per line: "A01 349", "A02, 331.5", "A03<TAB>342". The last item on a line is the weight. */
export function parseWeightList(text: string): { rows: WeighRow[]; bad: string[] } {
  const rows: WeighRow[] = [];
  const bad: string[] = [];
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) continue;
    const parts = line.split(/[\s,;\t]+/).filter(Boolean);
    const last = parts[parts.length - 1] ?? "";
    const w = Number(last);
    if (parts.length < 2 || !Number.isFinite(w) || w <= 0) bad.push(line);
    else rows.push(newRow(parts[0], last));
  }
  return { rows, bad };
}
