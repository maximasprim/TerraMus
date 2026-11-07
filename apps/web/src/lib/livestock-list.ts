// Pure search / filter / sort logic for the Livestock list page. No React or browser imports on purpose, so it can
// be tested on its own (scripts/livestock-list.test.ts). The page already loads every animal, so all of this runs
// in the browser: no API change.

export interface ListAnimal {
  animal_number: string; ear_tag: string | null; rfid: string | null; name: string | null;
  species: string; breed: string | null; category: string | null; sex: string;
  current_weight: string | null; status: string; health_status: string;
}

export type SortKey = "id" | "species" | "sex" | "weight" | "status" | "health";
export type SortDir = "asc" | "desc";
export interface SortState { key: SortKey; dir: SortDir }
export interface Filters { q: string; species: string; status: string }

export const NO_FILTERS: Filters = { q: "", species: "", status: "" };

/** Everything a person might type to find an animal, lower-cased in one string. */
function haystack(a: ListAnimal): string {
  return [a.animal_number, a.ear_tag, a.rfid, a.name, a.breed, a.species, a.category, a.sex]
    .filter(Boolean).join(" ").toLowerCase();
}

/** Every word typed must appear somewhere ("bull boran" finds a Boran bull). Filters combine with the search. */
export function filterAnimals<T extends ListAnimal>(animals: T[], f: Filters): T[] {
  const terms = f.q.toLowerCase().split(/\s+/).filter(Boolean);
  return animals.filter((a) => {
    if (f.species && a.species !== f.species) return false;
    if (f.status && a.status !== f.status) return false;
    if (terms.length === 0) return true;
    const h = haystack(a);
    return terms.every((t) => h.includes(t));
  });
}

/** Tags sort the way people read them: A2 before A10, B0129 before B0130. */
const collator = new Intl.Collator("en", { numeric: true, sensitivity: "base" });

function textOf(a: ListAnimal, key: SortKey): string {
  switch (key) {
    case "id": return a.animal_number ?? "";
    case "species": return `${a.species ?? ""} ${a.breed ?? ""}`.trim();
    case "sex": return a.sex ?? "";
    case "status": return a.status ?? "";
    case "health": return a.health_status ?? "";
    default: return "";
  }
}

const weightOf = (a: ListAnimal): number | null => {
  if (a.current_weight == null || a.current_weight === "") return null;
  const n = Number(a.current_weight);
  return Number.isFinite(n) ? n : null;
};

/** Returns a new array. `null` sort = leave the order as loaded (newest first). Animals with no weight always
 * go last, whichever direction is chosen. Ties keep their loaded order. */
export function sortAnimals<T extends ListAnimal>(animals: T[], sort: SortState | null): T[] {
  if (!sort) return animals;
  const sign = sort.dir === "asc" ? 1 : -1;
  const indexed = animals.map((a, i) => ({ a, i }));
  indexed.sort((x, y) => {
    if (sort.key === "weight") {
      const wx = weightOf(x.a), wy = weightOf(y.a);
      if (wx === null && wy === null) return x.i - y.i;
      if (wx === null) return 1;
      if (wy === null) return -1;
      return wx === wy ? x.i - y.i : (wx - wy) * sign;
    }
    const c = collator.compare(textOf(x.a, sort.key), textOf(y.a, sort.key));
    return c === 0 ? x.i - y.i : c * sign;
  });
  return indexed.map((e) => e.a);
}

/** Clicking a column header: first click ascending, second descending, third goes back to the loaded order. */
export function nextSort(current: SortState | null, key: SortKey): SortState | null {
  if (!current || current.key !== key) return { key, dir: "asc" };
  return current.dir === "asc" ? { key, dir: "desc" } : null;
}

/** Distinct values for a filter dropdown, alphabetical. */
export function distinct<T extends ListAnimal>(animals: T[], field: "species" | "status"): string[] {
  return Array.from(new Set(animals.map((a) => a[field]).filter(Boolean))).sort((a, b) => a.localeCompare(b));
}
