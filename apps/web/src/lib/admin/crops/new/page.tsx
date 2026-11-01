"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { Card, Button, Input, Select, Textarea, ErrorState, EmptyState } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import type { Farm, CropPlanting, EffectiveCatalog, CropTypeCatalogEntry } from "@/lib/types";

export default function NewCropPlantingPage() {
  const router = useRouter();
  const { data: farms } = useQuery<Farm[]>({
    queryKey: ["farms"],
    queryFn: () => apiFetch<Farm[]>("/api/v1/farms"),
  });

  // Crop-type options come from this tenant's own effective catalog, not a
  // hardcoded list - a platform admin may have restricted which crop types
  // this organization can use (see the "catalog" module), so the dropdown
  // here always reflects exactly what the backend will accept.
  const { data: catalog, isLoading: catalogLoading } = useQuery<EffectiveCatalog>({
    queryKey: ["catalog"],
    queryFn: () => apiFetch<EffectiveCatalog>("/api/v1/catalog"),
  });

  const [form, setForm] = useState({
    farm_id: "",
    location_id: "",
    planting_number: "",
    crop_type: "",
    variety: "",
    planting_date: new Date().toISOString().slice(0, 10),
    planting_method: "",
    area_size: "",
    area_unit: "acres",
    expected_harvest_date: "",
    acquisition_cost: "",
    notes: "",
  });
  const [error, setError] = useState<string | null>(null);

  const selectedFarm = farms?.find((f) => f.id === form.farm_id);
  const allLocations = selectedFarm?.branches.flatMap((b) => b.locations) ?? [];

  // Group crop-type options by category (fodder / cash_crop / horticulture /
  // cereal / legume / root_tuber / flower) so the dropdown stays readable
  // even with 30+ options.
  const cropTypesByCategory = (catalog?.crop_types ?? []).reduce<Record<string, CropTypeCatalogEntry[]>>(
    (acc, c) => {
      (acc[c.category] ??= []).push(c);
      return acc;
    },
    {},
  );
  const CATEGORY_LABELS: Record<string, string> = {
    fodder: "Fodder", cash_crop: "Cash / bearing crops", horticulture: "Horticulture",
    cereal: "Cereals", legume: "Legumes", root_tuber: "Roots & tubers", flower: "Flowers",
  };

  const create = useMutation({
    mutationFn: () =>
      apiFetch<CropPlanting>("/api/v1/crops", {
        method: "POST",
        body: JSON.stringify({
          farm_id: form.farm_id,
          location_id: form.location_id || null,
          planting_number: form.planting_number,
          crop_type: form.crop_type,
          variety: form.variety || null,
          planting_date: form.planting_date,
          planting_method: form.planting_method || null,
          area_size: form.area_size || null,
          area_unit: form.area_unit,
          expected_harvest_date: form.expected_harvest_date || null,
          acquisition_cost: form.acquisition_cost || "0",
          notes: form.notes || null,
        }),
      }),
    onSuccess: (planting) => router.push(`/admin/crops/${planting.id}`),
    onError: (err) => setError(err instanceof ApiError ? err.message : "Failed to register planting"),
  });

  if (!catalogLoading && catalog && !catalog.crops_enabled) {
    return (
      <AdminShell>
        <EmptyState
          title="Crops aren't enabled for this organization"
          body="Ask your platform administrator to enable the crops module for your account."
        />
      </AdminShell>
    );
  }

  return (
    <AdminShell>
      <h1 className="font-display text-2xl text-forest">Register a crop planting</h1>
      <p className="mb-6 text-sm text-muted">Add a new plot/batch of a crop to your farm.</p>

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
              <option key={f.id} value={f.id}>{f.name}</option>
            ))}
          </Select>

          {allLocations.length > 0 && (
            <Select
              id="location"
              label="Location / plot"
              value={form.location_id}
              onChange={(e) => setForm({ ...form, location_id: e.target.value })}
            >
              <option value="">Unassigned</option>
              {allLocations.map((l) => (
                <option key={l.id} value={l.id}>{l.name}</option>
              ))}
            </Select>
          )}

          <Input
            id="planting_number"
            label="Planting number"
            required
            value={form.planting_number}
            onChange={(e) => setForm({ ...form, planting_number: e.target.value })}
          />

          <div className="grid grid-cols-2 gap-4">
            <Select
              id="crop_type"
              label="Crop type"
              required
              value={form.crop_type}
              onChange={(e) => setForm({ ...form, crop_type: e.target.value })}
            >
              <option value="">
                {catalogLoading ? "Loading crop types…" : "Select a crop type…"}
              </option>
              {Object.entries(cropTypesByCategory).map(([category, types]) => (
                <optgroup key={category} label={CATEGORY_LABELS[category] ?? category}>
                  {types.map((t) => (
                    <option key={t.code} value={t.code}>{t.label}</option>
                  ))}
                </optgroup>
              ))}
            </Select>
            <Input
              id="variety"
              label="Variety"
              placeholder='e.g. "Hass" avocado'
              value={form.variety}
              onChange={(e) => setForm({ ...form, variety: e.target.value })}
            />
          </div>

          {catalog && catalog.crops_enabled && catalog.crop_types.length === 0 && (
            <ErrorState message="Your platform administrator hasn't enabled any crop types for this organization yet." />
          )}

          <div className="grid grid-cols-2 gap-4">
            <Input
              id="planting_date"
              label="Planting date"
              type="date"
              required
              value={form.planting_date}
              onChange={(e) => setForm({ ...form, planting_date: e.target.value })}
            />
            <Select
              id="planting_method"
              label="Planting method"
              value={form.planting_method}
              onChange={(e) => setForm({ ...form, planting_method: e.target.value })}
            >
              <option value="">Not specified</option>
              <option value="seed">Seed</option>
              <option value="seedling">Seedling</option>
              <option value="cutting">Cutting</option>
              <option value="grafted">Grafted</option>
              <option value="tissue_culture">Tissue culture</option>
            </Select>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <Input
              id="area_size"
              label="Area size"
              type="number"
              min="0"
              step="0.01"
              value={form.area_size}
              onChange={(e) => setForm({ ...form, area_size: e.target.value })}
            />
            <Select
              id="area_unit"
              label="Area unit"
              value={form.area_unit}
              onChange={(e) => setForm({ ...form, area_unit: e.target.value })}
            >
              <option value="acres">Acres</option>
              <option value="hectares">Hectares</option>
            </Select>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <Input
              id="expected_harvest_date"
              label="Expected harvest date"
              type="date"
              value={form.expected_harvest_date}
              onChange={(e) => setForm({ ...form, expected_harvest_date: e.target.value })}
            />
            <Input
              id="acquisition_cost"
              label="Acquisition/input cost (KES)"
              type="number"
              min="0"
              step="0.01"
              value={form.acquisition_cost}
              onChange={(e) => setForm({ ...form, acquisition_cost: e.target.value })}
            />
          </div>

          <Textarea
            id="notes"
            label="Notes"
            value={form.notes}
            onChange={(e) => setForm({ ...form, notes: e.target.value })}
          />

          <Button type="submit" disabled={create.isPending || !form.farm_id || !form.crop_type} className="w-full">
            {create.isPending ? "Registering…" : "Register planting"}
          </Button>
        </form>
      </Card>
    </AdminShell>
  );
}
