// Run: npx tsx scripts/idle.test.ts   (pure logic test for the inactivity sign-out)
import { idleMessage, idleStatus, keepAliveEveryMs, secondsLeft } from "../src/lib/idle";
let pass = 0, fail = 0;
const ok = (c: boolean, m: string) => { c ? pass++ : (fail++, console.log("FAIL:", m)); };
const MIN = 60_000, T = 1_000_000_000;

ok(idleStatus(T + 5 * MIN, T, 60) === "active", "recent activity is active");
ok(idleStatus(T + 58 * MIN + 1, T, 60) === "warning", "last two minutes warn");
ok(idleStatus(T + 60 * MIN, T, 60) === "expired", "at the limit it expires");
ok(idleStatus(T + 999 * MIN, T, 0) === "active", "0 disables");
ok(idleStatus(T + 999 * MIN, T, undefined as unknown as number) === "active", "missing disables");
ok(secondsLeft(T + 59 * MIN, T, 60) === 60, "seconds left");
ok(secondsLeft(T + 90 * MIN, T, 60) === 0, "never negative");
ok(secondsLeft(T, T, 0) === Infinity, "off means unlimited");
ok(keepAliveEveryMs(60) === 10 * MIN && keepAliveEveryMs(20) === 6 * MIN, "keep-alive stays well inside the limit");
ok(idleMessage(60) === "You were signed out after 1 hour of inactivity." && idleMessage(90).includes("90 minutes"), "messages");
console.log(`idle: ${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
