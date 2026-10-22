// Run: npx tsx scripts/offline-queue.test.ts   (pure logic test for the offline weigh-day queue; no test framework needed)
import { enqueue, loadQueue, syncQueue, discard, retry, isNetworkError, QUEUE_KEY, type KV, type QueuedWeighDay } from "../src/app/admin/feedlot/offline-queue";
let pass = 0, fail = 0;
const ok = (c: boolean, m: string) => { c ? pass++ : (fail++, console.log("FAIL:", m)); };
const mem = (): KV & { m: Map<string, string> } => { const m = new Map<string, string>(); return { m, getItem: (k) => m.get(k) ?? null, setItem: (k, v) => void m.set(k, v) }; };
class Rejected extends Error { constructor(public status: number, msg: string) { super(msg); } }
const day = (d: string) => ({ weighed_on: d, entries: [{ animal_number: "A01", weight_kg: 300 }, { animal_number: "A02", weight_kg: 310 }] });

(async () => {
  // 1. all delivered, oldest first, queue emptied
  let s = mem(); enqueue(s, day("2026-07-01")); enqueue(s, day("2026-07-02"));
  const order: string[] = [];
  let o = await syncQueue(s, async (q) => { order.push(q.weighed_on); return { recorded: 2 }; });
  ok(order.join() === "2026-07-01,2026-07-02", "oldest first");
  ok(o.synced === 2 && o.animalsRecorded === 4 && o.stoppedBecause === "done" && loadQueue(s).length === 0, "all delivered + removed");

  // 2. offline: nothing lost, stops at the first failure, later items untouched
  s = mem(); enqueue(s, day("2026-07-01")); enqueue(s, day("2026-07-02"));
  let calls = 0;
  o = await syncQueue(s, async () => { calls++; throw new TypeError("Failed to fetch"); });
  ok(calls === 1 && o.stoppedBecause === "offline" && o.stillPending === 2 && loadQueue(s).length === 2, "offline keeps everything, stops early");

  // 3. server rejects one (422): marked failed, and does NOT block the next one
  s = mem(); enqueue(s, day("2026-07-01")); enqueue(s, day("2026-07-02"));
  o = await syncQueue(s, async (q) => { if (q.weighed_on === "2026-07-01") throw new Rejected(422, "weighed_on is in the future"); return { recorded: 2 }; });
  let q = loadQueue(s);
  ok(o.failed === 1 && o.synced === 1 && q.length === 1 && q[0].status === "failed" && q[0].error === "weighed_on is in the future", "4xx marks failed, continues");
  // a failed item is not retried automatically, until the user retries it
  calls = 0; o = await syncQueue(s, async () => { calls++; return { recorded: 1 }; });
  ok(calls === 0 && o.synced === 0, "failed items are not auto-retried");
  retry(s, q[0].id); o = await syncQueue(s, async () => ({ recorded: 2 }));
  ok(o.synced === 1 && loadQueue(s).length === 0, "retry sends it");

  // 4. expired login (401) stops and says why; 5xx/429/408 keep pending
  for (const [status, why] of [[401, "login"], [500, "server"], [503, "server"], [429, "server"], [408, "server"]] as const) {
    s = mem(); enqueue(s, day("2026-07-01"));
    o = await syncQueue(s, async () => { throw new Rejected(status, "x"); });
    ok(o.stoppedBecause === why && o.stillPending === 1 && loadQueue(s)[0].status === "pending", `status ${status} -> stop (${why}), keep pending`);
  }

  // 5. discard, corrupt storage, wrong shapes
  s = mem(); const a = enqueue(s, day("2026-07-01")); discard(s, a.id); ok(loadQueue(s).length === 0, "discard");
  s = mem(); s.setItem(QUEUE_KEY, "{not json"); ok(loadQueue(s).length === 0, "corrupt JSON tolerated");
  s.setItem(QUEUE_KEY, JSON.stringify({ a: 1 })); ok(loadQueue(s).length === 0, "non-array tolerated");
  s.setItem(QUEUE_KEY, JSON.stringify([{ id: "x" }, null, 5, { id: "ok", entries: [] }])); ok(loadQueue(s).length === 1, "malformed items dropped, valid kept");
  s = mem(); enqueue(s, day("2026-07-01")); ok(typeof loadQueue(s)[0].id === "string" && loadQueue(s)[0].status === "pending", "enqueue shape");

  // 6. network-error classification: a server answer is never mistaken for 'offline'
  ok(isNetworkError(new TypeError("Failed to fetch")) === true, "TypeError = network");
  ok(isNetworkError(new Rejected(500, "boom")) === false, "ApiError-like = not network");
  ok(isNetworkError(new Error("other")) === false, "plain Error = not network");

  // 7. a poisoned item never starves the rest and nothing is dropped silently
  s = mem(); for (const d of ["2026-07-01", "2026-07-02", "2026-07-03"]) enqueue(s, day(d));
  o = await syncQueue(s, async (q) => { if (q.weighed_on === "2026-07-02") throw new Rejected(400, "bad"); return { recorded: 2 }; });
  ok(o.synced === 2 && o.failed === 1 && loadQueue(s).length === 1, "middle failure isolated");
  console.log(`queue tests: ${pass} passed, ${fail} failed`); process.exit(fail ? 1 : 0);
})();
