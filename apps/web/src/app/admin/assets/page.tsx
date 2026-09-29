"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { Card, Button, Input, Select, Modal, ErrorState, EmptyState, StatusBadge } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import type { Asset } from "@/lib/types";

const ASSET_TYPES = [
  "tractor", "vehicle", "pump", "generator", "milking_equipment",
  "water_system", "building", "fence", "tool", "machinery", "other",
] as const;

export default function AssetsPage() {
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data, isLoading, error: loadError } = useQuery<Asset[]>({
    queryKey: ["assets"],
    queryFn: () => apiFetch<Asset[]>("/api/v1/assets"),
  });

  const create = useMutation({
    mutationFn: (body: {
      name: string; asset_type: string; acquisition_date?: string; acquisition_cost?: string;
      useful_life_years?: number; salvage_value?: string;
    }) => apiFetch("/api/v1/assets", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["assets"] });
      setModalOpen(false);
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Failed to create asset"),
  });

  return (
    <AdminShell>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl text-forest">Assets</h1>
          <p className="text-sm text-muted">Equipment and machinery - depreciation is computed automatically.</p>
        </div>
        <Button onClick={() => { setError(null); setModalOpen(true); }}>+ New asset</Button>
      </div>

      {loadError && <ErrorState message={loadError instanceof ApiError ? loadError.message : "Failed to load assets"} />}
      {isLoading && <p className="text-sm text-muted">Loading…</p>}
      {data && data.length === 0 && (
        <EmptyState title="No assets yet" body="Track tractors, vehicles, and equipment here." />
      )}

      {data && data.length > 0 && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {data.map((a) => (
            <Link key={a.id} href={`/admin/assets/${a.id}`}>
              <Card className="h-full">
                <div className="mb-1 flex items-center justify-between">
                  <h2 className="font-display text-lg text-forest">{a.name}</h2>
                  <StatusBadge status={a.status} />
                </div>
                <p className="text-xs capitalize text-muted">{a.asset_type.replace(/_/g, " ")}</p>
                <p className="mt-3 font-display text-xl text-ink">
                  {a.current_value ? `KES ${Number(a.current_value).toLocaleString()}` : "Value unknown"}
                </p>
                <p className="text-xs text-muted">{a.asset_number}</p>
              </Card>
            </Link>
          ))}
        </div>
      )}

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title="New asset">
        <AssetForm error={error} pending={create.isPending} onSubmit={(b) => create.mutate(b)} />
      </Modal>
    </AdminShell>
  );
}

function AssetForm({
  onSubmit,
  error,
  pending,
}: {
  onSubmit: (body: {
    name: string; asset_type: string; acquisition_date?: string; acquisition_cost?: string;
    useful_life_years?: number; salvage_value?: string;
  }) => void;
  error: string | null;
  pending: boolean;
}) {
  const [name, setName] = useState("");
  const [assetType, setAssetType] = useState<string>(ASSET_TYPES[0]);
  const [acquisitionDate, setAcquisitionDate] = useState("");
  const [acquisitionCost, setAcquisitionCost] = useState("");
  const [usefulLife, setUsefulLife] = useState("");
  const [salvageValue, setSalvageValue] = useState("");

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({
          name, asset_type: assetType,
          acquisition_date: acquisitionDate || undefined,
          acquisition_cost: acquisitionCost || undefined,
          useful_life_years: usefulLife ? Number(usefulLife) : undefined,
          salvage_value: salvageValue || undefined,
        });
      }}
      className="space-y-3"
    >
      {error && <ErrorState message={error} />}
      <Input id="asset-name" label="Name" required value={name} onChange={(e) => setName(e.target.value)} />
      <Select id="asset-type" label="Type" value={assetType} onChange={(e) => setAssetType(e.target.value)}>
        {ASSET_TYPES.map((t) => (
          <option key={t} value={t}>{t.replace(/_/g, " ")}</option>
        ))}
      </Select>
      <Input id="asset-acq-date" label="Acquisition date" type="date" value={acquisitionDate} onChange={(e) => setAcquisitionDate(e.target.value)} />
      <div className="grid grid-cols-2 gap-4">
        <Input
          id="asset-cost" label="Acquisition cost" type="number" min="0" step="0.01"
          value={acquisitionCost} onChange={(e) => setAcquisitionCost(e.target.value)}
        />
        <Input
          id="asset-life" label="Useful life (years)" type="number" min="1"
          value={usefulLife} onChange={(e) => setUsefulLife(e.target.value)}
        />
      </div>
      <Input
        id="asset-salvage" label="Salvage value" type="number" min="0" step="0.01"
        value={salvageValue} onChange={(e) => setSalvageValue(e.target.value)}
      />
      <p className="text-xs text-muted">
        Leave acquisition cost / useful life blank to skip depreciation tracking for this asset.
      </p>
      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Creating…" : "Create asset"}
      </Button>
    </form>
  );
}
