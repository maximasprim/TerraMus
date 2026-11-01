"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { Button, Card, EmptyState, ErrorState, Input, StatCard } from "@/components/ui";
import { apiDownload, apiFetch, apiUpload, ApiError } from "@/lib/api";
import { BatchesTab } from "./batches-tab";
import { CostingTab } from "./costing-tab";
import { SalesTab } from "./sales-tab";
import { discard, enqueue, isNetworkError, KV, loadQueue, QueuedWeighDay, retry, Sender, syncQueue } from "./offline-queue";

interface IntakeBatch {
  id: string; batch_number: number; name: string; delivered_on: string; source: string | null; sex_class: string;
  head_purchased: number; landed_cost_per_head: number; head_registered: number; head_active: number;
}
interface PerfAnimal {
  tag: string; intake_batch: number | null; days_on_farm: number; entry_weight: number | null; latest_weight: number | null;
  overall_gain: number | null; adg: number | null; adg_band: string | null; market_ready: boolean; status: string;
  est_days_to_market: number | null; latest_weigh_date: string | null;
}
interface Performance {
  as_of: string;
  summary: {
    head: number; active: number; sold: number; culled: number; died: number; market_ready: number; avg_adg_active: number | null;
    by_adg_band: Record<string, number>; no_recent_weight: string[]; flagged: { tag: string; flags: string[] }[];
  };
  animals: PerfAnimal[];
}
interface Agg {
  head: number; revenue: number; total_cost: number; profit: number; profit_per_head: number; avg_adg: number | null;
  avg_days_on_farm: number | null; avg_presale_shrink_kg: number | null;
}
interface Profit {
  assumptions: { ration_plan: string | null; overhead_pool: string | null; overhead_rate_per_bull_day: number; overhead_method: string };
  totals: Agg & { head_realised: number; head_open: number; unrealised_projected_profit: number };
  by_sale_batch: (Agg & { sale_batch: number; effective_price_per_kg: number | null })[];
  by_intake_batch: (Agg & { intake_batch: number; head_total: number; head_active: number; head_culled: number; head_died: number; loss_rate_pct: number })[];
}
interface WeighResult {
  dry_run: boolean; recorded: number; session_id: string | null;
  results: { animal: string; status: string; flags?: string[]; existing_kg?: number; detail?: string }[];
}
interface ImportReport {
  dry_run: boolean; ok: boolean; created: Record<string, number>; updated: Record<string, number>;
  warnings: { code: string; where?: string; message: string }[]; errors: { code: string; message: string }[];
  date_corrections: { where: string; read_as: string; corrected_to: string; reason: string }[];
  reconciliation: Record<string, unknown>;
}

const kes = (n: number | null | undefined) => (n == null ? "-" : new Intl.NumberFormat("en-KE", { maximumFractionDigits: 0 }).format(n));
const BAND_STYLE: Record<string, string> = {
  poor: "bg-red-100 text-red-800", below_target: "bg-amber-100 text-amber-800", on_target: "bg-green-100 text-green-800", excellent: "bg-cyan-100 text-cyan-800",
};
const errMsg = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback);
type Tab = "overview" | "batches" | "weigh" | "sales" | "costing" | "worksheet";

