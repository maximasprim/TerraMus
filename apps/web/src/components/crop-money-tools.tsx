"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button, ErrorState } from "@/components/ui";
import { apiFetch, apiUpload, ApiError } from "@/lib/api";

const kes = (v: number) => `KES ${Math.round(v).toLocaleString()}`;
const errMsg = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback);

interface ImportResult {
  ok: boolean; dry_run: boolean; kind: string; rows: number; created: number; already_imported: number; posted_to_finance: number;
  errors: { row: number; error: string }[]; warnings: { row: number; warning: string }[];
}
interface SyncResult {
  dry_run: boolean; needs_confirmation: boolean;
  sales: { missing: number; missing_amount: number; posted: number; already_recorded: number; no_price: number };
  costs: { missing: number; missing_amount: number; posted: number; already_recorded: number };
  plantings: { missing: number; missing_amount: number; posted: number; already_recorded: number };
  overlap: { manual_sales: { count: number; total: number }; manual_costs: { count: number; total: number } };
  sample: { kind: string; ref: string; date: string; amount: number }[];
}

export function CropMoneyTools() {
  return (
    <div className="space-y-6">
      <ImportSection />
      <div className="border-t border-hairline pt-4"><FinanceSync /></div>
    </div>
  );
}

function ImportSection() {
  const queryClient = useQueryClient();
  const [kind, setKind] = useState<"sales" | "costs">("sales");
  const [file, setFile] = useState<File | null>(null);
  const [post, setPost] = useState(true);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const run = useMutation({
    mutationFn: async (dry: boolean) => {
      const fd = new FormData();
      fd.append("file", file as File);
      return apiUpload<ImportResult>(`/api/v1/crops/${kind}/import?dry_run=${dry}&post_to_finance=${post}`, fd);
    },
    onSuccess: (d) => { setResult(d); setError(null); if (!d.dry_run && d.ok) queryClient.invalidateQueries(); },
    onError: (e) => setError(errMsg(e, "Import failed")),
  });
  const reset = () => { setResult(null); setError(null); };
  return (
    <section className="space-y-3">
      <h3 className="font-display text-base text-forest">Import sales or costs from a spreadsheet</h3>
      <p className="text-xs text-muted">
        For produce sold outside the web shop and costs recorded elsewhere. An .xlsx or .csv with a header row. Re-importing the same file
        never doubles anything: rows already imported are skipped.
      </p>
      <div className="flex gap-4 text-sm">
        <label className="flex items-center gap-1.5"><input type="radio" checked={kind === "sales"} onChange={() => { setKind("sales"); reset(); }} />Sales</label>
        <label className="flex items-center gap-1.5"><input type="radio" checked={kind === "costs"} onChange={() => { setKind("costs"); reset(); }} />Costs</label>
      </div>
      <p className="rounded-md bg-black/5 p-2 text-xs text-muted">
        {kind === "sales"
          ? "Columns: planting_number, date, quantity, unit (optional), unit_price or amount, buyer (optional), notes (optional)."
          : "Columns: planting_number, date, category (seed, fertilizer, chemicals, labour, fuel, transport, …), amount, notes (optional)."}
        {" "}Use the planting number exactly as shown in the Crops list.
      </p>
      <input type="file" accept=".xlsx,.xlsm,.csv" className="block w-full text-sm" onChange={(e) => { setFile(e.target.files?.[0] ?? null); reset(); }} />
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" className="mt-1" checked={post} onChange={(e) => { setPost(e.target.checked); reset(); }} />
        <span>Also record in Finance, dated on the day each {kind === "sales" ? "sale" : "cost"} happened. Each is recorded once only.</span>
      </label>
      {error && <ErrorState message={error} />}
      <div className="flex gap-2">
        <Button variant="ghost" disabled={!file || run.isPending} onClick={() => run.mutate(true)}>Check file (nothing saved)</Button>
        <Button disabled={!file || run.isPending || !result || !result.dry_run || !result.ok || result.created === 0} onClick={() => run.mutate(false)}>Import</Button>
      </div>
      {result && (
        <div className="space-y-2 text-sm">
          {!result.ok ? (
            <>
              <p className="font-medium text-clay">{result.errors.length} problem(s) found. Nothing was imported. Fix the file and check again.</p>
              <ul className="max-h-40 list-disc overflow-y-auto pl-5 text-xs">{result.errors.slice(0, 50).map((e, i) => <li key={i}>{e.row ? `Row ${e.row}: ` : ""}{e.error}</li>)}</ul>
            </>
          ) : result.dry_run ? (
            <p>Ready: <b>{result.created}</b> new row(s) to import{result.already_imported > 0 && <>, <b>{result.already_imported}</b> already imported (skipped)</>}
              {post && result.created > 0 && <>, <b>{result.posted_to_finance}</b> to be recorded in Finance</>}.</p>
          ) : (
            <p className="font-medium text-forest">Imported {result.created} row(s){result.already_imported > 0 && <>, skipped {result.already_imported} already imported</>}
              {post && <>; {result.posted_to_finance} recorded in Finance</>}.</p>
          )}
          {result.warnings.length > 0 && (
            <ul className="list-disc pl-5 text-xs text-amber-800">{result.warnings.map((w, i) => <li key={i}>{w.warning}</li>)}</ul>
          )}
        </div>
      )}
    </section>
  );
}

