"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { Card, StatusBadge, ErrorState, Button, Input, Select } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import type { AssetDetail } from "@/lib/types";

const MAINTENANCE_TYPES = ["service", "repair", "inspection"] as const;

export default function AssetDetailPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [maintenanceType, setMaintenanceType] = useState<string>(MAINTENANCE_TYPES[0]);
  const [maintenanceDate, setMaintenanceDate] = useState("");
  const [description, setDescription] = useState("");
  const [cost, setCost] = useState("");
  const [error, setError] = useState<string | null>(null);

  const assetQuery = useQuery<AssetDetail>({
    queryKey: ["asset", id],
    queryFn: () => apiFetch<AssetDetail>(`/api/v1/assets/${id}`),
  });

  const addRecord = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/assets/${id}/maintenance`, {
        method: "POST",
        body: JSON.stringify({
          maintenance_type: maintenanceType, maintenance_date: maintenanceDate,
          description, cost: cost || undefined,
        }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["asset", id] });
      queryClient.invalidateQueries({ queryKey: ["assets"] });
      setMaintenanceDate("");
      setDescription("");
      setCost("");
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Failed to add maintenance record"),
  });

  if (assetQuery.error) {
    return (
      <AdminShell>
        <ErrorState message={assetQuery.error instanceof ApiError ? assetQuery.error.message : "Failed to load asset"} />
      </AdminShell>
    );
  }
  if (!assetQuery.data) {
    return (
      <AdminShell>
        <p className="text-sm text-muted">Loading…</p>
      </AdminShell>
    );
  }

  const asset = assetQuery.data;

  return (
    <AdminShell>
      <div className="mb-6 flex items-start justify-between">
        <div>
          <div className="mb-2"><StatusBadge status={asset.status} /></div>
          <h1 className="font-display text-2xl text-forest">{asset.name}</h1>
          <p className="text-sm text-muted">{asset.asset_number} · {asset.asset_type.replace(/_/g, " ")}</p>
        </div>
        <div className="text-right">
          <p className="text-xs uppercase tracking-wider text-muted">Current value</p>
          <p className="font-display text-2xl text-forest">
            {asset.current_value ? `KES ${Number(asset.current_value).toLocaleString()}` : "Unknown"}
          </p>
          <p className="text-xs text-muted">Maintenance to date: KES {Number(asset.total_maintenance_cost).toLocaleString()}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card>
          <h2 className="mb-3 font-display text-lg text-forest">Details</h2>
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between"><dt className="text-muted">Condition</dt><dd className="capitalize text-ink">{asset.condition}</dd></div>
            <div className="flex justify-between"><dt className="text-muted">Acquisition date</dt><dd className="text-ink">{asset.acquisition_date ?? "-"}</dd></div>
            <div className="flex justify-between"><dt className="text-muted">Acquisition cost</dt><dd className="text-ink">{asset.acquisition_cost ? `KES ${Number(asset.acquisition_cost).toLocaleString()}` : "-"}</dd></div>
            <div className="flex justify-between"><dt className="text-muted">Useful life</dt><dd className="text-ink">{asset.useful_life_years ? `${asset.useful_life_years} years` : "-"}</dd></div>
            <div className="flex justify-between"><dt className="text-muted">Serial number</dt><dd className="text-ink">{asset.serial_number ?? "-"}</dd></div>
          </dl>
        </Card>

        <Card>
          <h2 className="mb-3 font-display text-lg text-forest">Maintenance log</h2>
          {error && <div className="mb-2"><ErrorState message={error} /></div>}
          <form
            onSubmit={(e) => { e.preventDefault(); addRecord.mutate(); }}
            className="mb-4 space-y-2"
          >
            <div className="grid grid-cols-2 gap-2">
              <Select value={maintenanceType} onChange={(e) => setMaintenanceType(e.target.value)}>
                {MAINTENANCE_TYPES.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </Select>
              <Input type="date" required value={maintenanceDate} onChange={(e) => setMaintenanceDate(e.target.value)} />
            </div>
            <Input placeholder="Description" required value={description} onChange={(e) => setDescription(e.target.value)} />
            <Input placeholder="Cost" type="number" min="0" step="0.01" value={cost} onChange={(e) => setCost(e.target.value)} />
            <Button type="submit" disabled={addRecord.isPending} className="w-full text-xs">
              {addRecord.isPending ? "Adding…" : "+ Add maintenance record"}
            </Button>
          </form>

          {asset.maintenance_records.length === 0 ? (
            <p className="text-sm text-muted">No maintenance recorded yet.</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {asset.maintenance_records.map((r) => (
                <li key={r.id} className="border-b border-hairline/60 pb-2">
                  <div className="flex justify-between">
                    <span className="capitalize text-ink">{r.maintenance_type} - {r.description}</span>
                    <span className="text-muted">{r.cost ? `KES ${Number(r.cost).toLocaleString()}` : "-"}</span>
                  </div>
                  <p className="text-xs text-muted">{r.maintenance_date}</p>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </AdminShell>
  );
}
