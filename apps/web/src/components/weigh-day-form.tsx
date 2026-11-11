"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import { Button, Card, ErrorState, Input } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import {
  discard, enqueue, isNetworkError, loadQueue, retry, syncQueue,
  type KV, type QueuedWeighDay, type Sender,
} from "@/app/admin/feedlot/offline-queue";
import { analyseRows, blankRows, isBlankRow, MAX_WEIGHT_KG, parseWeight, parseWeightList, withTrailingBlank, type WeighRow } from "@/lib/weigh-rows";
import { useCan, useMe } from "@/lib/use-auth";

// One weigh-day form for the whole app: the Feedlot "Weigh day" tab and the Livestock page's "Record weights".
// Tag and weight are separate boxes, one row per animal. Offline saving, preview and the result list are unchanged.

interface WeighResult {
  dry_run: boolean; recorded: number; session_id: string | null;
  results: { animal: string; status: string; flags?: string[]; existing_kg?: number; detail?: string }[];
}

const errMsg = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback);
const todayIso = () => new Date().toISOString().slice(0, 10);
const post = (body: object) => apiFetch<WeighResult>("/api/v1/feedlot/weigh-days", { method: "POST", body: JSON.stringify(body) });

function getStore(): KV | null {
  try { return typeof window === "undefined" ? null : window.localStorage; } catch { return null; }   // blocked in some private modes
}

/** After weights are recorded, refresh everything that shows them (feedlot figures, the animal list, an animal's own page). */
function refreshAfterRecording(queryClient: QueryClient) {
  for (const key of ["feedlot", "livestock", "animal"]) queryClient.invalidateQueries({ queryKey: [key] });
}

/** The device-saved weigh days: load them, and send them whenever the connection is there. */
export function useWeighQueue() {
  const queryClient = useQueryClient();
  const [queue, setQueue] = useState<QueuedWeighDay[]>([]);
  const [online, setOnline] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);
  const syncing = useRef(false);

  const refreshQueue = useCallback(() => { const s = getStore(); setQueue(s ? loadQueue(s) : []); }, []);

  const sync = useCallback(async () => {
    const s = getStore();
    if (!s || syncing.current || loadQueue(s).every((q) => q.status !== "pending")) return;
    syncing.current = true;
    try {
      const send: Sender = async (item) => {
        const d = await post({ weighed_on: item.weighed_on, scale_label: item.scale_label, notes: item.notes, entries: item.entries });
        return { recorded: d.recorded };
      };
      const o = await syncQueue(s, send);
      refreshQueue();
      if (o.synced > 0) {
        refreshAfterRecording(queryClient);
        setNotice(`Sent ${o.synced} saved weigh day(s) (${o.animalsRecorded} animals recorded).${o.failed ? ` ${o.failed} could not be accepted: see below.` : ""}`);
      } else if (o.stoppedBecause === "login") setNotice("Please sign in again to send the saved weights. They are safe on this device.");
      else if (o.failed > 0) setNotice(`${o.failed} saved weigh day(s) were rejected: see below.`);
    } finally { syncing.current = false; }
  }, [queryClient, refreshQueue]);

  useEffect(() => {
    refreshQueue();
    setOnline(typeof navigator === "undefined" ? true : navigator.onLine);
    const goOnline = () => { setOnline(true); void sync(); };
    const goOffline = () => setOnline(false);
    window.addEventListener("online", goOnline);
    window.addEventListener("offline", goOffline);
    if (navigator.onLine) void sync();
    return () => { window.removeEventListener("online", goOnline); window.removeEventListener("offline", goOffline); };
  }, [refreshQueue, sync]);

  return { queue, online, notice, setNotice, refreshQueue, sync };
}

function Panel({ split, className, children }: { split: boolean; className?: string; children: ReactNode }) {
  return split ? <Card className={className}>{children}</Card> : <div className={className}>{children}</div>;
}

type QueueState = ReturnType<typeof useWeighQueue>;

