// Run: npx tsx scripts/tag-rows.test.ts   (pure logic test for the Sales / Add-animals "Tag | Weight | Price" rows)
import { analyseTagRows, blankTagRows, isBlankTagRow, newTagRow, parseTagList, withTrailingBlankTag } from "../src/lib/tag-rows";
let pass = 0, fail = 0;
const ok = (c: boolean, m: string) => { c ? pass++ : (fail++, console.log("FAIL:", m)); };

// 1. complete rows become entries in order; blank rows are ignored; price is optional
let rows = [newTagRow("A01", "324"), newTagRow(), newTagRow(" A02 ", "331,5", "335"), newTagRow("A03", "318 kg", "")];
let a = analyseTagRows(rows, { allowPrice: true });
ok(a.blocking === 0 && a.entries.length === 3, "three entries, no problems");
ok(a.entries[0].tag === "A01" && a.entries[0].price === undefined, "no price stays undefined (batch price applies)");
ok(a.entries[1].tag === "A02" && a.entries[1].weight === 331.5 && a.entries[1].price === 335, "tag trimmed, decimal comma, price read");
ok(a.entries[2].weight === 318, "kg suffix accepted");

// 2. half-filled and invalid rows block and say what is wrong
rows = [newTagRow("A01", ""), newTagRow("", "200"), newTagRow("A03", "abc"), newTagRow("A04", "0"), newTagRow("A05", "2500"), newTagRow("A06", "300", "x"), newTagRow("A07", "300", "-4")];
a = analyseTagRows(rows, { allowPrice: true });
ok(a.blocking === 7 && a.entries.length === 0, "seven blocking rows");
ok(a.problems.get(rows[0].id)?.weight === "Enter the weight" && a.problems.get(rows[1].id)?.tag === "Enter the tag", "missing parts named");
ok(!!a.problems.get(rows[2].id)?.weight && !!a.problems.get(rows[3].id)?.weight && /2000/.test(a.problems.get(rows[4].id)?.weight ?? ""), "bad weights rejected");
ok(!!a.problems.get(rows[5].id)?.price && !!a.problems.get(rows[6].id)?.price, "bad prices rejected");

// 3. a tag listed twice is an error on the SECOND row (selling / adding twice is a mistake), the first stays good
rows = [newTagRow("A01", "300"), newTagRow("A02", "310"), newTagRow("A01", "305")];
a = analyseTagRows(rows);
ok(a.blocking === 1 && a.entries.length === 2 && a.problems.get(rows[2].id)?.tag === "Tag listed twice" && !a.problems.has(rows[0].id), "duplicate flagged on the later row only");

// 4. with no price column, a typed price is refused rather than silently ignored
a = analyseTagRows([newTagRow("A01", "210", "50")]);
ok(a.blocking === 1 && !!a.problems.get(a.problems.keys().next().value as number)?.price, "price not accepted without a price column");

// 5. trailing blank row logic
let r = withTrailingBlankTag([newTagRow("A", "1")]);
ok(r.length === 2 && isBlankTagRow(r[1]), "adds a trailing blank");
ok(withTrailingBlankTag(r) === r, "does not add a second one");
ok(withTrailingBlankTag([]).length === 1 && blankTagRows(4).length === 4, "empty list and blankTagRows");

// 6. pasted lists: the old one-line-per-animal format still works, with or without a price
let p = parseTagList("A01 349\nA02, 331.5\r\nA03\t342\n\nnonsense\nA04 abc\nA05\nA06 1 2 3");
ok(p.rows.length === 3 && p.rows[0].weight === "349" && p.rows[1].weight === "331.5" && p.rows[2].tag === "A03", "weight-only lines become rows");
ok(p.bad.length === 4 && p.bad.includes("nonsense") && p.bad.includes("A06 1 2 3"), "unreadable lines are returned, not lost");
p = parseTagList("A01 324\nA02 331 335\nA03, 318", true);
ok(p.rows.length === 3 && p.rows[1].price === "335" && p.rows[0].price === "", "price column parsed when in use");
ok(parseTagList("A02 331 335", false).bad.length === 1, "a third item is not accepted without a price column");
const merged = analyseTagRows(p.rows, { allowPrice: true });
ok(merged.entries.length === 3 && merged.blocking === 0, "pasted rows analyse cleanly");

console.log(`tag-rows tests: ${pass} passed, ${fail} failed`); process.exit(fail ? 1 : 0);
