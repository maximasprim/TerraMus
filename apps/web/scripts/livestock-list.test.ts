// Run: npx tsx scripts/livestock-list.test.ts   (pure logic test for the Livestock page's search, filters and sorting)
import { distinct, filterAnimals, nextSort, NO_FILTERS, sortAnimals, type ListAnimal } from "../src/lib/livestock-list";
let pass = 0, fail = 0;
const ok = (c: boolean, m: string) => { c ? pass++ : (fail++, console.log("FAIL:", m)); };

const mk = (tag: string, o: Partial<ListAnimal> = {}): ListAnimal => ({
  animal_number: tag, ear_tag: null, rfid: null, name: null, species: "cattle", breed: null, category: null, sex: "male",
  current_weight: null, status: "active", health_status: "healthy", ...o });
const herd = [
  mk("B0130", { breed: "Boran", current_weight: "331.5" }),
  mk("B0129", { breed: "Boran", sex: "female", current_weight: "210" }),
  mk("B0131", { species: "goat", breed: "Galla", current_weight: null, name: "Wanjiru", ear_tag: "E-77" }),
  mk("A2", { status: "sold", current_weight: "400" }),
  mk("A10", { rfid: "9820001", current_weight: "95" }),
];
const tags = (l: ListAnimal[]) => l.map((a) => a.animal_number).join(",");

// search
ok(tags(filterAnimals(herd, { ...NO_FILTERS, q: "b013" })) === "B0130,B0131", "partial tag match, case-insensitive");
ok(tags(filterAnimals(herd, { ...NO_FILTERS, q: "BORAN" })) === "B0130,B0129", "breed match");
ok(tags(filterAnimals(herd, { ...NO_FILTERS, q: "boran female" })) === "B0129", "every word must match");
ok(tags(filterAnimals(herd, { ...NO_FILTERS, q: "wanjiru" })) === "B0131" && tags(filterAnimals(herd, { ...NO_FILTERS, q: "e-77" })) === "B0131", "name and ear tag");
ok(tags(filterAnimals(herd, { ...NO_FILTERS, q: "9820001" })) === "A10", "rfid");
ok(filterAnimals(herd, { ...NO_FILTERS, q: "   " }).length === 5, "blank search shows everything");
ok(filterAnimals(herd, { ...NO_FILTERS, q: "zzz" }).length === 0, "no match gives an empty list");
// filters
ok(tags(filterAnimals(herd, { ...NO_FILTERS, species: "goat" })) === "B0131", "species filter");
ok(tags(filterAnimals(herd, { ...NO_FILTERS, status: "sold" })) === "A2", "status filter");
ok(tags(filterAnimals(herd, { q: "a", species: "cattle", status: "active" })) === "B0130,B0129,A10", "search and filters combine");
// sort
ok(tags(sortAnimals(herd, { key: "id", dir: "asc" })) === "A2,A10,B0129,B0130,B0131", "tags sort naturally (A2 before A10)");
ok(tags(sortAnimals(herd, { key: "id", dir: "desc" })) === "B0131,B0130,B0129,A10,A2", "descending");
ok(tags(sortAnimals(herd, { key: "weight", dir: "asc" })) === "A10,B0129,B0130,A2,B0131", "weight ascending, no weight last");
ok(tags(sortAnimals(herd, { key: "weight", dir: "desc" })) === "A2,B0130,B0129,A10,B0131", "weight descending, no weight STILL last");
ok(tags(sortAnimals(herd, { key: "species", dir: "asc" })) === "A2,A10,B0130,B0129,B0131", "species then breed; ties keep loaded order");
ok(sortAnimals(herd, null) === herd, "no sort leaves the loaded order");
const before = tags(herd); sortAnimals(herd, { key: "id", dir: "asc" }); ok(tags(herd) === before, "input array is never mutated");
// header clicks cycle
let s = nextSort(null, "weight");
ok(s?.key === "weight" && s.dir === "asc", "first click ascending");
s = nextSort(s, "weight"); ok(s?.dir === "desc", "second click descending");
ok(nextSort(s, "weight") === null, "third click back to loaded order");
ok(nextSort({ key: "weight", dir: "desc" }, "id")?.dir === "asc", "a different column starts ascending");
ok(distinct(herd, "species").join() === "cattle,goat" && distinct(herd, "status").join() === "active,sold", "dropdown values");

console.log(`livestock-list tests: ${pass} passed, ${fail} failed`); process.exit(fail ? 1 : 0);