/** Offline banner, the "sent" notice and the list of weigh days waiting on this device (shared by both forms). */
function WeighQueueSection({ q: { queue, online, notice, refreshQueue, sync } }: { q: QueueState }) {
  const pending = queue.filter((x) => x.status === "pending").length;
  return (
    <>
      {!online && <div className="rounded border border-amber-300 bg-amber-50 px-4 py-2 text-sm text-amber-900">You are offline. Weights you save are kept on this device and sent when the connection returns.</div>}
      {notice && <div className="rounded border border-forest/30 bg-forest/5 px-4 py-2 text-sm text-forest">{notice}</div>}
      {queue.length > 0 && (
        <Card>
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-display text-lg text-forest">Waiting to be sent <span className="text-sm font-normal text-muted">({queue.length})</span></h2>
            <Button variant="ghost" disabled={!online || pending === 0} onClick={() => void sync()}>Send now</Button>
          </div>
          {queue.map((q) => (
            <div key={q.id} className="flex items-center justify-between gap-3 border-t border-hairline/60 py-2 text-sm">
              <div>
                <span className="font-medium">{q.weighed_on}</span> · {q.entries.length} animals{q.scale_label ? ` · ${q.scale_label}` : ""}
                {q.status === "failed" ? <div className="text-xs text-clay">Rejected: {q.error}</div> : <div className="text-xs text-muted">Waiting for a connection</div>}
              </div>
              <div className="flex gap-2">
                {q.status === "failed" && <Button variant="ghost" onClick={() => { const s = getStore(); if (s) { retry(s, q.id); refreshQueue(); void sync(); } }}>Try again</Button>}
                <Button variant="ghost" onClick={() => { if (window.confirm("Discard these saved weights? They have not been recorded yet.")) { const s = getStore(); if (s) { discard(s, q.id); refreshQueue(); } } }}>Discard</Button>
              </div>
            </div>))}
        </Card>
      )}
    </>
  );
}

const CELL = "w-full rounded-md border bg-white px-3 py-2.5 text-base focus:border-brass focus:outline-none sm:py-2 sm:text-sm";

