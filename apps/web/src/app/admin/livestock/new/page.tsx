"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { Card, Button, Input, Select, ErrorState, EmptyState } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import type { Farm, Animal, EffectiveCatalog } from "@/lib/types";

export default function NewAnimalPage() {
  const router = useRouter();
  const { data: farms } = useQuery<Farm[]>({
    queryKey: ["farms"],
    queryFn: () => apiFetch<Farm[]>("/api/v1/farms"),
  });

  // Species options come from this tenant's own effective catalog - a
  // platform admin may have restricted which species this organization can
  // use (see the "catalog" module), so this always reflects exactly what
  // the backend will accept, instead of a hardcoded cattle/sheep list.
  const { data: catalog } = useQuery<EffectiveCatalog>({
    queryKey: ["catalog"],
    queryFn: () => apiFetch<EffectiveCatalog>("/api/v1/catalog"),
  });

  const [form, setForm] = useState({
    farm_id: "",
    location_id: "",
    animal_number: "",
    species: "cattle",
    breed: "",
    sex: "female",
    acquisition_date: new Date().toISOString().slice(0, 10),
    acquisition_method: "purchased",
    acquisition_cost: "",
    current_weight: "",
  });
  const [error, setError] = useState<string | null>(null);

  // The form used to start on "cattle" unconditionally. For an organization restricted to,
  // say, poultry that value isn't in the dropdown yet would still be submitted (and rejected
  // with a 403). Once the catalog loads, fall back to the first species they may actually use.
  useEffect(() => {
    if (!catalog || catalog.species.length === 0) return;
    if (!catalog.species.some((s) => s.code === form.species)) {
      setForm((f) => ({ ...f, species: catalog.species[0].code }));
    }
  }, [catalog, form.species]);

  const selectedFarm = farms?.find((f) => f.id === form.farm_id);
  const allLocations = selectedFarm?.branches.flatMap((b) => b.locations) ?? [];

  const create = useMutation({
    mutationFn: () =>
      apiFetch<Animal>("/api/v1/livestock", {
        method: "POST",
        body: JSON.stringify({
          farm_id: form.farm_id,
          location_id: form.location_id || null,
          animal_number: form.animal_number,
          species: form.species,
          breed: form.breed || null,
          sex: form.sex,
          acquisition_date: form.acquisition_date,
          acquisition_method: form.acquisition_method,
          acquisition_cost: form.acquisition_cost || "0",
          current_weight: form.current_weight || null,
        }),
      }),
    onSuccess: (animal) => router.push(`/admin/livestock/${animal.id}`),
    onError: (err) => setError(err instanceof ApiError ? err.message : "Failed to register animal"),
  });

  if (catalog && !catalog.livestock_enabled) {
    return (
      <AdminShell>
        <EmptyState
          title="Livestock isn't enabled for this organization"
          body="Ask your platform administrator to enable the livestock module for your account."
        />
      </AdminShell>
    );
  }

  return (
    <AdminShell>
      <h1 className="font-display text-2xl text-forest">Register an animal</h1>
      <p className="mb-6 text-sm text-muted">Add a new animal to the herd.</p>

      <Card className="max-w-xl">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            create.mutate();
          }}
          className="space-y-4"
        >
          {error && <ErrorState message={error} />}

          <Select
            id="farm"
            label="Farm"
            required
            value={form.farm_id}
            onChange={(e) => setForm({ ...form, farm_id: e.target.value, location_id: "" })}
          >
            <option value="">Select a farm…</option>
            {farms?.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name}
              </option>
            ))}
          </Select>

          {allLocations.length > 0 && (
            <Select
              id="location"
              label="Location"
              value={form.location_id}
              onChange={(e) => setForm({ ...form, location_id: e.target.value })}
            >
              <option value="">Unassigned</option>
              {allLocations.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name}
                </option>
              ))}
            </Select>
          )}

          <Input
            id="animal_number"
            label="Animal number (ear tag ID)"
            required
            value={form.animal_number}
            onChange={(e) => setForm({ ...form, animal_number: e.target.value })}
          />

          <div className="grid grid-cols-2 gap-4">
            <Select
              id="species"
              label="Species"
              value={form.species}
              onChange={(e) => setForm({ ...form, species: e.target.value })}
            >
               {(catalog?.species ?? []).map((s) => (
                <option key={s.code} value={s.code}>{s.label}</option>
              ))}
            </Select>
            <Input
              id="breed"
              label="Breed"
              value={form.breed}
              onChange={(e) => setForm({ ...form, breed: e.target.value })}
            />
          </div>
          {catalog && catalog.species.length === 0 && (
            <p className="text-sm text-clay">
              No species are enabled for your organization yet. Ask your platform administrator to enable at least one.
            </p>
          )}

          <Select id="sex" label="Sex" value={form.sex} onChange={(e) => setForm({ ...form, sex: e.target.value })}>
            <option value="female">Female</option>
            <option value="male">Male</option>
          </Select>

          <div className="grid grid-cols-2 gap-4">
            <Input
              id="acquisition_date"
              label="Acquisition date"
              type="date"
              required
              value={form.acquisition_date}
              onChange={(e) => setForm({ ...form, acquisition_date: e.target.value })}
            />
            <Select
              id="acquisition_method"
              label="Acquisition method"
              value={form.acquisition_method}
              onChange={(e) => setForm({ ...form, acquisition_method: e.target.value })}
            >
              <option value="purchased">Purchased</option>
              <option value="born_on_farm">Born on farm</option>
              <option value="transferred_in">Transferred in</option>
              <option value="gifted">Gifted</option>
            </Select>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <Input
              id="acquisition_cost"
              label="Acquisition cost (KES)"
              type="number"
              min="0"
              step="0.01"
              value={form.acquisition_cost}
              onChange={(e) => setForm({ ...form, acquisition_cost: e.target.value })}
            />
            <Input
              id="current_weight"
              label="Current weight (kg)"
              type="number"
              min="0"
              step="0.01"
              value={form.current_weight}
              onChange={(e) => setForm({ ...form, current_weight: e.target.value })}
            />
          </div>

          <Button type="submit" disabled={create.isPending || !form.farm_id} className="w-full">
            {create.isPending ? "Registering…" : "Register animal"}
          </Button>
        </form>
      </Card>
    </AdminShell>
  );
}
