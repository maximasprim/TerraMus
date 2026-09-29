"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { Card, Button, Input, Select, Modal, ErrorState, EmptyState } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import type { Farm } from "@/lib/types";

const LOCATION_TYPES = ["paddock", "barn", "pen", "grazing_area", "quarantine"] as const;

export default function FarmsPage() {
  const queryClient = useQueryClient();
  const [farmModalOpen, setFarmModalOpen] = useState(false);
  const [branchModalFarmId, setBranchModalFarmId] = useState<string | null>(null);
  const [locationModal, setLocationModal] = useState<{ farmId: string; branchId: string } | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  const { data: farms, isLoading, error } = useQuery<Farm[]>({
    queryKey: ["farms"],
    queryFn: () => apiFetch<Farm[]>("/api/v1/farms"),
  });

  const invalidateFarms = () => queryClient.invalidateQueries({ queryKey: ["farms"] });

  const createFarm = useMutation({
    mutationFn: (body: { name: string; county?: string; address?: string }) =>
      apiFetch("/api/v1/farms", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      invalidateFarms();
      setFarmModalOpen(false);
      setFormError(null);
    },
    onError: (err) => setFormError(err instanceof ApiError ? err.message : "Failed to create farm"),
  });

  const createBranch = useMutation({
    mutationFn: ({ farmId, name }: { farmId: string; name: string }) =>
      apiFetch(`/api/v1/farms/${farmId}/branches`, { method: "POST", body: JSON.stringify({ name }) }),
    onSuccess: () => {
      invalidateFarms();
      setBranchModalFarmId(null);
      setFormError(null);
    },
    onError: (err) => setFormError(err instanceof ApiError ? err.message : "Failed to create branch"),
  });

  const createLocation = useMutation({
    mutationFn: ({
      farmId,
      branchId,
      name,
      location_type,
    }: {
      farmId: string;
      branchId: string;
      name: string;
      location_type: string;
    }) =>
      apiFetch(`/api/v1/farms/${farmId}/branches/${branchId}/locations`, {
        method: "POST",
        body: JSON.stringify({ name, location_type }),
      }),
    onSuccess: () => {
      invalidateFarms();
      setLocationModal(null);
      setFormError(null);
    },
    onError: (err) => setFormError(err instanceof ApiError ? err.message : "Failed to create location"),
  });

  return (
    <AdminShell>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl text-forest">Farms</h1>
          <p className="text-sm text-muted">Farms, branches, and the paddocks/barns within them.</p>
        </div>
        <Button onClick={() => { setFormError(null); setFarmModalOpen(true); }}>+ New farm</Button>
      </div>

      {error && <ErrorState message={error instanceof ApiError ? error.message : "Failed to load farms"} />}
      {isLoading && <p className="text-sm text-muted">Loading…</p>}
      {farms && farms.length === 0 && (
        <EmptyState title="No farms yet" body="Create your first farm to start registering livestock." />
      )}

      <div className="space-y-4">
        {farms?.map((farm) => (
          <Card key={farm.id}>
            <div className="mb-3 flex items-center justify-between">
              <div>
                <h2 className="font-display text-lg text-forest">{farm.name}</h2>
                {farm.county && <p className="text-xs text-muted">{farm.county}</p>}
              </div>
              <Button variant="ghost" onClick={() => { setFormError(null); setBranchModalFarmId(farm.id); }}>
                + Branch
              </Button>
            </div>

            {farm.branches.length === 0 && <p className="text-sm text-muted">No branches yet.</p>}

            <div className="space-y-3">
              {farm.branches.map((branch) => (
                <div key={branch.id} className="rounded-md border border-hairline/60 p-3">
                  <div className="mb-2 flex items-center justify-between">
                    <p className="text-sm font-medium text-ink">{branch.name}</p>
                    <Button
                      variant="ghost"
                      className="px-2 py-1 text-xs"
                      onClick={() => { setFormError(null); setLocationModal({ farmId: farm.id, branchId: branch.id }); }}
                    >
                      + Location
                    </Button>
                  </div>
                  {branch.locations.length === 0 ? (
                    <p className="text-xs text-muted">No locations yet.</p>
                  ) : (
                    <div className="flex flex-wrap gap-2">
                      {branch.locations.map((loc) => (
                        <span
                          key={loc.id}
                          className="rounded-full border border-hairline bg-paper px-2 py-1 text-xs capitalize text-muted"
                        >
                          {loc.name} · {loc.location_type.replace(/_/g, " ")}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </Card>
        ))}
      </div>

      <Modal open={farmModalOpen} onClose={() => setFarmModalOpen(false)} title="New farm">
        <FarmForm error={formError} onSubmit={(body) => createFarm.mutate(body)} pending={createFarm.isPending} />
      </Modal>

      <Modal open={!!branchModalFarmId} onClose={() => setBranchModalFarmId(null)} title="New branch">
        <BranchForm
          error={formError}
          pending={createBranch.isPending}
          onSubmit={(name) => branchModalFarmId && createBranch.mutate({ farmId: branchModalFarmId, name })}
        />
      </Modal>

      <Modal open={!!locationModal} onClose={() => setLocationModal(null)} title="New location">
        <LocationForm
          error={formError}
          pending={createLocation.isPending}
          onSubmit={(name, location_type) =>
            locationModal &&
            createLocation.mutate({ ...locationModal, name, location_type })
          }
        />
      </Modal>
    </AdminShell>
  );
}

function FarmForm({
  onSubmit,
  error,
  pending,
}: {
  onSubmit: (body: { name: string; county?: string; address?: string }) => void;
  error: string | null;
  pending: boolean;
}) {
  const [name, setName] = useState("");
  const [county, setCounty] = useState("");
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ name, county: county || undefined });
      }}
      className="space-y-3"
    >
      {error && <ErrorState message={error} />}
      <Input id="farm-name" label="Farm name" required value={name} onChange={(e) => setName(e.target.value)} />
      <Input id="farm-county" label="County" value={county} onChange={(e) => setCounty(e.target.value)} />
      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Creating…" : "Create farm"}
      </Button>
    </form>
  );
}

function BranchForm({
  onSubmit,
  error,
  pending,
}: {
  onSubmit: (name: string) => void;
  error: string | null;
  pending: boolean;
}) {
  const [name, setName] = useState("");
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(name);
      }}
      className="space-y-3"
    >
      {error && <ErrorState message={error} />}
      <Input id="branch-name" label="Branch name" required value={name} onChange={(e) => setName(e.target.value)} />
      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Creating…" : "Create branch"}
      </Button>
    </form>
  );
}

function LocationForm({
  onSubmit,
  error,
  pending,
}: {
  onSubmit: (name: string, locationType: string) => void;
  error: string | null;
  pending: boolean;
}) {
  const [name, setName] = useState("");
  const [type, setType] = useState<string>(LOCATION_TYPES[0]);
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(name, type);
      }}
      className="space-y-3"
    >
      {error && <ErrorState message={error} />}
      <Input id="loc-name" label="Location name" required value={name} onChange={(e) => setName(e.target.value)} />
      <Select id="loc-type" label="Type" value={type} onChange={(e) => setType(e.target.value)}>
        {LOCATION_TYPES.map((t) => (
          <option key={t} value={t}>
            {t.replace(/_/g, " ")}
          </option>
        ))}
      </Select>
      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Creating…" : "Create location"}
      </Button>
    </form>
  );
}
