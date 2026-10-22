// Offline queue for weigh days.
//
// A weigh-in often happens at a crush pen with no signal. When the device is offline (or the server
// cannot be reached) the weigh day is saved here, on the device, and sent when the connection returns.
//
// Replays are safe: the server skips an animal already weighed on that date, so a retry after a
// timed-out request cannot double-record. This module has no browser or framework imports on purpose
// so that its decision logic can be tested on its own.

export interface WeighEntry { animal_number: string; weight_kg: number }

export interface QueuedWeighDay {
  id: string;
  createdAt: string;
  weighed_on: string;
  scale_label?: string;
  notes?: string;
  entries: WeighEntry[];
  status: "pending" | "failed";
  error?: string;
}

export interface KV { getItem(key: string): string | null; setItem(key: string, value: string): void }
export const QUEUE_KEY = "terramus.feedlot.weighQueue.v1";

export function loadQueue(store: KV): QueuedWeighDay[] {
  try {
    const raw = store.getItem(QUEUE_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((q): q is QueuedWeighDay =>
      !!q && typeof q === "object" && typeof (q as QueuedWeighDay).id === "string" && Array.isArray((q as QueuedWeighDay).entries));
  } catch {
    return [];   // a corrupt entry must never stop the app from working
  }
}

export function saveQueue(store: KV, queue: QueuedWeighDay[]): void {
  store.setItem(QUEUE_KEY, JSON.stringify(queue));
}

function newId(): string {
  const c = (globalThis as { crypto?: { randomUUID?: () => string } }).crypto;
  return c?.randomUUID ? c.randomUUID() : `q-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export function enqueue(store: KV, item: Pick<QueuedWeighDay, "weighed_on" | "scale_label" | "notes" | "entries">): QueuedWeighDay {
  const q: QueuedWeighDay = { ...item, id: newId(), createdAt: new Date().toISOString(), status: "pending" };
  saveQueue(store, [...loadQueue(store), q]);
  return q;
}

export function discard(store: KV, id: string): void {
  saveQueue(store, loadQueue(store).filter((q) => q.id !== id));
}

/** Put a failed item back to pending (e.g. after the user fixed the cause). */
export function retry(store: KV, id: string): void {
  saveQueue(store, loadQueue(store).map((q) => (q.id === id ? { ...q, status: "pending", error: undefined } : q)));
}

/** True for "could not reach the server" - as opposed to the server answering with an error. */
export function isNetworkError(e: unknown): boolean {
  if (e && typeof e === "object" && typeof (e as { status?: unknown }).status === "number") return false;   // ApiError: the server answered
  return e instanceof TypeError || (typeof navigator !== "undefined" && navigator.onLine === false);
}

export interface SendResult { recorded: number; problems?: number }
export type Sender = (item: QueuedWeighDay) => Promise<SendResult>;

export interface SyncOutcome {
  synced: number;            // queued weigh days delivered
  animalsRecorded: number;
  failed: number;            // rejected by the server: need a person to look at them
  stillPending: number;
  stoppedBecause: "done" | "offline" | "login" | "server";
}

/**
 * Send queued weigh days oldest-first.
 *  - delivered            -> removed from the queue
 *  - rejected (4xx)       -> kept, marked failed with the server's message; never retried automatically
 *  - 401 / no connection / 5xx / 408 / 429 -> stop and keep everything pending for the next attempt
 */
export async function syncQueue(store: KV, send: Sender): Promise<SyncOutcome> {
  const out: SyncOutcome = { synced: 0, animalsRecorded: 0, failed: 0, stillPending: 0, stoppedBecause: "done" };
  for (const item of loadQueue(store).filter((q) => q.status === "pending")) {
    try {
      const r = await send(item);
      discard(store, item.id);
      out.synced += 1;
      out.animalsRecorded += r.recorded;
    } catch (e) {
      const status = e && typeof e === "object" ? (e as { status?: unknown }).status : undefined;
      if (typeof status === "number" && status >= 400 && status < 500 && ![401, 408, 429].includes(status)) {
        const msg = e instanceof Error ? e.message : "Rejected by the server";
        saveQueue(store, loadQueue(store).map((q) => (q.id === item.id ? { ...q, status: "failed", error: msg } : q)));
        out.failed += 1;
        continue;
      }
      out.stoppedBecause = status === 401 ? "login" : isNetworkError(e) ? "offline" : "server";
      break;
    }
  }
  out.stillPending = loadQueue(store).filter((q) => q.status === "pending").length;
  return out;
}