function FinanceSync() {
  const queryClient = useQueryClient();
  const [result, setResult] = useState<SyncResult | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = useMutation({
    mutationFn: (dry: boolean) => apiFetch<SyncResult>(`/api/v1/crops/ledger-sync?dry_run=${dry}&confirm_overlap=${confirm}`, { method: "POST" }),
    onSuccess: (d) => { setResult(d); setError(null); if (!d.dry_run) queryClient.invalidateQueries(); },
    onError: (e) => setError(errMsg(e, "Sync failed")),
  });
  const nothing = result && result.sales.missing === 0 && result.costs.missing === 0 && result.plantings.missing === 0;
  return (
    <section className="space-y-3">
      <h3 className="font-display text-base text-forest">Sync crop sales and costs to Finance</h3>
      <p className="text-xs text-muted">
        Books crop sales, costs and planting costs that exist here but not yet in Finance. Press Check first: it shows what would be recorded and
        changes nothing. Each item is recorded once only, so this is safe to repeat.
      </p>
      {error && <ErrorState message={error} />}
      <div className="flex gap-2">
        <Button variant="ghost" disabled={run.isPending} onClick={() => run.mutate(true)}>Check (nothing saved)</Button>
        <Button disabled={run.isPending || !result || !result.dry_run || !!nothing || (result.needs_confirmation && !confirm)} onClick={() => run.mutate(false)}>Record in Finance</Button>
      </div>
      {result && (
        <div className="space-y-2 text-sm">
          {result.dry_run ? (
            nothing ? <p className="font-medium text-forest">Finance is already up to date.</p> : (
              <ul className="list-disc pl-5">
                {result.sales.missing > 0 && <li><b>{result.sales.missing}</b> sale(s), {kes(result.sales.missing_amount)}</li>}
                {result.costs.missing > 0 && <li><b>{result.costs.missing}</b> cost(s), {kes(result.costs.missing_amount)}</li>}
                {result.plantings.missing > 0 && <li><b>{result.plantings.missing}</b> planting cost(s), {kes(result.plantings.missing_amount)}</li>}
              </ul>
            )
          ) : (
            <p className="font-medium text-forest">Recorded {result.sales.posted} sale(s), {result.costs.posted} cost(s) and {result.plantings.posted} planting cost(s) in Finance.</p>
          )}
          {result.dry_run && result.needs_confirmation && (
            <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900">
              <p className="mb-2 font-medium">Finance already has crops entries typed in by hand that may be the same money:</p>
              <ul className="mb-2 list-disc pl-5">
                {result.overlap.manual_sales.count > 0 && <li>{result.overlap.manual_sales.count} crop sale(s), {kes(result.overlap.manual_sales.total)}</li>}
                {result.overlap.manual_costs.count > 0 && <li>{result.overlap.manual_costs.count} crops expense(s), {kes(result.overlap.manual_costs.total)}</li>}
              </ul>
              <p className="mb-2">Recording these as well could count the same money twice, and Finance entries cannot be deleted afterwards. Review them in Finance first.</p>
              <label className="flex items-start gap-2"><input type="checkbox" className="mt-0.5" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} /><span>I checked: those entries are different from these.</span></label>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
