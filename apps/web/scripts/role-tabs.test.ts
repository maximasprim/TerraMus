// Run: npx tsx scripts/role-tabs.test.ts   (the role switches for the Notifications page and the animal-page tabs)
import { ANIMAL_TAB_PERMISSIONS, canAccessPath, roleShowsTab } from "../src/lib/permissions";
let pass = 0, fail = 0;
const ok = (c: boolean, m: string) => { c ? pass++ : (fail++, console.log("FAIL:", m)); };

const all = ["notifications.view", ...Object.values(ANIMAL_TAB_PERMISSIONS)];
ok(Object.keys(ANIMAL_TAB_PERMISSIONS).join() === "Timeline,Health,Weights,Movements,Breeding,Dairy", "six switchable tabs, Overview is not one");
ok(roleShowsTab(all, "Health") && roleShowsTab(all, "Dairy"), "a role holding every switch sees every tab");
ok(!roleShowsTab(["animaltabs.timeline"], "Health") && roleShowsTab(["animaltabs.timeline"], "Timeline"), "an unticked tab is hidden, a ticked one shown");
ok(roleShowsTab([], "Overview") && roleShowsTab(["x"], "Overview"), "Overview can never be hidden");
ok(roleShowsTab(undefined, "Health"), "fails open until /auth/me has loaded");

ok(canAccessPath(all, "/admin/notifications"), "notifications open with the switch");
ok(!canAccessPath(["livestock.read"], "/admin/notifications"), "notifications closed without it");
ok(canAccessPath(undefined, "/admin/notifications"), "fails open while loading");
ok(canAccessPath(["livestock.read"], "/admin/livestock"), "other sections unchanged");

console.log(`role-tabs tests: ${pass} passed, ${fail} failed`); process.exit(fail ? 1 : 0);