function MultiWeighForm({ layout = "split", title = "Record a weigh day" }: { layout?: "split" | "stacked"; title?: string | null }) {
  const queryClient = useQueryClient();
  const { queue, online, notice, setNotice, refreshQueue, sync } = useWeighQueue();
  const [date, setDate] = useState(todayIso());
  const [scale, setScale] = useState("");
  const [rows, setRows] = useState<WeighRow[]>(() => blankRows());
  const [touched, setTouched] = useState<Set<number>>(new Set());
  const [attempted, setAttempted] = useState(false);
  const [pasteOpen, setPasteOpen] = useState(false);
  const [pasteText, setPasteText] = useState("");
  const [pasteBad, setPasteBad] = useState<string[]>([]);
  const [result, setResult] = useState<WeighResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inputs = useRef(new Map<string, HTMLInputElement>());
  const split = layout === "split";
  const analysis = useMemo(() => analyseRows(rows), [rows]);

  const setCell = (id: number, field: "tag" | "weight", value: string) => {
    setRows((prev) => withTrailingBlank(prev.map((r) => (r.id === id ? { ...r, [field]: value } : r))));
    setResult(null);
  };
  const removeRow = (id: number) => { setRows((prev) => withTrailingBlank(prev.filter((r) => r.id !== id))); setResult(null); };
  const touch = (id: number) => setTouched((prev) => (prev.has(id) ? prev : new Set(prev).add(id)));
  const focusCell = (id: number, field: "tag" | "weight") => inputs.current.get(`${id}:${field}`)?.focus();
  const resetList = () => { setRows(blankRows()); setTouched(new Set()); setAttempted(false); setResult(null); setError(null); };

  const addPasted = () => {
    const { rows: added, bad } = parseWeightList(pasteText);
    setRows((prev) => withTrailingBlank([...prev.filter((r) => !isBlankRow(r)), ...added]));
    setPasteBad(bad);
    setPasteText(bad.join("\n"));            // leave only the lines that were not understood, ready to fix
    if (bad.length === 0) setPasteOpen(false);
    setResult(null);
  };

  const payload = { weighed_on: date, scale_label: scale || undefined, entries: analysis.entries };
  const keepOnDevice = () => {
    const s = getStore();
    if (!s) { setError("This browser cannot keep data offline. Reconnect before saving."); return; }
    enqueue(s, payload);
    refreshQueue(); resetList();
    setNotice(`Saved on this device (${payload.entries.length} animals). It will be sent automatically when you are back online.`);
  };

  /** True when everything entered is complete; otherwise shows what is wrong and stops. */
  const checkRows = (): boolean => {
    if (analysis.blocking > 0) {
      setAttempted(true);
      setError("Some rows are missing a tag or a valid weight. Fix the highlighted rows, or clear them, then try again.");
      return false;
    }
    return true;
  };

  const preview = async () => {
    setNotice(null);
    if (!checkRows()) return;
    setBusy(true); setError(null);
    try { setResult(await post({ ...payload, dry_run: true })); }
    catch (e) { setError(isNetworkError(e) ? "Preview needs a connection. You can still save: the weights are kept on this device and sent later." : errMsg(e, "Could not preview")); }
    finally { setBusy(false); }
  };
  const save = async () => {
    setNotice(null);
    if (!checkRows()) return;
    if (typeof navigator !== "undefined" && !navigator.onLine) { keepOnDevice(); return; }
    setBusy(true); setError(null);
    try {
      const d = await post({ ...payload, dry_run: false });
      setResult(d); refreshAfterRecording(queryClient);
    } catch (e) {
      if (isNetworkError(e)) keepOnDevice(); else setError(errMsg(e, "Could not record weights"));
    } finally { setBusy(false); }
  };

  const pending = queue.filter((q) => q.status === "pending").length;
  const nothingToSend = analysis.entries.length === 0 && analysis.blocking === 0;
  const showProblems = (id: number) => attempted || touched.has(id);

  return (
    <div className="space-y-6">
      <WeighQueueSection q={{ queue, online, notice, setNotice, refreshQueue, sync }} />
      <div className={split ? "grid gap-6 lg:grid-cols-2" : "space-y-4"}>
        <Panel split={split} className="space-y-3">
          {title && <h2 className="font-display text-lg text-forest">{title}</h2>}
          <div className="grid grid-cols-2 gap-3">
            <Input label="Weigh date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
            <Input label="Scale (optional)" value={scale} onChange={(e) => setScale(e.target.value)} placeholder="e.g. Crush pen scale" />
          </div>

          <div>
            <div className="mb-1 grid grid-cols-[1.75rem_1fr_1fr_2.25rem] gap-2 text-sm font-medium text-ink">
              <span /><span>Tag</span><span>Weight (kg)</span><span />
            </div>
            <div className="space-y-2">
              {rows.map((r, i) => {
                const p = analysis.problems.get(r.id);
                const shown = showProblems(r.id);
                return (
                  <div key={r.id} onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) touch(r.id); }}>
                    <div className="grid grid-cols-[1.75rem_1fr_1fr_2.25rem] items-center gap-2">
                      <span className="text-right text-xs text-muted">{i + 1}</span>
                      <input
                        ref={(el) => { if (el) inputs.current.set(`${r.id}:tag`, el); else inputs.current.delete(`${r.id}:tag`); }}
                        aria-label={`Tag, row ${i + 1}`} value={r.tag} placeholder="e.g. B0130"
                        autoCapitalize="characters" autoCorrect="off" autoComplete="off" spellCheck={false} enterKeyHint="next"
                        onChange={(e) => setCell(r.id, "tag", e.target.value)}
                        onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); focusCell(r.id, "weight"); } }}
                        className={`${CELL} font-mono ${shown && p?.tag ? "border-clay" : "border-hairline"}`}
                      />
                      <input
                        ref={(el) => { if (el) inputs.current.set(`${r.id}:weight`, el); else inputs.current.delete(`${r.id}:weight`); }}
                        aria-label={`Weight in kg, row ${i + 1}`} value={r.weight} placeholder="e.g. 349"
                        inputMode="decimal" autoComplete="off" enterKeyHint="next"
                        onChange={(e) => setCell(r.id, "weight", e.target.value)}
                        onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); const next = rows[i + 1]; if (next) focusCell(next.id, "tag"); } }}
                        className={`${CELL} ${shown && p?.weight ? "border-clay" : "border-hairline"}`}
                      />
                      <button type="button" aria-label={`Remove row ${i + 1}`} disabled={isBlankRow(r)} onClick={() => removeRow(r.id)}
                        className="h-9 rounded text-muted hover:text-clay disabled:opacity-20">✕</button>
                    </div>
                    {shown && (p?.tag || p?.weight) && <p className="ml-8 mt-0.5 text-xs text-clay">{[p.tag, p.weight].filter(Boolean).join(" · ")}</p>}
                    {p?.warning && !(p.tag || p.weight) && <p className="ml-8 mt-0.5 text-xs text-amber-700">{p.warning}</p>}
                  </div>
                );
              })}
            </div>
          </div>

          <div>
            <button type="button" onClick={() => setPasteOpen((o) => !o)} className="text-xs text-forest underline">
              {pasteOpen ? "Hide pasted list" : "Paste a list instead"}
            </button>
            {pasteOpen && (
              <div className="mt-2 space-y-2">
                <label htmlFor="weigh-paste" className="block text-xs text-muted">One animal per line: tag, then weight in kg (for example A01 349). Use a dot for decimals.</label>
                <textarea id="weigh-paste" rows={6} value={pasteText} onChange={(e) => setPasteText(e.target.value)} placeholder={"A01 349\nA02 331.5\nA03, 342"}
                  className="w-full rounded-md border border-hairline bg-white px-3 py-2 font-mono text-sm focus:border-brass focus:outline-none" />
                <Button variant="ghost" disabled={!pasteText.trim()} onClick={addPasted}>Add to the list</Button>
                {pasteBad.length > 0 && <p className="text-xs text-clay">{pasteBad.length} line(s) not understood and left above for you to fix: {pasteBad.slice(0, 3).join(" | ")}</p>}
              </div>
            )}
          </div>

          <p className="text-xs text-muted">
            {analysis.ready} animal(s) ready
            {analysis.blocking > 0 && <span className="text-clay"> · {analysis.blocking} row(s) need a tag or a valid weight</span>}
          </p>
          {error && <ErrorState message={error} />}
          <div className="flex flex-wrap gap-2">
            <Button variant="ghost" disabled={nothingToSend || busy || !online} onClick={() => void preview()}>Preview (nothing saved)</Button>
            <Button disabled={nothingToSend || busy} onClick={() => void save()}>{online ? "Save weights" : "Save on this device"}</Button>
            {rows.some((r) => !isBlankRow(r)) && (
              <Button variant="ghost" disabled={busy} onClick={() => {
                const unsaved = analysis.entries.length > 0 && !(result && !result.dry_run);
                if (!unsaved || window.confirm("Clear the whole list? Nothing has been saved yet.")) resetList();
              }}>Clear list</Button>
            )}
          </div>
        </Panel>

        <Panel split={split} className={split ? undefined : "border-t border-hairline pt-4"}>
          <h2 className="mb-3 font-display text-lg text-forest">{result ? (result.dry_run ? "Preview" : "Saved") : "Result"}</h2>
          {!result && <p className="text-sm text-muted">Duplicates for the same day are skipped, unknown tags are reported, and unusually large changes are flagged for a second look. Sending the same weigh day twice is harmless.</p>}
          {result && (
            <>
              <p className="mb-3 text-sm">{result.dry_run ? `${result.recorded} would be recorded` : `${result.recorded} recorded`}</p>
              <div className="max-h-96 overflow-y-auto"><table className="w-full text-sm"><tbody>
                {result.results.map((r) => (
                  <tr key={r.animal} className="border-b border-hairline/60">
                    <td className="py-1.5 font-mono">{r.animal}</td>
                    <td className={["recorded", "updated", "would_record"].includes(r.status) ? "text-forest" : "text-clay"}>{r.status.replace(/_/g, " ")}</td>
                    <td className="text-xs text-amber-700">{r.flags?.join(", ")}</td>
                  </tr>))}
              </tbody></table></div>
            </>
          )}
        </Panel>
      </div>
    </div>
  );
}

