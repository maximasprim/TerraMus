"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { Can } from "@/components/can";
import { TagChip, StatusBadge, ErrorState, EmptyState, Button, Modal, Select } from "@/components/ui";
import { ApiError, apiDownload, apiFetch, apiFetchAll, apiUpload } from "@/lib/api";
import { useCan } from "@/lib/use-auth";
import { useCatalog } from "@/lib/use-catalog";
import { ModuleDisabledNotice } from "@/components/module-disabled-notice";
import { WeighDayForm, WeighQueueNotice } from "@/components/weigh-day-form";
import { distinct, filterAnimals, nextSort, NO_FILTERS, sortAnimals, type Filters, type SortKey, type SortState } from "@/lib/livestock-list";
import type { Animal, Farm, BulkImportResult } from "@/lib/types";

export default function LivestockListPage() {
  const [importOpen, setImportOpen] = useState(false);
  const [weighOpen, setWeighOpen] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [sort, setSort] = useState<SortState | null>(null);   // null = the order loaded (newest first)
  const can = useCan();
  const { data: catalog } = useCatalog();
  const moduleOff = catalog?.livestock_enabled === false;
  // literal URLs (not built from a variable) so the contract audit can verify them against the backend
  const reportExport = (download: Promise<void>) =>
    download.then(() => setExportError(null)).catch((err) => setExportError(err instanceof ApiError ? err.message : "Export failed"));
  const exportCsv = () => reportExport(apiDownload("/api/v1/reports/export/livestock.csv", "livestock.csv"));
  const exportPdf = () => reportExport(apiDownload("/api/v1/reports/export/livestock.pdf", "livestock.pdf"));
  const { data, isLoading, error } = useQuery<Animal[]>({
    queryKey: ["livestock"],
    queryFn: () => apiFetchAll<Animal>("/api/v1/livestock"),
  });

  // Search, filters and sorting run in the browser on the animals already loaded.
  const visible = useMemo(() => sortAnimals(filterAnimals(data ?? [], filters), sort), [data, filters, sort]);
  const speciesOptions = useMemo(() => distinct(data ?? [], "species"), [data]);
  const statusOptions = useMemo(() => distinct(data ?? [], "status"), [data]);
  const filtering = filters.q.trim() !== "" || filters.species !== "" || filters.status !== "";
  const sortTh = (k: SortKey, label: string) => (
    <th key={k} className="px-4 py-3 font-medium" aria-sort={sort?.key === k ? (sort.dir === "asc" ? "ascending" : "descending") : "none"}>
      <button type="button" onClick={() => setSort((cur) => nextSort(cur, k))} className="inline-flex items-center gap-1 hover:underline">
        {label}
        <span aria-hidden className={sort?.key === k ? "" : "opacity-40"}>{sort?.key === k ? (sort.dir === "asc" ? "▲" : "▼") : "↕"}</span>
      </button>
    </th>
  );

  return (
    <AdminShell>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl text-forest">Livestock</h1>
          <p className="text-sm text-muted">Every animal currently on record.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {!moduleOff && <Can permission="feedlot.weigh"><Button onClick={() => setWeighOpen(true)}>Record weights</Button></Can>}
          {can("reports.view") && (
            <>
              <Button variant="ghost" onClick={exportCsv}>Export CSV</Button>
              <Button variant="ghost" onClick={exportPdf}>Export PDF</Button>
            </>
          )}
          {!moduleOff && <Can permission="livestock.create"><Button variant="ghost" onClick={() => setImportOpen(true)}>Import CSV</Button></Can>}
          {!moduleOff && <Can permission="livestock.create"><Link href="/admin/livestock/new">
            <Button>+ Register animal</Button>
          </Link></Can>}
        </div>
      </div>
      {moduleOff && <ModuleDisabledNotice module="Livestock" />}
      {!moduleOff && !weighOpen && <Can permission="feedlot.weigh"><WeighQueueNotice /></Can>}
      {exportError && <div className="mb-4"><ErrorState message={exportError} /></div>}

      {error && <ErrorState message={error instanceof ApiError ? error.message : "Failed to load livestock"} />}
      {isLoading && <p className="text-sm text-muted">Loading…</p>}
      {data && data.length === 0 && (
        <EmptyState title="No animals yet" body="Animals you register will show up here." />
      )}

      {data && data.length > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <input
            type="search" aria-label="Search animals" value={filters.q} placeholder="Search tag, ear tag, name, breed…"
            onChange={(e) => setFilters({ ...filters, q: e.target.value })}
            className="min-w-[12rem] flex-1 rounded-md border border-hairline bg-white px-3 py-2 text-sm focus:border-brass focus:outline-none"
          />
          <select aria-label="Filter by species" value={filters.species} onChange={(e) => setFilters({ ...filters, species: e.target.value })}
            className="rounded-md border border-hairline bg-white px-3 py-2 text-sm capitalize">
            <option value="">All species</option>
            {speciesOptions.map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
          <select aria-label="Filter by status" value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })}
            className="rounded-md border border-hairline bg-white px-3 py-2 text-sm capitalize">
            <option value="">All statuses</option>
            {statusOptions.map((v) => <option key={v} value={v}>{v.replace(/_/g, " ")}</option>)}
          </select>
          {(filtering || sort) && (
            <Button variant="ghost" onClick={() => { setFilters(NO_FILTERS); setSort(null); }}>Clear</Button>
          )}
          <p className="w-full text-xs text-muted sm:ml-auto sm:w-auto" aria-live="polite">
            {filtering ? `Showing ${visible.length} of ${data.length}` : `${data.length} animal${data.length === 1 ? "" : "s"}`}
          </p>
        </div>
      )}
      {data && data.length > 0 && visible.length === 0 && (
        <EmptyState title="No animals match" body="Try a different search, or clear the filters." />
      )}

      {data && visible.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-hairline">
          <table className="w-full text-left text-sm">
            <thead className="bg-forest text-paper">
              <tr>
                {sortTh("id", "ID")}
                {sortTh("species", "Species / Breed")}
                {sortTh("sex", "Sex")}
                {sortTh("weight", "Weight")}
                {sortTh("status", "Status")}
                {sortTh("health", "Health")}
              </tr>
            </thead>
            <tbody>
              {visible.map((animal, i) => (
                <tr
                  key={animal.id}
                  className={i % 2 === 0 ? "bg-white/40" : "bg-white/70"}
                >
                  <td className="px-4 py-3">
                    <Link href={`/admin/livestock/${animal.id}`} className="hover:underline">
                      <TagChip>{animal.animal_number}</TagChip>
                    </Link>
                  </td>
                  <td className="px-4 py-3 capitalize">
                    {animal.species}
                    {animal.breed ? ` · ${animal.breed}` : ""}
                  </td>
                  <td className="px-4 py-3 capitalize">{animal.sex}</td>
                  <td className="px-4 py-3">{animal.current_weight ? `${animal.current_weight} kg` : "-"}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={animal.status} />
                  </td>
                  <td className="px-4 py-3 capitalize text-muted">{animal.health_status.replace(/_/g, " ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <LivestockImportModal open={importOpen} onClose={() => setImportOpen(false)} />
      <Modal open={weighOpen} onClose={() => setWeighOpen(false)} title="Record weights" size="lg">
        <WeighDayForm layout="stacked" title={null} />
      </Modal>
    </AdminShell>
  );
}

function LivestockImportModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [farmId, setFarmId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<BulkImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const farmsQuery = useQuery<Farm[]>({
    queryKey: ["farms"],
    queryFn: () => apiFetch<Farm[]>("/api/v1/farms"),
    enabled: open,
  });

  const run = useMutation({
    mutationFn: (dryRun: boolean) => {
      if (!file || !farmId) throw new Error("Choose a farm and a CSV file first");
      const params = new URLSearchParams({ dry_run: String(dryRun), farm_id: farmId });
      const formData = new FormData();
      formData.append("file", file);
      return apiUpload<BulkImportResult>(`/api/v1/bulk-import/livestock?${params.toString()}`, formData);
    },
    onSuccess: (data, dryRun) => {
      setResult(data);
      setError(null);
      if (!dryRun) queryClient.invalidateQueries({ queryKey: ["livestock"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Import failed"),
  });

  const reset = () => { setFarmId(""); setFile(null); setResult(null); setError(null); };

  return (
    <Modal open={open} onClose={() => { reset(); onClose(); }} title="Bulk import livestock from CSV">
      <div className="space-y-3">
        {error && <ErrorState message={error} />}
        <Select label="Farm" required value={farmId} onChange={(e) => { setFarmId(e.target.value); setResult(null); }}>
          <option value="">Every animal in this file goes into…</option>
          {farmsQuery.data?.map((f) => (
            <option key={f.id} value={f.id}>{f.name}</option>
          ))}
        </Select>
        <input
          type="file"
          accept=".csv"
          onChange={(e) => { setFile(e.target.files?.[0] ?? null); setResult(null); }}
          className="w-full rounded-md border border-hairline bg-white px-3 py-2 text-sm"
        />

        {result && (
          <div className="rounded-md border border-hairline bg-paper p-3 text-sm">
            <p className="font-medium text-ink">
              {result.dry_run ? "Preview" : "Import complete"}: {result.valid_rows} of {result.total_rows} rows valid
              {!result.dry_run && `, ${result.imported} imported`}.
            </p>
            {result.errors.length > 0 && (
              <ul className="mt-2 space-y-1 text-xs text-clay">
                {result.errors.map((e, i) => <li key={i}>Row {e.row}: {e.error}</li>)}
              </ul>
            )}
          </div>
        )}

        <div className="flex gap-2">
          <Button variant="ghost" className="flex-1" disabled={!file || !farmId || run.isPending} onClick={() => run.mutate(true)}>
            {run.isPending ? "Checking…" : "Preview"}
          </Button>
          <Button className="flex-1" disabled={!file || !farmId || !result || run.isPending} onClick={() => run.mutate(false)}>
            {run.isPending ? "Importing…" : "Confirm import"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
