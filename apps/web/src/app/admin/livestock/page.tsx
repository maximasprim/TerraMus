"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { TagChip, StatusBadge, ErrorState, EmptyState, Button, Modal, Select } from "@/components/ui";
import { apiFetch, apiUpload, ApiError } from "@/lib/api";
import type { Animal, Farm, BulkImportResult } from "@/lib/types";

export default function LivestockListPage() {
  const [importOpen, setImportOpen] = useState(false);
  const { data, isLoading, error } = useQuery<Animal[]>({
    queryKey: ["livestock"],
    queryFn: () => apiFetch<Animal[]>("/api/v1/livestock?page_size=100"),
  });

  return (
    <AdminShell>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl text-forest">Livestock</h1>
          <p className="text-sm text-muted">Every animal currently on record.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" onClick={() => setImportOpen(true)}>Import CSV</Button>
          <Link href="/admin/livestock/new">
            <Button>+ Register animal</Button>
          </Link>
        </div>
      </div>

      {error && <ErrorState message={error instanceof ApiError ? error.message : "Failed to load livestock"} />}
      {isLoading && <p className="text-sm text-muted">Loading…</p>}
      {data && data.length === 0 && (
        <EmptyState title="No animals yet" body="Animals you register will show up here." />
      )}

      {data && data.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-hairline">
          <table className="w-full text-left text-sm">
            <thead className="bg-forest text-paper">
              <tr>
                <th className="px-4 py-3 font-medium">ID</th>
                <th className="px-4 py-3 font-medium">Species / Breed</th>
                <th className="px-4 py-3 font-medium">Sex</th>
                <th className="px-4 py-3 font-medium">Weight</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Health</th>
              </tr>
            </thead>
            <tbody>
              {data.map((animal, i) => (
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
