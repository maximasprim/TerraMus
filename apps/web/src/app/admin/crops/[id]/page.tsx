"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { Card, TagChip, StatusBadge, ErrorState, Button, Modal, Input, Select, Textarea } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import type { CropPlanting, CropEvent, HarvestRecord, CropPlantingProfitability } from "@/lib/types";
import { clsx } from "clsx";

const ALL_TABS = ["Overview", "Timeline", "Harvests"] as const;
type Tab = (typeof ALL_TABS)[number];

// Mirrors apps/api/app/modules/crops/service.py's _ALLOWED_TRANSITIONS - kept
// in sync by hand, same convention as livestock's detail page; the backend
// is still the enforcement point.
const ALLOWED_TRANSITIONS: Record<string, string[]> = {
  growing: ["ready_for_harvest", "harvesting", "fallow", "failed", "archived"],
  ready_for_harvest: ["harvesting", "growing", "failed", "archived"],
  harvesting: ["harvested", "ready_for_harvest", "growing", "failed", "archived"],
  harvested: ["fallow", "growing", "archived"],
  fallow: ["growing", "archived"],
  failed: [],
  archived: [],
};

export default function CropPlantingDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [tab, setTab] = useState<Tab>("Overview");
  const queryClient = useQueryClient();

  const plantingQuery = useQuery<CropPlanting>({
    queryKey: ["crop-planting", id],
    queryFn: () => apiFetch<CropPlanting>(`/api/v1/crops/${id}`),
  });
  const timelineQuery = useQuery<CropEvent[]>({
    queryKey: ["crop-planting", id, "timeline"],
    queryFn: () => apiFetch<CropEvent[]>(`/api/v1/crops/${id}/timeline`),
    enabled: tab === "Timeline",
  });
  const harvestsQuery = useQuery<HarvestRecord[]>({
    queryKey: ["crop-planting", id, "harvests"],
    queryFn: () => apiFetch<HarvestRecord[]>(`/api/v1/crops/${id}/harvests`),
    enabled: tab === "Harvests",
  });
  const profitabilityQuery = useQuery<CropPlantingProfitability>({
    queryKey: ["crop-planting", id, "profitability"],
    queryFn: () => apiFetch<CropPlantingProfitability>(`/api/v1/crops/${id}/profitability`),
    enabled: tab === "Overview",
  });

  const [statusError, setStatusError] = useState<string | null>(null);
  const changeStatus = useMutation({
    mutationFn: (status: string) =>
      apiFetch(`/api/v1/crops/${id}/status`, { method: "POST", body: JSON.stringify({ status }) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["crop-planting", id] });
      queryClient.invalidateQueries({ queryKey: ["crop-planting", id, "timeline"] });
      setStatusError(null);
    },
    onError: (err) => setStatusError(err instanceof ApiError ? err.message : "Failed to change status"),
  });

  const [harvestModalOpen, setHarvestModalOpen] = useState(false);
  const [harvestFormError, setHarvestFormError] = useState<string | null>(null);
  const addHarvest = useMutation({
    mutationFn: (body: { quantity: string; unit: string; quality_grade?: string; notes?: string }) =>
      apiFetch(`/api/v1/crops/${id}/harvests`, { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["crop-planting", id, "harvests"] });
      queryClient.invalidateQueries({ queryKey: ["crop-planting", id, "timeline"] });
      setHarvestModalOpen(false);
      setHarvestFormError(null);
    },
    onError: (err) => setHarvestFormError(err instanceof ApiError ? err.message : "Failed to record harvest"),
  });

  if (plantingQuery.error) {
    return (
      <AdminShell>
        <ErrorState message={plantingQuery.error instanceof ApiError ? plantingQuery.error.message : "Failed to load planting"} />
      </AdminShell>
    );
  }
  if (!plantingQuery.data) {
    return (
      <AdminShell>
        <p className="text-sm text-muted">Loading…</p>
      </AdminShell>
    );
  }

  const p = plantingQuery.data;

  return (
    <AdminShell>
      <div className="mb-6 flex items-start justify-between">
        <div>
          <div className="mb-2 flex items-center gap-3">
            <TagChip>{p.planting_number}</TagChip>
            <StatusBadge status={p.status} />
          </div>
          <h1 className="font-display text-2xl text-forest capitalize">
            {p.crop_type.replace(/_/g, " ")}
            {p.variety ? ` · ${p.variety}` : ""}
          </h1>
          <p className="text-sm text-muted">
            {p.is_perennial ? "Bearing / perennial crop" : "Annual crop"}
            {p.area_size ? ` · ${p.area_size} ${p.area_unit}` : ""}
          </p>
        </div>
        {p.current_value && (
          <div className="text-right">
            <p className="text-xs uppercase tracking-wider text-muted">Current value</p>
            <p className="font-display text-2xl text-forest">KES {Number(p.current_value).toLocaleString()}</p>
          </div>
        )}
      </div>

      {ALLOWED_TRANSITIONS[p.status]?.length > 0 && (
        <div className="mb-6 flex flex-wrap items-center gap-2">
          <span className="text-xs uppercase tracking-wider text-muted">Change status:</span>
          {ALLOWED_TRANSITIONS[p.status].map((next) => (
            <Button
              key={next}
              variant="ghost"
              className="px-3 py-1 text-xs capitalize"
              disabled={changeStatus.isPending}
              onClick={() => changeStatus.mutate(next)}
            >
              → {next.replace(/_/g, " ")}
            </Button>
          ))}
        </div>
      )}
      {statusError && <div className="mb-4"><ErrorState message={statusError} /></div>}

      <div className="mb-6 flex gap-1 border-b border-hairline">
        {ALL_TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={clsx(
              "border-b-2 px-4 py-2 text-sm font-medium transition-colors",
              tab === t ? "border-brass text-forest" : "border-transparent text-muted hover:text-ink",
            )}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "Overview" && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <Card>
            <h2 className="mb-3 font-display text-lg text-forest">Details</h2>
            <dl className="space-y-2 text-sm">
              <Row label="Planting date" value={p.planting_date} />
              <Row label="Planting method" value={p.planting_method?.replace(/_/g, " ") ?? "-"} />
              <Row label="Expected harvest date" value={p.expected_harvest_date ?? "-"} />
              <Row label="Expected yield" value={p.expected_yield ? `${p.expected_yield} ${p.yield_unit ?? ""}` : "-"} />
              <Row label="Source" value={p.source ?? "-"} />
              <Row label="Supplier" value={p.supplier ?? "-"} />
            </dl>
          </Card>
          <Card>
            <h2 className="mb-3 font-display text-lg text-forest">Health & investment</h2>
            <dl className="space-y-2 text-sm">
              <Row label="Health status" value={p.health_status.replace(/_/g, " ")} />
              <Row label="Acquisition/input cost" value={`KES ${Number(p.acquisition_cost).toLocaleString()}`} />
              {profitabilityQuery.data && (
                <Row
                  label="Total investment"
                  value={`KES ${Number(profitabilityQuery.data.total_investment).toLocaleString()}`}
                />
              )}
            </dl>
            {p.notes && (
              <>
                <h3 className="mb-1 mt-4 text-xs uppercase tracking-wider text-muted">Notes</h3>
                <p className="text-sm text-ink">{p.notes}</p>
              </>
            )}
          </Card>
        </div>
      )}

      {tab === "Timeline" && (
        <Card>
          {timelineQuery.isLoading && <p className="text-sm text-muted">Loading…</p>}
          {timelineQuery.data && timelineQuery.data.length === 0 && (
            <p className="text-sm text-muted">No events recorded yet.</p>
          )}
          {timelineQuery.data && timelineQuery.data.length > 0 && (
            <ol className="relative space-y-4 border-l border-hairline pl-6">
              {timelineQuery.data.map((event) => (
                <li key={event.id} className="relative">
                  <span className="absolute -left-[27px] top-1 h-2.5 w-2.5 rounded-full bg-brass" />
                  <p className="text-sm font-medium capitalize text-ink">
                    {event.event_type.replace(/[_:]/g, " ")}
                  </p>
                  <p className="text-xs text-muted">{new Date(event.event_at).toLocaleString()}</p>
                </li>
              ))}
            </ol>
          )}
        </Card>
      )}

      {tab === "Harvests" && (
        <div>
          <div className="mb-4 flex justify-end">
            <Button onClick={() => { setHarvestFormError(null); setHarvestModalOpen(true); }}>
              + Record harvest
            </Button>
          </div>
          <Card>
            {harvestsQuery.isLoading && <p className="text-sm text-muted">Loading…</p>}
            {harvestsQuery.data && harvestsQuery.data.length === 0 && (
              <p className="text-sm text-muted">
                No harvests recorded yet.{p.is_perennial ? " This is a bearing crop, so expect repeat harvests over its productive life." : ""}
              </p>
            )}
            {harvestsQuery.data && harvestsQuery.data.length > 0 && (
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-hairline text-xs uppercase tracking-wider text-muted">
                    <th className="py-2 font-medium">Date</th>
                    <th className="py-2 font-medium">Quantity</th>
                    <th className="py-2 font-medium">Grade</th>
                    <th className="py-2 font-medium">Cumulative</th>
                    <th className="py-2 font-medium">Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {harvestsQuery.data.map((h) => (
                    <tr key={h.id} className="border-b border-hairline/60">
                      <td className="py-2">{new Date(h.harvested_at).toLocaleDateString()}</td>
                      <td className="py-2">{h.quantity} {h.unit}</td>
                      <td className="py-2">{h.quality_grade ?? "-"}</td>
                      <td className="py-2">{h.cumulative_yield ? `${h.cumulative_yield} ${h.unit}` : "-"}</td>
                      <td className="py-2 text-muted">{h.notes ?? "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </div>
      )}

      <Modal open={harvestModalOpen} onClose={() => setHarvestModalOpen(false)} title="Record a harvest">
        <HarvestForm
          error={harvestFormError}
          pending={addHarvest.isPending}
          defaultUnit={p.yield_unit ?? ""}
          onSubmit={(body) => addHarvest.mutate(body)}
        />
      </Modal>
    </AdminShell>
  );
}

function HarvestForm({
  error, pending, defaultUnit, onSubmit,
}: {
  error: string | null;
  pending: boolean;
  defaultUnit: string;
  onSubmit: (body: { quantity: string; unit: string; quality_grade?: string; notes?: string }) => void;
}) {
  const [quantity, setQuantity] = useState("");
  const [unit, setUnit] = useState(defaultUnit);
  const [qualityGrade, setQualityGrade] = useState("");
  const [notes, setNotes] = useState("");

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ quantity, unit, quality_grade: qualityGrade || undefined, notes: notes || undefined });
      }}
      className="space-y-3"
    >
      {error && <ErrorState message={error} />}
      <div className="grid grid-cols-2 gap-3">
        <Input id="harvest-quantity" label="Quantity" type="number" min="0" step="0.01" required value={quantity} onChange={(e) => setQuantity(e.target.value)} />
        <Input id="harvest-unit" label="Unit" required placeholder="kg, bags, crates…" value={unit} onChange={(e) => setUnit(e.target.value)} />
      </div>
      <Select id="harvest-grade" label="Quality grade (optional)" value={qualityGrade} onChange={(e) => setQualityGrade(e.target.value)}>
        <option value="">Not graded</option>
        <option value="premium">Premium</option>
        <option value="grade_a">Grade A</option>
        <option value="grade_b">Grade B</option>
        <option value="reject">Reject</option>
      </Select>
      <Textarea id="harvest-notes" label="Notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
      <Button type="submit" disabled={pending || !quantity || !unit} className="w-full">
        {pending ? "Recording…" : "Record harvest"}
      </Button>
    </form>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between border-b border-hairline/60 pb-2 capitalize">
      <dt className="text-muted">{label}</dt>
      <dd className="font-medium text-ink">{value}</dd>
    </div>
  );
}
