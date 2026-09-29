"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { TagChip, StatusBadge, ErrorState, EmptyState, Button, Modal, Select } from "@/components/ui";
import { apiFetch, apiUpload, ApiError } from "@/lib/api";
import type { CropPlanting, Farm, BulkImportResult } from "@/lib/types";

export default function CropsListPage() {
  const [importOpen, setImportOpen] = useState(false);
  const { data, isLoading, error } = useQuery<CropPlanting[]>({
    queryKey: ["crops"],
    queryFn: () => apiFetch<CropPlanting[]>("/api/v1/crops?page_size=100"),
  });

  return (
    <AdminShell>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl text-forest">Crops</h1>
          <p className="text-sm text-muted">Every plot/batch of a crop currently on record.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" onClick={() => setImportOpen(true)}>Import CSV</Button>
          <Link href="/admin/crops/new">
            <Button>+ Register planting</Button>
          </Link>
        </div>
      </div>

      {error && <ErrorState message={error instanceof ApiError ? error.message : "Failed to load crops"} />}
      {isLoading && <p className="text-sm text-muted">Loading…</p>}
      {data && data.length === 0 && (
        <EmptyState
          title="No crop plantings yet"
          body="Plantings you register - fodder, tea, avocado, maize and more - will show up here."
        />
      )}

      {data && data.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-hairline">
          <table className="w-full text-left text-sm">
            <thead className="bg-forest text-paper">
              <tr>
                <th className="px-4 py-3 font-medium">Number</th>
                <th className="px-4 py-3 font-medium">Crop / Variety</th>
                <th className="px-4 py-3 font-medium">Planted</th>
                <th className="px-4 py-3 font-medium">Area</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Health</th>
              </tr>
            </thead>
            <tbody>
              {data.map((planting, i) => (
                <tr key={planting.id} className={i % 2 === 0 ? "bg-white/40" : "bg-white/70"}>
                  <td className="px-4 py-3">
                    <Link href={`/admin/crops/${planting.id}`} className="hover:underline">
                      <TagChip>{planting.planting_number}</TagChip>
                    </Link>
                  </td>
                  <td className="px-4 py-3 capitalize">
                    {planting.crop_type.replace(/_/g, " ")}
                    {planting.variety ? ` · ${planting.variety}` : ""}
                    {planting.is_perennial && <span className="ml-1 text-xs text-muted">(bearing)</span>}
                  </td>
                  <td className="px-4 py-3">{new Date(planting.planting_date).toLocaleDateString()}</td>
                  <td className="px-4 py-3">
                    {planting.area_size ? `${planting.area_size} ${planting.area_unit}` : "-"}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={planting.status} />
                  </td>
                  <td className="px-4 py-3 capitalize text-muted">{planting.health_status.replace(/_/g, " ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <CropsImportModal open={importOpen} onClose={() => setImportOpen(false)} />
    </AdminShell>
  );
}

function CropsImportModal({ open, onClose }: { open: boolean; onClose: () => void }) {
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
      return apiUpload<BulkImportResult>(`/api/v1/bulk-import/crops?${params.toString()}`, formData);
    },
    onSuccess: (data, dryRun) => {
      setResult(data);
      setError(null);
      if (!dryRun) queryClient.invalidateQueries({ queryKey: ["crops"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Import failed"),
  });

  const reset = () => { setFarmId(""); setFile(null); setResult(null); setError(null); };

  return (
    <Modal open={open} onClose={() => { reset(); onClose(); }} title="Bulk import crop plantings from CSV">
      <div className="space-y-3">
        {error && <ErrorState message={error} />}
        <Select label="Farm" required value={farmId} onChange={(e) => { setFarmId(e.target.value); setResult(null); }}>
          <option value="">Every planting in this file goes into…</option>
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
        <p className="text-xs text-muted">
          Columns: planting_number, crop_type, planting_date (required); variety, is_perennial, area_size,
          area_unit, planting_method, expected_harvest_date, acquisition_cost, source, supplier, notes (optional).
          location_id can be included per row to override the default location.
        </p>

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