export default function FeedlotPage() {
  const [tab, setTab] = useState<Tab>("overview");
  useEffect(() => {   // reopen on the tab named in the URL (#weigh), so a reload or the installed app returns to it
    const h = window.location.hash.slice(1) as Tab;
    if (["overview", "batches", "weigh", "sales", "costing", "worksheet"].includes(h)) setTab(h);
  }, []);
  const choose = (k: Tab) => { setTab(k); window.history.replaceState(null, "", `#${k}`); };
  return (
    <AdminShell>
      <div className="mb-6">
        <h1 className="font-display text-2xl text-forest">Feedlot</h1>
        <p className="text-sm text-muted">Intake batches, weigh days, growth performance, profitability and the Bulls WG worksheet.</p>
      </div>
      <div className="mb-6 flex flex-wrap gap-2 border-b border-hairline">
        {([["overview", "Overview"], ["batches", "Batches"], ["weigh", "Weigh day"], ["sales", "Sales & exits"], ["costing", "Costing"], ["worksheet", "Worksheet import / export"]] as [Tab, string][]).map(([k, label]) => (
          <button key={k} onClick={() => choose(k)}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium ${tab === k ? "border-forest text-forest" : "border-transparent text-muted hover:text-ink"}`}>
            {label}
          </button>
        ))}
      </div>
      {tab === "overview" && <Overview />}
      {tab === "batches" && <BatchesTab />}
      {tab === "weigh" && <WeighDay />}
      {tab === "sales" && <SalesTab />}
      {tab === "costing" && <CostingTab />}
      {tab === "worksheet" && <Worksheet />}
    </AdminShell>
  );
}

function Overview() {
  const perf = useQuery<Performance>({ queryKey: ["feedlot", "performance"], queryFn: () => apiFetch<Performance>("/api/v1/feedlot/performance") });
  const profit = useQuery<Profit>({ queryKey: ["feedlot", "profit"], queryFn: () => apiFetch<Profit>("/api/v1/feedlot/profitability") });
  const batches = useQuery<IntakeBatch[]>({ queryKey: ["feedlot", "batches"], queryFn: () => apiFetch<IntakeBatch[]>("/api/v1/feedlot/intake-batches") });
  const err = perf.error ?? profit.error ?? batches.error;
  if (err) return <ErrorState message={errMsg(err, "Failed to load feedlot data")} />;
  if (perf.isLoading || batches.isLoading) return <p className="text-sm text-muted">Loading…</p>;
  const s = perf.data?.summary;
  if (!s || s.head === 0) {
    return <EmptyState title="No feedlot animals yet" body="Create an intake batch via the API, or import your Bulls WG worksheet from the Worksheet tab." />;
  }
  const t = profit.data?.totals;
  const ready = (perf.data?.animals ?? []).filter((a) => a.status === "active" && a.market_ready);
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard label="On farm" value={String(s.active)} hint={`${s.head} ever received`} />
        <StatCard label="Market-ready" value={String(s.market_ready)} hint="at or above target weight" />
        <StatCard label="Avg ADG (kg/day)" value={s.avg_adg_active == null ? "-" : s.avg_adg_active.toFixed(2)} hint="active animals" />
        <StatCard label="Sold / lost" value={`${s.sold} / ${s.culled + s.died}`} hint="sold / culled + died" />
      </div>
      {t && (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <StatCard label="Revenue (KES)" value={kes(t.revenue)} />
          <StatCard label="Total cost (KES)" value={kes(t.total_cost)} />
          <StatCard label="Realised profit (KES)" value={kes(t.profit)} hint={`${t.head_realised} animals`} />
          <StatCard label="Unrealised, projected (KES)" value={kes(t.unrealised_projected_profit)} hint={`${t.head_open} still on farm`} />
        </div>
      )}
      {s.no_recent_weight.length > 0 && (
        <Card><p className="text-sm text-clay">{s.no_recent_weight.length} active animal(s) have not been weighed in over 45 days: <span className="font-mono">{s.no_recent_weight.slice(0, 12).join(", ")}{s.no_recent_weight.length > 12 ? "…" : ""}</span></p></Card>
      )}
      <Card>
        <h2 className="mb-3 font-display text-lg text-forest">Intake batches</h2>
        <div className="overflow-x-auto"><table className="w-full text-sm">
          <thead><tr className="border-b border-hairline text-left text-xs uppercase text-muted">
            <th className="py-2">Batch</th><th>Delivered</th><th>Source</th><th className="text-right">Purchased</th><th className="text-right">On farm</th><th className="text-right">Landed / head</th></tr></thead>
          <tbody>{(batches.data ?? []).map((b) => (
            <tr key={b.id} className="border-b border-hairline/60">
              <td className="py-2 font-medium">{b.name}</td><td>{b.delivered_on}</td><td>{b.source ?? "-"} ({b.sex_class})</td>
              <td className="text-right">{b.head_purchased}</td><td className="text-right">{b.head_active} / {b.head_registered}</td><td className="text-right">{kes(b.landed_cost_per_head)}</td>
            </tr>))}</tbody>
        </table></div>
      </Card>
      {profit.data && profit.data.by_sale_batch.length > 0 && (
        <Card>
          <h2 className="mb-1 font-display text-lg text-forest">Sale batches</h2>
          <p className="mb-3 text-xs text-muted">Overhead is allocated per bull-day ({kes(profit.data.assumptions.overhead_rate_per_bull_day)} KES/day), so longer-held animals carry more.</p>
          <div className="overflow-x-auto"><table className="w-full text-sm">
            <thead><tr className="border-b border-hairline text-left text-xs uppercase text-muted">
              <th className="py-2">Sale</th><th className="text-right">Head</th><th className="text-right">Price/kg</th><th className="text-right">Avg days</th><th className="text-right">Avg ADG</th>
              <th className="text-right">Shrink (kg)</th><th className="text-right">Revenue</th><th className="text-right">Cost</th><th className="text-right">Profit</th></tr></thead>
            <tbody>{profit.data.by_sale_batch.map((b) => (
              <tr key={b.sale_batch} className="border-b border-hairline/60">
                <td className="py-2 font-medium">Sale {b.sale_batch}</td><td className="text-right">{b.head}</td><td className="text-right">{b.effective_price_per_kg ?? "-"}</td>
                <td className="text-right">{b.avg_days_on_farm ?? "-"}</td><td className="text-right">{b.avg_adg?.toFixed(2) ?? "-"}</td><td className="text-right">{b.avg_presale_shrink_kg ?? "-"}</td>
                <td className="text-right">{kes(b.revenue)}</td><td className="text-right">{kes(b.total_cost)}</td>
                <td className={`text-right font-medium ${b.profit < 0 ? "text-clay" : "text-forest"}`}>{kes(b.profit)}</td>
              </tr>))}</tbody>
          </table></div>
        </Card>
      )}
      <Card>
        <h2 className="mb-3 font-display text-lg text-forest">Action list <span className="text-sm font-normal text-muted">({ready.length} market-ready)</span></h2>
        <div className="overflow-x-auto"><table className="w-full text-sm">
          <thead><tr className="border-b border-hairline text-left text-xs uppercase text-muted">
            <th className="py-2">Tag</th><th>Batch</th><th className="text-right">Weight</th><th className="text-right">Days</th><th className="text-right">ADG</th><th>Band</th><th className="text-right">Est. days to market</th></tr></thead>
          <tbody>{(perf.data?.animals ?? []).filter((a) => a.status === "active")
            .sort((a, b) => Number(b.market_ready) - Number(a.market_ready) || (a.adg ?? 9) - (b.adg ?? 9)).slice(0, 40).map((a) => (
            <tr key={a.tag} className="border-b border-hairline/60">
              <td className="py-1.5 font-mono">{a.tag}{a.market_ready && <span className="ml-2 rounded bg-green-100 px-1.5 text-xs text-green-800">READY</span>}</td>
              <td>{a.intake_batch ?? "-"}</td><td className="text-right">{a.latest_weight ?? "-"}</td><td className="text-right">{a.days_on_farm}</td>
              <td className="text-right">{a.adg?.toFixed(2) ?? "-"}</td>
              <td>{a.adg_band && <span className={`rounded px-1.5 text-xs ${BAND_STYLE[a.adg_band] ?? ""}`}>{a.adg_band.replace("_", " ")}</span>}</td>
              <td className="text-right">{a.est_days_to_market ?? "-"}</td>
            </tr>))}</tbody>
        </table></div>
      </Card>
    </div>
  );
}

function parseWeights(text: string): { entries: { animal_number: string; weight_kg: number }[]; bad: string[] } {
  const entries: { animal_number: string; weight_kg: number }[] = [];
  const bad: string[] = [];
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    const parts = line.split(/[\s,;\t]+/).filter(Boolean);
    const w = Number(parts[parts.length - 1]);
    if (parts.length < 2 || !Number.isFinite(w) || w <= 0) bad.push(line);
    else entries.push({ animal_number: parts[0], weight_kg: w });
  }
  return { entries, bad };
}

function getStore(): KV | null {
  try { return typeof window === "undefined" ? null : window.localStorage; } catch { return null; }   // blocked in some private modes
}

function WeighDay() {
  const queryClient = useQueryClient();
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [scale, setScale] = useState("");
  const [text, setText] = useState("");
  const [result, setResult] = useState<WeighResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [online, setOnline] = useState(true);
  const [queue, setQueue] = useState<QueuedWeighDay[]>([]);
  const syncing = useRef(false);
  const parsed = parseWeights(text);

  const refreshQueue = useCallback(() => { const s = getStore(); setQueue(s ? loadQueue(s) : []); }, []);
  const post = (body: object) => apiFetch<WeighResult>("/api/v1/feedlot/weigh-days", { method: "POST", body: JSON.stringify(body) });

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
        queryClient.invalidateQueries({ queryKey: ["feedlot"] });
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

  const payload = { weighed_on: date, scale_label: scale || undefined, entries: parsed.entries };
  const keepOnDevice = () => {
    const s = getStore();
    if (!s) { setError("This browser cannot keep data offline. Reconnect before saving."); return; }
    enqueue(s, payload);
    refreshQueue(); setText(""); setResult(null); setError(null);
    setNotice(`Saved on this device (${payload.entries.length} animals). It will be sent automatically when you are back online.`);
  };

  const preview = async () => {
    setBusy(true); setError(null); setNotice(null);
    try { setResult(await post({ ...payload, dry_run: true })); }
    catch (e) { setError(isNetworkError(e) ? "Preview needs a connection. You can still save: the weights are kept on this device and sent later." : errMsg(e, "Could not preview")); }
    finally { setBusy(false); }
  };
  const save = async () => {
    setNotice(null);
    if (typeof navigator !== "undefined" && !navigator.onLine) { keepOnDevice(); return; }
    setBusy(true); setError(null);
    try {
      const d = await post({ ...payload, dry_run: false });
      setResult(d); queryClient.invalidateQueries({ queryKey: ["feedlot"] });
    } catch (e) {
      if (isNetworkError(e)) keepOnDevice(); else setError(errMsg(e, "Could not record weights"));
    } finally { setBusy(false); }
  };

  const pending = queue.filter((q) => q.status === "pending").length;
  return (
    <div className="space-y-6">
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
      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="space-y-3">
          <h2 className="font-display text-lg text-forest">Record a weigh day</h2>
          <div className="grid grid-cols-2 gap-3">
            <Input label="Weigh date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
            <Input label="Scale (optional)" value={scale} onChange={(e) => setScale(e.target.value)} placeholder="e.g. Crush pen scale" />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-ink" htmlFor="wl">One animal per line: tag, then weight in kg</label>
            <textarea id="wl" rows={12} value={text} onChange={(e) => { setText(e.target.value); setResult(null); }}
              placeholder={"A01 349\nA02 331.5\nA03, 342"} className="w-full rounded-md border border-hairline bg-white px-3 py-2 font-mono text-sm focus:border-brass focus:outline-none" />
          </div>
          <p className="text-xs text-muted">{parsed.entries.length} animal(s) ready{parsed.bad.length > 0 && <span className="text-clay"> · {parsed.bad.length} line(s) not understood: {parsed.bad.slice(0, 3).join(" | ")}</span>}</p>
          {error && <ErrorState message={error} />}
          <div className="flex gap-2">
            <Button variant="ghost" disabled={!parsed.entries.length || busy || !online} onClick={() => void preview()}>Preview (nothing saved)</Button>
            <Button disabled={!parsed.entries.length || busy || parsed.bad.length > 0} onClick={() => void save()}>{online ? "Save weights" : "Save on this device"}</Button>
          </div>
        </Card>
        <Card>
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
        </Card>
      </div>
    </div>
  );
}

function Worksheet() {
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [report, setReport] = useState<ImportReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [asOf, setAsOf] = useState("");
  const [exporting, setExporting] = useState(false);
  const [postToFinance, setPostToFinance] = useState(true);
  const run = useMutation({
    mutationFn: (dry: boolean) => {
      if (!file) throw new Error("Choose the .xlsx worksheet first");
      const fd = new FormData();
      fd.append("file", file);
      return apiUpload<ImportReport>(`/api/v1/feedlot/worksheet/import?dry_run=${dry}&post_to_finance=${postToFinance}`, fd);
    },
    onSuccess: (d) => { setReport(d); setError(null); if (!d.dry_run && d.ok) queryClient.invalidateQueries({ queryKey: ["feedlot"] }); },
    onError: (e) => setError(e instanceof Error ? e.message : "Import failed"),
  });
  const doExport = async () => {
    setExporting(true); setError(null);
    try { await apiDownload(`/api/v1/feedlot/worksheet/export${asOf ? `?as_of=${asOf}` : ""}`, `Bulls_WG_Worksheet${asOf ? `_${asOf}` : ""}.xlsx`); }
    catch (e) { setError(errMsg(e, "Export failed")); }
    finally { setExporting(false); }
  };
  const created = report ? Object.entries(report.created).filter(([, v]) => v > 0) : [];
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card className="space-y-3">
        <h2 className="font-display text-lg text-forest">Import your worksheet</h2>
        <p className="text-sm text-muted">Reads the BATCH, Sales weight, register and costing sheets. Always preview first: nothing is saved until you press Import. Re-importing the same file changes nothing; a newer copy adds only what is new.</p>
        <input type="file" accept=".xlsx,.xlsm" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setReport(null); }} className="block w-full text-sm" />
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" className="mt-1" checked={postToFinance} onChange={(e) => { setPostToFinance(e.target.checked); setReport(null); }} />
          <span>Also record the <b>new</b> sales and purchases in Finance, dated on the day they happened. Each is recorded once only, so re-importing never doubles anything.</span>
        </label>
        {error && <ErrorState message={error} />}
        <div className="flex gap-2">
          <Button variant="ghost" disabled={!file || run.isPending} onClick={() => run.mutate(true)}>Preview</Button>
          <Button disabled={!file || run.isPending || !report || !report.dry_run || !report.ok} onClick={() => run.mutate(false)}>Import</Button>
        </div>
        {report && (
          <div className="space-y-3 border-t border-hairline pt-3 text-sm">
            <p className={report.ok ? "font-medium text-forest" : "font-medium text-clay"}>
              {report.ok ? (report.dry_run ? "Preview OK, nothing saved yet" : "Imported") : "Cannot import"}
            </p>
            {report.errors.map((e) => <ErrorState key={e.code} message={e.message} />)}
            {created.length > 0 && <p>{report.dry_run ? "Would create: " : "Created: "}{created.map(([k, v]) => `${v} ${k.replace(/_/g, " ")}`).join(", ")}</p>}
            {report.date_corrections.length > 0 && (
              <details><summary className="cursor-pointer text-amber-700">{report.date_corrections.length} date(s) corrected (day/month were swapped)</summary>
                <ul className="mt-1 list-disc pl-5 text-xs">{report.date_corrections.map((c) => <li key={c.where}>{c.where}: {c.read_as} → <b>{c.corrected_to}</b></li>)}</ul></details>
            )}
            {report.warnings.length > 0 && (
              <details open><summary className="cursor-pointer text-amber-700">{report.warnings.length} item(s) to review</summary>
                <ul className="mt-1 list-disc space-y-1 pl-5 text-xs">{report.warnings.map((w, i) => <li key={i}>{w.message}</li>)}</ul></details>
            )}
          </div>
        )}
      </Card>
      <Card className="space-y-3">
        <h2 className="font-display text-lg text-forest">Export the worksheet</h2>
        <p className="text-sm text-muted">Downloads the workbook in your exact layout (same sheets, columns, headers and colours) with live formulas, plus analytics sheets added after your originals.</p>
        <Input label="Report as at (optional)" type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} />
        <Button disabled={exporting} onClick={doExport}>{exporting ? "Preparing…" : "Download worksheet (.xlsx)"}</Button>
      </Card>
      <FinanceSync />
    </div>
  );
}

interface LedgerSyncResult {
  dry_run: boolean; needs_confirmation: boolean;
  sales: { missing: number; missing_amount: number; posted: number; already_recorded: number; no_price: number };
  purchases: { missing: number; missing_amount: number; posted: number; already_recorded: number; no_cost: number };
  overlap: { manual_sales: { count: number; total: number }; manual_purchases: { count: number; total: number } };
  sample: { kind: string; animal: string; date: string; amount: number }[];
}

function FinanceSync() {
  const queryClient = useQueryClient();
  const [result, setResult] = useState<LedgerSyncResult | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = useMutation({
    mutationFn: (dry: boolean) => apiFetch<LedgerSyncResult>(`/api/v1/feedlot/ledger-sync?dry_run=${dry}&confirm_overlap=${confirm}`, { method: "POST" }),
    onSuccess: (d) => { setResult(d); setError(null); if (!d.dry_run) queryClient.invalidateQueries(); },
    onError: (e) => setError(errMsg(e, "Sync failed")),
  });
  const nothingToDo = result && result.sales.missing === 0 && result.purchases.missing === 0;
  return (
    <Card className="space-y-3 lg:col-span-2">
      <h2 className="font-display text-lg text-forest">Sync feedlot sales and purchases to Finance</h2>
      <p className="text-sm text-muted">
        For sales and purchases that are in the feedlot but not yet in Finance, for example a worksheet imported earlier. Press Check first:
        it shows what would be recorded and changes nothing. Each sale and purchase is recorded once only, so this is safe to repeat.
      </p>
      {error && <ErrorState message={error} />}
      <div className="flex gap-2">
        <Button variant="ghost" disabled={run.isPending} onClick={() => run.mutate(true)}>Check (nothing saved)</Button>
        <Button disabled={run.isPending || !result || !result.dry_run || !!nothingToDo || (result.needs_confirmation && !confirm)} onClick={() => run.mutate(false)}>Record in Finance</Button>
      </div>
      {result && (
        <div className="space-y-2 border-t border-hairline pt-3 text-sm">
          {result.dry_run ? (
            nothingToDo ? <p className="font-medium text-forest">Finance is already up to date. Nothing to record.</p> : (
              <p>
                Would record <b>{result.sales.missing}</b> sale(s) totalling <b>KES {kes(result.sales.missing_amount)}</b>
                {result.purchases.missing > 0 && <> and <b>{result.purchases.missing}</b> purchase(s) totalling <b>KES {kes(result.purchases.missing_amount)}</b></>}.
              </p>
            )
          ) : (
            <p className="font-medium text-forest">Recorded {result.sales.posted} sale(s) and {result.purchases.posted} purchase(s) in Finance.</p>
          )}
          {result.sales.no_price > 0 && <p className="text-xs text-amber-700">{result.sales.no_price} sale(s) have no price per kg and are skipped. Set the sale batch price, then check again.</p>}
          {result.dry_run && result.needs_confirmation && (
            <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900">
              <p className="mb-2 font-medium">Finance already has entries typed in by hand that may be the same bulls:</p>
              <ul className="mb-2 list-disc pl-5">
                {result.overlap.manual_sales.count > 0 && <li>{result.overlap.manual_sales.count} livestock sale(s), KES {kes(result.overlap.manual_sales.total)}</li>}
                {result.overlap.manual_purchases.count > 0 && <li>{result.overlap.manual_purchases.count} livestock purchase(s), KES {kes(result.overlap.manual_purchases.total)}</li>}
              </ul>
              <p className="mb-2">Recording these as well could count the same money twice, and Finance entries cannot be deleted afterwards. Review them in Finance first.</p>
              <label className="flex items-start gap-2"><input type="checkbox" className="mt-0.5" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} /><span>I checked: those entries are different from these bulls.</span></label>
            </div>
          )}
          {result.dry_run && result.sample.length > 0 && (
            <details><summary className="cursor-pointer text-muted">Preview of the first {result.sample.length}</summary>
              <table className="mt-1 w-full text-xs"><tbody>
                {result.sample.map((r, i) => <tr key={i} className="border-b border-hairline/60"><td className="py-1 font-mono">{r.animal}</td><td>{r.kind}</td><td>{r.date}</td><td className="text-right">KES {kes(r.amount)}</td></tr>)}
              </tbody></table></details>
          )}
        </div>
      )}
    </Card>
  );
}