/** One animal at a time: for people who weigh slowly (a few minutes per animal). Each weight is saved the moment it is
 * entered, so nothing is lost between animals. Same endpoint, same offline saving as the full form. */
function SingleWeighForm({ title = "Record a weight" }: { title?: string | null }) {
  const queryClient = useQueryClient();
  const { queue, online, notice, setNotice, refreshQueue, sync } = useWeighQueue();
  const [date, setDate] = useState(todayIso());
  const [scale, setScale] = useState("");
  const [tag, setTag] = useState("");
  const [weight, setWeight] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<{ tag: string; kg: number; note?: string; offline?: boolean } | null>(null);
  const [replace, setReplace] = useState<{ tag: string; kg: number; existing: number } | null>(null);
  const [recent, setRecent] = useState<{ tag: string; kg: number; offline?: boolean }[]>([]);
  const tagRef = useRef<HTMLInputElement>(null);
  const weightRef = useRef<HTMLInputElement>(null);

  const next = (t: string, kgValue: number, note?: string, offline?: boolean) => {
    setSaved({ tag: t, kg: kgValue, note, offline }); setRecent((r) => [{ tag: t, kg: kgValue, offline }, ...r].slice(0, 6));
    setTag(""); setWeight(""); setReplace(null); setError(null);
    tagRef.current?.focus();
  };

  const submit = async (overwrite = false, forTag?: string, forKg?: number) => {
    setNotice(null); setSaved(null);
    const t = (forTag ?? tag).trim();
    const w = forKg ?? parseWeight(weight);
    if (!t) { setError("Enter the animal's tag."); tagRef.current?.focus(); return; }
    if (w === null || w <= 0 || w > MAX_WEIGHT_KG) { setError(`Enter the weight in kg (a number above 0, up to ${MAX_WEIGHT_KG}).`); weightRef.current?.focus(); return; }
    const entries = [{ animal_number: t, weight_kg: w }];
    const keepOnDevice = () => {
      const s = getStore();
      if (!s) { setError("This browser cannot keep data offline. Reconnect before saving."); return; }
      enqueue(s, { weighed_on: date, scale_label: scale || undefined, entries });
      refreshQueue(); next(t, w, "Saved on this device. It will be sent when you are back online.", true);
    };
    if (typeof navigator !== "undefined" && !navigator.onLine) { keepOnDevice(); return; }
    setBusy(true); setError(null);
    try {
      const d = await post({ weighed_on: date, scale_label: scale || undefined, entries, dry_run: false, ...(overwrite ? { overwrite: true } : {}) });
      const r = d.results[0];
      if (r && (r.status === "recorded" || r.status === "updated")) {
        refreshAfterRecording(queryClient);
        next(t, w, r.flags?.length ? "Saved, but this is a big change from the last weight. Please check it is right." : undefined);
      } else if (r?.status === "already_recorded") {
        setReplace({ tag: t, kg: w, existing: r.existing_kg ?? 0 });
      } else if (r?.status === "unknown_animal") {
        setError(`No animal with the tag ${t}. Check the tag and try again.`); tagRef.current?.focus();
      } else if (r?.status === "inactive_animal") {
        setError(`${t} is no longer on the farm (${r.detail ?? "inactive"}), so a weight cannot be added.`);
      } else if (r?.status === "cycle_closed") {
        setError(r.detail ?? "This animal's production cycle is closed.");
      } else {
        setError("The weight was not saved. Please try again.");
      }
    } catch (e) {
      if (isNetworkError(e)) keepOnDevice(); else setError(errMsg(e, "Could not record the weight"));
    } finally { setBusy(false); }
  };

  const big = "w-full rounded-md border border-hairline bg-white px-4 py-3 text-lg focus:border-brass focus:outline-none";
  return (
    <div className="space-y-4">
      <WeighQueueSection q={{ queue, online, notice, setNotice, refreshQueue, sync }} />
      <div className="space-y-4">
        {title && <h2 className="font-display text-lg text-forest">{title}</h2>}
        <div className="grid grid-cols-2 gap-3">
          <Input label="Weigh date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          <Input label="Scale (optional)" value={scale} onChange={(e) => setScale(e.target.value)} placeholder="e.g. Crush pen scale" />
        </div>
        <div>
          <label htmlFor="single-tag" className="mb-1 block text-sm font-medium text-ink">Animal tag</label>
          <input id="single-tag" ref={tagRef} value={tag} placeholder="e.g. B0130" autoFocus
            autoCapitalize="characters" autoCorrect="off" autoComplete="off" spellCheck={false} enterKeyHint="next"
            onChange={(e) => { setTag(e.target.value); setError(null); setReplace(null); }}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); weightRef.current?.focus(); } }}
            className={`${big} font-mono`} />
        </div>
        <div>
          <label htmlFor="single-weight" className="mb-1 block text-sm font-medium text-ink">Weight (kg)</label>
          <input id="single-weight" ref={weightRef} value={weight} placeholder="e.g. 349" inputMode="decimal" autoComplete="off" enterKeyHint="done"
            onChange={(e) => { setWeight(e.target.value); setError(null); setReplace(null); }}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); if (!busy) void submit(); } }}
            className={big} />
        </div>
        {error && <ErrorState message={error} />}
        {replace && (
          <div className="rounded border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            <p><b>{replace.tag}</b> was already weighed on this date: <b>{replace.existing} kg</b>. Replace it with <b>{replace.kg} kg</b>?</p>
            <div className="mt-2 flex gap-2">
              <Button disabled={busy} onClick={() => void submit(true, replace.tag, replace.kg)}>Replace with {replace.kg} kg</Button>
              <Button variant="ghost" disabled={busy} onClick={() => { setReplace(null); weightRef.current?.focus(); }}>Keep {replace.existing} kg</Button>
            </div>
          </div>
        )}
        {saved && (
          <div role="status" className="rounded border border-forest/30 bg-forest/5 px-4 py-3 text-sm text-forest">
            <b>{saved.tag}</b> · {saved.kg} kg {saved.offline ? "kept on this device" : "saved"}
            {saved.note && <p className={`mt-0.5 text-xs ${saved.offline ? "text-forest" : "text-amber-800"}`}>{saved.note}</p>}
          </div>
        )}
        <Button className="w-full py-3 text-base" disabled={busy || !tag.trim() || !weight.trim()} onClick={() => void submit()}>
          {busy ? "Saving…" : online ? "Save weight" : "Save on this device"}
        </Button>
      </div>
      {recent.length > 0 && (
        <div className="border-t border-hairline pt-3">
          <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted">Recorded in this visit</p>
          <ul className="divide-y divide-hairline/60 text-sm">
            {recent.map((r, i) => <li key={`${r.tag}-${i}`} className="flex justify-between py-1.5"><span className="font-mono">{r.tag}</span><span>{r.kg} kg{r.offline ? " · waiting to send" : ""}</span></li>)}
          </ul>
        </div>
      )}
    </div>
  );
}

