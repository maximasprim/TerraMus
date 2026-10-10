// Runs the REAL apps/web/src/lib/permissions.ts against the backend's default roles.
const OUT = process.env.AUDIT_OUT || ".";
const ts = require(process.cwd() + "/node_modules/typescript");
const fs = require("fs"), assert = require("assert");
const js = ts.transpileModule(fs.readFileSync("src/lib/permissions.ts", "utf8"), { compilerOptions: { module: "commonjs", target: "es2019" } }).outputText;
const m = { exports: {} }; new Function("module", "exports", js)(m, m.exports);
const P = m.exports, be = JSON.parse(fs.readFileSync(OUT + "/be_perms.json", "utf8"));
console.log("\n######## D) real permission functions x backend default roles ########");
let bad = 0;
assert.ok(be.catalog.length > 0 && Object.keys(be.roles).length > 0, "no permission data extracted - refusing to pass vacuously");
const nav = P.SECTION_PERMISSIONS.filter((s) => s.prefix !== "/admin/reports" && s.prefix.split("/").length === 3);
for (const [role, grants] of Object.entries(be.roles)) {
  const open = nav.filter((s) => P.hasPermission(grants, s.permission)).map((s) => s.prefix.replace("/admin/", ""));
  const landing = P.firstAccessiblePath(grants);
  const realSections = open.filter((x) => x !== "notifications");   // notifications is open to everyone
  const staff = grants.length > 0;   // e.g. "Customer" has no permissions by design (ownership checks, not RBAC)
  const flag = realSections.length === 0 ? (staff ? "  <-- NO usable section!" : "  (not a staff role - fine)") : "";
  if (staff && realSections.length === 0) bad++;
  console.log(`  ${role.padEnd(18)} lands on ${landing.replace("/admin/", "").padEnd(14)} sees ${String(open.length).padStart(2)}/${nav.length}: ${open.join(", ")}${flag}`);
}
assert.equal(P.requiredPermission("/admin/livestock/123"), "livestock.read");        // detail pages inherit their section
assert.equal(P.requiredPermission("/admin/livestock/new"), "livestock.create");      // ...except pages that need a write permission
assert.equal(P.requiredPermission("/admin/crops/new"), "crops.create");
assert.equal(P.requiredPermission("/admin/inventory/valuation"), "inventory.read");
assert.equal(P.requiredPermission("/admin/reports/profitability"), "reports.view");
assert.equal(P.requiredPermission("/admin/something-new"), null);                    // unknown paths fail open
assert.equal(P.requiredPermission("/admin/livestockfoo"), null);                     // prefix match is segment-aware
assert.equal(P.hasPermission(undefined, "finance.read"), true);                      // not loaded yet -> fail open
assert.equal(P.firstAccessiblePath([]), "/admin/notifications");                     // zero permissions still lands somewhere valid (the only open section)
console.log(bad ? `\n${bad} role(s) cannot reach any real section` : "\n  every default role can reach at least one real section; unit assertions passed");
process.exit(bad ? 1 : 0);
