/**
 * Production-cycle scoping, kept free of React so it can be unit-tested (scripts/cycle-scope.test.ts).
 *
 * The admin header has one "Production cycle" selector. When a cycle is chosen, every LIST / REPORT request the
 * app makes to an endpoint that understands the `production_cycle_id` filter gets it appended automatically, and
 * every CREATE request for a record that can belong to a cycle is stamped with it. That way each existing page
 * becomes cycle-aware without each one re-implementing the plumbing, and "no cycle selected" changes nothing.
 *
 * Values: null = all cycles (nothing added) | "unassigned" = records in no cycle | a cycle id.
 */
export const CYCLE_STORAGE_KEY = "farm.production_cycle";
export const UNASSIGNED = "unassigned";

let active: string | null = null;
export const getActiveCycle = (): string | null => active;
export const setActiveCycle = (id: string | null): void => { active = id && id !== "all" ? id : null; };

const Q = "(\\?.*)?$";
const re = (s: string) => new RegExp(`^${s}${Q}`);

/** GET endpoints whose backend route accepts ?production_cycle_id= */
const FILTERED_GET: RegExp[] = [
  // (costing documents are deliberately NOT filtered: the Costing tab always lists organisation-level and cycle-specific documents together)
  re("/api/v1/feedlot/(intake-batches|sale-batches|weigh-days|performance|profitability|worksheet/export)"),
  re("/api/v1/finance/(transactions|summary|profitability)"),
  re("/api/v1/receivables/(balances|sales-by-salesperson)"),
  re("/api/v1/receivables/customers/[^/?]+/statement"),
  re("/api/v1/fuel(/summary)?"),
  re("/api/v1/groups"),
  re("/api/v1/fodder/(cycles|movements|summary)"),
  re("/api/v1/crops(/stats/summary)?"),
  re("/api/v1/training/(sessions|summary)"),
  re("/api/v1/livestock(/stats/summary)?"),
  re("/api/v1/reports/(dashboard|analytics|profitability(/crops)?|export/livestock\\.(csv|pdf))"),
  re("/api/v1/procurement/purchase-orders"),
  re("/api/v1/inventory/items/[^/?]+/movements"),
];

/** POST endpoints that create a record which can belong to a cycle. Customer payments and write-offs are left
 * out on purpose: they inherit the cycle of the sale they settle. */
const TAGGED_POST: RegExp[] = [
  re("/api/v1/feedlot/(intake-batches|sale-batches)"),
  re("/api/v1/finance/transactions"),
  re("/api/v1/receivables/charges"),
  re("/api/v1/fuel"),
  re("/api/v1/groups"),
  re("/api/v1/fodder/(cycles|movements)"),
  re("/api/v1/crops"),
  re("/api/v1/training/sessions"),
  re("/api/v1/procurement/purchase-orders"),
  re("/api/v1/inventory/items/[^/?]+/movements"),
];

const isGet = (m?: string) => !m || m.toUpperCase() === "GET";

export function scopePath(path: string, method?: string, cycle: string | null = active): string {
  if (!cycle || !isGet(method) || path.includes("production_cycle_id=")) return path;
  if (!FILTERED_GET.some((r) => r.test(path))) return path;
  return `${path}${path.includes("?") ? "&" : "?"}production_cycle_id=${encodeURIComponent(cycle)}`;
}

export function scopeBody(path: string, method: string | undefined, body: BodyInit | null | undefined, cycle: string | null = active): BodyInit | null | undefined {
  if (!cycle || cycle === UNASSIGNED || typeof body !== "string" || (method ?? "GET").toUpperCase() !== "POST") return body;
  if (!TAGGED_POST.some((r) => r.test(path))) return body;
  try {
    const parsed = JSON.parse(body);
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed) || "production_cycle_id" in parsed) return body;
    return JSON.stringify({ ...parsed, production_cycle_id: cycle });
  } catch {
    return body;
  }
}

/** What this browser remembers: null = the person has never chosen, "all" = they chose "All cycles", otherwise an id. */
export function readStoredCycle(): string | null {
  if (typeof window === "undefined") return null;
  try { return localStorage.getItem(CYCLE_STORAGE_KEY); } catch { return null; }
}
/** Remember a deliberate choice. Choosing "All cycles" is stored as "all" so it is not mistaken for "never chose". */
export function storeCycle(id: string | null): void {
  try { localStorage.setItem(CYCLE_STORAGE_KEY, id ?? "all"); } catch { /* storage blocked: the choice just resets on reload */ }
}
export function forgetStoredCycle(): void {
  try { localStorage.removeItem(CYCLE_STORAGE_KEY); } catch { /* ignore */ }
}

/**
 * Which cycle the console is on.
 *  - A deliberate choice always wins ("all" -> no filter, an id -> that cycle).
 *  - If the person has never chosen, the farm's optional "open on the running cycle" setting applies: the server
 *    resolves it to the single running cycle (or null when there are none / several - then we stay on all cycles).
 *  - Otherwise: all cycles, exactly as before cycles existed.
 * `fromDefault` tells the banner the selection was not the person's own.
 */
export function resolveCycle(stored: string | null, defaultCycleId: string | null | undefined): { cycleId: string | null; fromDefault: boolean } {
  if (stored === "all") return { cycleId: null, fromDefault: false };
  if (stored) return { cycleId: stored, fromDefault: false };
  if (defaultCycleId) return { cycleId: defaultCycleId, fromDefault: true };
  return { cycleId: null, fromDefault: false };
}
