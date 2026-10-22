// Run: npx tsx scripts/offline-auth.test.ts
// A lost connection must never be treated as a lost session, and the cached profile must die with the session.
const store = new Map<string, string>();
(globalThis as unknown as { window: object }).window = {};
(globalThis as unknown as { localStorage: Storage }).localStorage = {
  getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v), removeItem: (k: string) => void store.delete(k),
  clear: () => store.clear(), key: () => null, length: 0,
} as Storage;

import { ApiError, clearTokens, isNetworkFailure, readCachedMe, setTokens, writeCachedMe } from "../src/lib/api";

let pass = 0, fail = 0;
const ok = (c: boolean, m: string) => { c ? pass++ : (fail++, console.log("FAIL:", m)); };

ok(isNetworkFailure(new TypeError("Failed to fetch")) === true, "fetch failure is a network failure");
ok(isNetworkFailure(new ApiError(401, "expired")) === false, "401 is NOT a network failure (session really is invalid)");
ok(isNetworkFailure(new ApiError(500, "boom")) === false, "5xx is NOT a network failure");
ok(isNetworkFailure(new SyntaxError("bad json")) === false, "other errors keep their existing behaviour");
ok(isNetworkFailure(undefined) === false && isNetworkFailure("x") === false, "non-errors are not network failures");

ok(readCachedMe() === null, "no cache initially");
writeCachedMe({ user: { full_name: "Jane" }, permissions: ["feedlot.weigh"] });
ok((readCachedMe<{ user: { full_name: string } }>())?.user.full_name === "Jane", "cache round-trips");
setTokens("a", "r");
ok(store.has("farm.access_token") && store.has("farm.me_cache"), "tokens and cache present while signed in");
clearTokens();
ok(!store.has("farm.access_token") && !store.has("farm.refresh_token") && readCachedMe() === null, "logout wipes tokens AND cached profile");
store.set("farm.me_cache", "{corrupt");
ok(readCachedMe() === null, "corrupt cache is ignored, not thrown");

console.log(`offline auth tests: ${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
