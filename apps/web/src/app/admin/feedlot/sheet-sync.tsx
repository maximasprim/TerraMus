"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, ErrorState, Input } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import { useCycle } from "@/lib/cycle-context";

interface SyncConfig {
  sheet_url: string; enabled: boolean; production_cycle_id: string | null; post_to_finance: boolean; include_costing: boolean;
  last_run_at: string | null; last_status: "ok" | "unchanged" | "failed" | null; last_message: string | null;
  last_report: { created: Record<string, number>; updated: Record<string, number>; unchanged: Record<string, number>; warnings: number; errors: string[] } | null;
  configured: boolean;
}
interface RunResult { status: "ok" | "unchanged" | "failed"; message: string; dry_run: boolean }

const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "never");
const errMsg = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback);

/** Imports the farm's Google Sheet automatically every day (the same importer as the manual upload). */
export function SheetSync() {
  const qc = useQueryClient();
  const { cycles } = useCycle();
  const q = useQuery<SyncConfig>({ queryKey: ["feedlot", "worksheet-sync"], queryFn: () => apiFetch<SyncConfig>("/api/v1/feedlot/worksheet/sync") });
  const [form, setForm] = useState<Partial<Pick<SyncConfig, "sheet_url" | "enabled" | "production_cycle_id" | "post_to_finance">>>({});
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const openCycles = cycles.filter((c) => c.status !== "closed");
  const cfg = q.data;
  const v = {
    sheet_url: form.sheet_url ?? cfg?.sheet_url ?? "", enabled: form.enabled ?? cfg?.enabled ?? false,
    production_cycle_id: form.production_cycle_id !== undefined ? form.production_cycle_id : cfg?.production_cycle_id ?? null,
    post_to_finance: form.post_to_finance ?? cfg?.post_to_finance ?? true,
  };
  const save = useMutation({
    mutationFn: () => apiFetch<SyncConfig>("/api/v1/feedlot/worksheet/sync", { method: "PUT", body: JSON.stringify({ ...v, include_costing: cfg?.include_costing ?? true }) }),
    onSuccess: () => { setForm({}); setErr(null); setMsg({ ok: true, text: "Saved." }); void qc.invalidateQueries({ queryKey: ["feedlot", "worksheet-sync"] }); },
    onError: (e) => { setMsg(null); setErr(errMsg(e, "Could not save")); },
  });
  const run = useMutation({
    mutationFn: (mode: "preview" | "now") => apiFetch<RunResult>(`/api/v1/feedlot/worksheet/sync/run?${mode === "preview" ? "dry_run=true" : "force=true"}`, { method: "POST" }),
    onSuccess: (r, mode) => {
      setErr(null); setMsg({ ok: r.status !== "failed", text: (mode === "preview" ? "Preview: " : "") + r.message });
      void qc.invalidateQueries({ queryKey: ["feedlot"] }); void qc.invalidateQueries({ queryKey: ["weights"] });
    },
    onError: (e) => { setMsg(null); setErr(errMsg(e, "Could not run the import")); },
  });
  const dirty = Object.keys(form).length > 0;
  const busy = save.isPending || run.isPending;
  return (
    <Card className="space-y-3">
      <h2 className="font-display text-lg text-forest">Import from Google Sheets automatically</h2>
      <p className="text-sm text-muted">The system reads your Google Sheet every morning and imports it, so you do not have to upload the file. It only adds or updates what changed, and records new sales and purchases in Finance once each.</p>
      <ol className="list-decimal space-y-0.5 pl-5 text-xs text-muted">
        <li>In Google Sheets choose <b>Share</b> → General access → <b>Anyone with the link</b> (Viewer).</li>
        <li>Paste the sheet&rsquo;s address below, pick its production cycle and switch it on.</li>
        <li>Press <b>Preview</b> to check what would change, then <b>Import now</b>.</li>
      </ol>
      <Input label="Google Sheet link" placeholder="https://docs.google.com/spreadsheets/d/…/edit" value={v.sheet_url} onChange={(e) => setForm({ ...form, sheet_url: e.target.value })} />
      <div>
        <label className="block text-sm font-medium" htmlFor="sync-cycle">Production cycle</label>
        <select id="sync-cycle" value={v.production_cycle_id ?? ""} onChange={(e) => setForm({ ...form, production_cycle_id: e.target.value || null })}
          className="mt-1 w-full rounded-md border border-hairline bg-white px-3 py-2 text-sm">
          <option value="">{openCycles.length ? "Choose a cycle…" : "No cycles yet"}</option>
          {openCycles.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <p className="mt-1 text-xs text-muted">Batch numbers restart in every cycle, so the sheet must belong to one.</p>
      </div>
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" className="mt-1" checked={v.post_to_finance} onChange={(e) => setForm({ ...form, post_to_finance: e.target.checked })} />
        <span>Also record new sales and purchases in Finance.</span>
      </label>
      <label className="flex items-start gap-2 text-sm font-medium">
        <input type="checkbox" className="mt-1" checked={v.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} />
        <span>Import automatically every day</span>
      </label>
      {err && <ErrorState message={err} />}
      {msg && <p className={`text-sm ${msg.ok ? "text-forest" : "text-clay"}`}>{msg.text}</p>}
      <div className="flex flex-wrap gap-2">
        <Button disabled={busy || !dirty} onClick={() => save.mutate()}>Save</Button>
        <Button variant="ghost" disabled={busy || dirty || !cfg?.sheet_url} onClick={() => run.mutate("preview")}>Preview</Button>
        <Button variant="ghost" disabled={busy || dirty || !cfg?.sheet_url} onClick={() => run.mutate("now")}>Import now</Button>
      </div>
      {dirty && <p className="text-xs text-muted">Save your changes before previewing or importing.</p>}
      {cfg?.last_run_at && (
        <div className="border-t border-hairline pt-3 text-sm">
          <p>Last run: <b>{when(cfg.last_run_at)}</b> · <span className={cfg.last_status === "failed" ? "text-clay" : "text-forest"}>{cfg.last_status === "ok" ? "imported" : cfg.last_status === "unchanged" ? "no changes" : "failed"}</span></p>
          {cfg.last_message && <p className="text-xs text-muted">{cfg.last_message}</p>}
        </div>
      )}
    </Card>
  );
}