/** The weigh form for this person: the full one (several animals at once) when their role has "Weigh form: several
 * animals at once", otherwise one animal at a time. The farm owner sets this per role under Team > Roles. */
export function WeighDayForm({ layout = "split", title = "Record a weigh day" }: { layout?: "split" | "stacked"; title?: string | null }) {
  const me = useMe();
  const can = useCan();
  if (!me.data) return <p className="text-sm text-muted">Loading…</p>;
  if (!can("weighform.multi")) return <SingleWeighForm title={title === "Record a weigh day" ? "Record a weight" : title} />;
  return <MultiWeighForm layout={layout} title={title} />;
}

/** A slim reminder for pages other than the weigh form: weights saved on this device are waiting to be sent.
 * It also sends them as soon as the page is open and there is a connection. */
export function WeighQueueNotice() {
  const { queue, online, notice, sync } = useWeighQueue();
  const pending = queue.filter((q) => q.status === "pending").length;
  const failed = queue.filter((q) => q.status === "failed").length;
  if (queue.length === 0 && !notice) return null;
  if (queue.length === 0) return <div className="mb-4 rounded border border-forest/30 bg-forest/5 px-4 py-2 text-sm text-forest">{notice}</div>;
  return (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded border border-amber-300 bg-amber-50 px-4 py-2 text-sm text-amber-900">
      <span>
        {pending > 0 && `${pending} saved weigh day(s) waiting to be sent. `}
        {failed > 0 && `${failed} were rejected: open Record weights to try again or discard them.`}
      </span>
      {pending > 0 && <Button variant="ghost" disabled={!online} onClick={() => void sync()}>Send now</Button>}
    </div>
  );
}
