// Run: npx tsx scripts/weigh-rows.test.ts   (pure logic test for the weigh form's Tag | Weight rows; no test framework needed)
import { analyseRows, blankRows, isBlankRow, newRow, parseWeight, parseWeightList, withTrailingBlank } from "../src/lib/weigh-rows";
let pass = 0, fail = 0;
const ok = (c: boolean, m: string) => { c ? pass++ : (fail++, console.log("FAIL:", m)); };

// 1. weights typed the ways people type them
ok(parseWeight("349") === 349, "whole number");
ok(parseWeight("331.5") === 331.5, "decimal point");
ok(parseWeight("331,5") === 331.5, "decimal comma");
ok(parseWeight(" 349 kg ") === 349 && parseWeight("349KG") === 349, "kg suffix and spaces");
ok(parseWeight(".5") === 0.5 && parseWeight("12.") === 12, "leading / trailing dot");
for (const bad of ["", "abc", "1e3", "3.3.3", "-5", "12 13", "kg", "0x10"]) ok(parseWeight(bad) === null, `rejects "${bad}"`);

// 2. complete rows become entries, in order; blank rows are ignored
let rows = [newRow("B0130", "162"), newRow(), newRow("  B0129 ", "193.5"), newRow()];
let a = analyseRows(rows);
ok(a.entries.length === 2 && a.entries[0].animal_number === "B0130" && a.entries[1].animal_number === "B0129" && a.entries[1].weight_kg === 193.5, "entries trimmed, ordered, blanks skipped");
ok(a.blocking === 0 && a.ready === 2 && a.problems.size === 0, "no problems");

// 3. half-filled rows block saving and say what is missing
rows = [newRow("B0130", ""), newRow("", "200"), newRow("B0128", "abc"), newRow("B0127", "0"), newRow("B0126", "2500"), newRow("B0125", "300")];
a = analyseRows(rows);
ok(a.blocking === 5 && a.entries.length === 1 && a.ready === 1, "five blocking rows, one good");
ok(a.problems.get(rows[0].id)?.weight === "Enter the weight", "missing weight named");
ok(a.problems.get(rows[1].id)?.tag === "Enter the tag", "missing tag named");
ok(!!a.problems.get(rows[2].id)?.weight && !!a.problems.get(rows[3].id)?.weight, "non-numbers and zero rejected");
ok(/2000/.test(a.problems.get(rows[4].id)?.weight ?? ""), "above the 2000 kg limit rejected");

// 4. a tag listed twice is a warning, not a blocker; the server keeps the first
rows = [newRow("A01", "300"), newRow("A02", "310"), newRow("A01", "305")];
a = analyseRows(rows);
ok(a.blocking === 0 && a.entries.length === 3 && a.ready === 2, "duplicate still sent, counted once as ready");
ok(a.problems.get(rows[2].id)?.warning !== undefined && a.problems.get(rows[0].id) === undefined, "warning on the later copy only");

// 5. an empty form has nothing to send and nothing wrong
a = analyseRows(blankRows());
ok(a.entries.length === 0 && a.blocking === 0 && a.ready === 0, "blank form");

// 6. there is always one empty row at the end
let r = withTrailingBlank([newRow("A01", "1")]);
ok(r.length === 2 && isBlankRow(r[1]), "blank row added after a filled one");
r = withTrailingBlank([newRow("A01", "1"), newRow()]);
ok(r.length === 2, "not added twice");
ok(withTrailingBlank([]).length === 1, "empty list gets one");
ok(blankRows(4).length === 4 && new Set(blankRows(4).map((x) => x.id)).size === 4, "rows have distinct ids");

// 7. pasted lists: the old one-line-per-animal format still works
const p = parseWeightList("A01 349\nA02, 331.5\r\nA03\t342\n\nnonsense\nA04 abc\nA05");
ok(p.rows.length === 3 && p.rows[0].tag === "A01" && p.rows[0].weight === "349" && p.rows[1].weight === "331.5" && p.rows[2].tag === "A03", "good lines become rows");
ok(p.bad.length === 3 && p.bad.includes("nonsense") && p.bad.includes("A04 abc") && p.bad.includes("A05"), "unreadable lines are returned, not lost");
const merged = analyseRows(p.rows);
ok(merged.entries.length === 3 && merged.blocking === 0, "pasted rows analyse cleanly");

console.log(`weigh-rows tests: ${pass} passed, ${fail} failed`); process.exit(fail ? 1 : 0);
