"use client";

import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { Can } from "@/components/can";
import { EditEntityModal } from "@/components/edit-entity-modal";
import { useCan } from "@/lib/use-auth";
import { Card, TagChip, StatusBadge, ErrorState, Button, Modal, Input, Select, Textarea } from "@/components/ui";
import { apiFetch, apiDownload, getAccessToken, API_BASE, ApiError } from "@/lib/api";
import type { Animal, AnimalEvent, HealthRecord, WeightRecord, BreedingRecord, MilkRecord, Farm, Movement } from "@/lib/types";
import { clsx } from "clsx";

const ALL_TABS = ["Overview", "Timeline", "Health", "Weights", "Breeding", "Dairy", "Movements"] as const;
type Tab = (typeof ALL_TABS)[number];

const RECORD_TYPES = [
  "vaccination", "treatment", "deworming", "examination",
  "injury", "lab_result", "vet_visit", "prescription",
] as const;

// Mirrors apps/api/app/modules/livestock/service.py's _ALLOWED_TRANSITIONS -
// kept in sync by hand since this is a small, stable table; the backend is
// still the enforcement point (this only avoids offering an invalid choice).
const ALLOWED_TRANSITIONS: Record<string, string[]> = {
  active: ["for_sale", "quarantined", "missing", "deceased", "transferred", "archived"],
  quarantined: ["active", "deceased", "missing"],
  for_sale: ["reserved", "active", "sold", "deceased", "missing"],
  reserved: ["sold", "for_sale", "deceased"],
  sold: [],
  transferred: [],
  deceased: [],
  missing: ["active", "deceased"],
  archived: [],
};

export default function AnimalDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [tab, setTab] = useState<Tab>("Overview");
  const [healthModalOpen, setHealthModalOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const can = useCan();
  const queryClient = useQueryClient();

  const animalQuery = useQuery<Animal>({
    queryKey: ["animal", id],
    queryFn: () => apiFetch<Animal>(`/api/v1/livestock/${id}`),
  });
  const timelineQuery = useQuery<AnimalEvent[]>({
    queryKey: ["animal", id, "timeline"],
    queryFn: () => apiFetch<AnimalEvent[]>(`/api/v1/livestock/${id}/timeline`),
    enabled: tab === "Timeline",
  });
  const completeFollowUp = useMutation({
    mutationFn: (recordId: string) => apiFetch(`/api/v1/health/records/${recordId}/complete-follow-up`, { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["health", id] }),
  });
  const healthQuery = useQuery<HealthRecord[]>({
    queryKey: ["animal", id, "health"],
    queryFn: () => apiFetch<HealthRecord[]>(`/api/v1/livestock/${id}/health`),
    enabled: tab === "Health",
  });
  const weightsQuery = useQuery<WeightRecord[]>({
    queryKey: ["animal", id, "weights"],
    queryFn: () => apiFetch<WeightRecord[]>(`/api/v1/livestock/${id}/weights`),
    enabled: tab === "Weights",
  });
  const breedingQuery = useQuery<BreedingRecord[]>({
    queryKey: ["animal", id, "breeding"],
    queryFn: () => apiFetch<BreedingRecord[]>(`/api/v1/livestock/${id}/breeding`),
    enabled: tab === "Breeding",
  });
  const milkQuery = useQuery<MilkRecord[]>({
    queryKey: ["animal", id, "milk"],
    queryFn: () => apiFetch<MilkRecord[]>(`/api/v1/livestock/${id}/dairy/milk`),
    enabled: tab === "Dairy",
  });
  const movementsQuery = useQuery<Movement[]>({
    queryKey: ["animal", id, "movements"],
    queryFn: () => apiFetch<Movement[]>(`/api/v1/livestock/${id}/movements`),
    enabled: tab === "Movements",
  });
  const farmsQuery = useQuery<Farm[]>({
    queryKey: ["farms"],
    queryFn: () => apiFetch<Farm[]>("/api/v1/farms"),
    enabled: tab === "Movements",
  });

  const [healthFormError, setHealthFormError] = useState<string | null>(null);
  const createHealthRecord = useMutation({
    mutationFn: (body: {
      record_type: string;
      title: string;
      description?: string;
      cost?: string;
      follow_up_date?: string;
    }) =>
      apiFetch(`/api/v1/livestock/${id}/health`, { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["animal", id, "health"] });
      queryClient.invalidateQueries({ queryKey: ["animal", id] }); // health_status may change
      setHealthModalOpen(false);
      setHealthFormError(null);
    },
    onError: (err) => setHealthFormError(err instanceof ApiError ? err.message : "Failed to add health record"),
  });

  const [weightModalOpen, setWeightModalOpen] = useState(false);
  const [weightFormError, setWeightFormError] = useState<string | null>(null);
  const addWeight = useMutation({
    mutationFn: (body: { weight_kg: string; notes?: string }) =>
      apiFetch(`/api/v1/livestock/${id}/weights`, { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["animal", id, "weights"] });
      queryClient.invalidateQueries({ queryKey: ["animal", id] }); // current_weight changes
      setWeightModalOpen(false);
      setWeightFormError(null);
    },
    onError: (err) => setWeightFormError(err instanceof ApiError ? err.message : "Failed to record weight"),
  });

  const [statusError, setStatusError] = useState<string | null>(null);
  const changeStatus = useMutation({
    mutationFn: (status: string) =>
      apiFetch(`/api/v1/livestock/${id}/status`, { method: "POST", body: JSON.stringify({ status }) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["animal", id] });
      queryClient.invalidateQueries({ queryKey: ["animal", id, "timeline"] });
      setStatusError(null);
    },
    onError: (err) => setStatusError(err instanceof ApiError ? err.message : "Failed to change status"),
  });

  const [breedingModalOpen, setBreedingModalOpen] = useState(false);
  const [breedingFormError, setBreedingFormError] = useState<string | null>(null);
  const createBreeding = useMutation({
    mutationFn: (body: { method: string; mating_date: string; expected_delivery_date?: string; sire_external?: string }) =>
      apiFetch("/api/v1/breeding", { method: "POST", body: JSON.stringify({ ...body, dam_id: id }) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["animal", id, "breeding"] });
      queryClient.invalidateQueries({ queryKey: ["animal", id] }); // reproductive_status changes
      setBreedingModalOpen(false);
      setBreedingFormError(null);
    },
    onError: (err) => setBreedingFormError(err instanceof ApiError ? err.message : "Failed to record breeding"),
  });

  const [checkModalRecordId, setCheckModalRecordId] = useState<string | null>(null);
  const [checkFormError, setCheckFormError] = useState<string | null>(null);
  const addPregnancyCheck = useMutation({
    mutationFn: ({ recordId, body }: { recordId: string; body: { check_date: string; result: string } }) =>
      apiFetch(`/api/v1/breeding/${recordId}/pregnancy-checks`, { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["animal", id, "breeding"] });
      queryClient.invalidateQueries({ queryKey: ["animal", id] });
      setCheckModalRecordId(null);
      setCheckFormError(null);
    },
    onError: (err) => setCheckFormError(err instanceof ApiError ? err.message : "Failed to add pregnancy check"),
  });

  const [deliveryModalRecordId, setDeliveryModalRecordId] = useState<string | null>(null);
  const [deliveryFormError, setDeliveryFormError] = useState<string | null>(null);
  const recordDelivery = useMutation({
    mutationFn: ({ recordId, body }: { recordId: string; body: { actual_delivery_date: string; offspring_count: number } }) =>
      apiFetch(`/api/v1/breeding/${recordId}/delivery`, {
        method: "POST",
        body: JSON.stringify({ ...body, create_offspring_animals: true }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["animal", id, "breeding"] });
      queryClient.invalidateQueries({ queryKey: ["animal", id] });
      setDeliveryModalRecordId(null);
      setDeliveryFormError(null);
    },
    onError: (err) => setDeliveryFormError(err instanceof ApiError ? err.message : "Failed to record delivery"),
  });

  const [dairyActionError, setDairyActionError] = useState<string | null>(null);
  const startLactation = useMutation({
    mutationFn: (start_date: string) =>
      apiFetch(`/api/v1/livestock/${id}/dairy/lactation-cycles`, { method: "POST", body: JSON.stringify({ start_date }) }),
    onSuccess: () => setDairyActionError(null),
    onError: (err) => setDairyActionError(err instanceof ApiError ? err.message : "Failed to start lactation cycle"),
  });
  const dryOff = useMutation({
    mutationFn: (end_date: string) =>
      apiFetch(`/api/v1/livestock/${id}/dairy/lactation-cycles/dry-off`, { method: "POST", body: JSON.stringify({ end_date }) }),
    onSuccess: () => setDairyActionError(null),
    onError: (err) => setDairyActionError(err instanceof ApiError ? err.message : "Failed to dry off"),
  });
  const [milkModalOpen, setMilkModalOpen] = useState(false);
  const [milkFormError, setMilkFormError] = useState<string | null>(null);
  const recordMilk = useMutation({
    mutationFn: (body: { production_date: string; session: string; quantity_liters: string }) =>
      apiFetch(`/api/v1/livestock/${id}/dairy/milk`, { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["animal", id, "milk"] });
      setMilkModalOpen(false);
      setMilkFormError(null);
    },
    onError: (err) => setMilkFormError(err instanceof ApiError ? err.message : "Failed to record milk"),
  });

  const [movementModalOpen, setMovementModalOpen] = useState(false);
  const [movementFormError, setMovementFormError] = useState<string | null>(null);
  const recordMovement = useMutation({
    mutationFn: (body: { to_location_id: string; reason?: string; notes?: string }) =>
      apiFetch(`/api/v1/livestock/${id}/movements`, { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["animal", id, "movements"] });
      queryClient.invalidateQueries({ queryKey: ["animal", id] }); // location_id changes
      setMovementModalOpen(false);
      setMovementFormError(null);
    },
    onError: (err) => setMovementFormError(err instanceof ApiError ? err.message : "Failed to record movement"),
  });

  if (animalQuery.error) {
    return (
      <AdminShell>
        <ErrorState message={animalQuery.error instanceof ApiError ? animalQuery.error.message : "Failed to load animal"} />
      </AdminShell>
    );
  }
  if (!animalQuery.data) {
    return (
      <AdminShell>
        <p className="text-sm text-muted">Loading…</p>
      </AdminShell>
    );
  }

  const a = animalQuery.data;

  return (
    <AdminShell>
      <EditEntityModal entity="livestock" id={id} record={a} open={editOpen} onClose={() => setEditOpen(false)} invalidate={[["animal", id], ["livestock"]]} />
      <div className="mb-6 flex items-start justify-between">
        <div>
          <div className="mb-2 flex items-center gap-3">
            <TagChip>{a.animal_number}</TagChip>
            <StatusBadge status={a.status} />
            {can("livestock.update") && <button type="button" onClick={() => setEditOpen(true)} className="rounded border border-hairline px-2 py-0.5 text-xs text-forest hover:bg-forest/5">Edit</button>}
          </div>
          <h1 className="font-display text-2xl text-forest">{a.name ?? a.animal_number}</h1>
          <p className="text-sm capitalize text-muted">
            {a.species}
            {a.breed ? ` · ${a.breed}` : ""} · {a.sex}
          </p>
        </div>
        {a.current_value && (
          <div className="text-right">
            <p className="text-xs uppercase tracking-wider text-muted">Current value</p>
            <p className="font-display text-2xl text-forest">KES {Number(a.current_value).toLocaleString()}</p>
          </div>
        )}
      </div>

      {can("livestock.update") && ALLOWED_TRANSITIONS[a.status]?.length > 0 && (
        <div className="mb-6 flex flex-wrap items-center gap-2">
          <span className="text-xs uppercase tracking-wider text-muted">Change status:</span>
          {ALLOWED_TRANSITIONS[a.status].map((next) => (
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
        {ALL_TABS.filter((t) => {
          if (t === "Breeding") return a.sex === "female";
          if (t === "Dairy") return a.sex === "female" && a.species === "cattle";
          return true;
        }).map((t) => (
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
              <Row label="Date of birth" value={a.date_of_birth ?? "Unknown"} />
              <Row label="Acquisition date" value={a.acquisition_date} />
              <Row label="Acquisition method" value={a.acquisition_method.replace(/_/g, " ")} />
              <Row label="Acquisition cost" value={`KES ${Number(a.acquisition_cost).toLocaleString()}`} />
              <Row label="Current weight" value={a.current_weight ? `${a.current_weight} kg` : "-"} />
              <Row label="Target weight" value={a.target_weight ? `${a.target_weight} kg` : "-"} />
            </dl>
          </Card>
          <Card>
            <h2 className="mb-3 font-display text-lg text-forest">Health & reproduction</h2>
            <dl className="space-y-2 text-sm">
              <Row label="Health status" value={a.health_status.replace(/_/g, " ")} />
              <Row label="Reproductive status" value={a.reproductive_status?.replace(/_/g, " ") ?? "-"} />
              <Row label="Expected sale price" value={a.expected_sale_price ? `KES ${Number(a.expected_sale_price).toLocaleString()}` : "-"} />
            </dl>
          </Card>
          <AnimalQRCode animalId={a.id} />
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

      {tab === "Health" && (
        <div>
          <div className="mb-4 flex justify-end">
            <Can permission="health.create"><Button onClick={() => { setHealthFormError(null); setHealthModalOpen(true); }}>
              + Add health record
            </Button></Can>
          </div>
          <Card>
            {healthQuery.isLoading && <p className="text-sm text-muted">Loading…</p>}
            {healthQuery.data && healthQuery.data.length === 0 && (
              <p className="text-sm text-muted">No health records yet.</p>
            )}
            {healthQuery.data && healthQuery.data.length > 0 && (
              <div className="space-y-3">
                {healthQuery.data.map((record) => (
                  <div key={record.id} className="border-b border-hairline/60 pb-3 last:border-0 last:pb-0">
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-medium capitalize text-ink">
                        {record.record_type.replace(/_/g, " ")} - {record.title}
                      </p>
                      <p className="text-xs text-muted">{new Date(record.performed_at).toLocaleDateString()}</p>
                    </div>
                    {record.description && <p className="mt-1 text-sm text-muted">{record.description}</p>}
                    <div className="mt-1 flex gap-4 text-xs text-muted">
                      {record.cost && <span>Cost: KES {Number(record.cost).toLocaleString()}</span>}
                      {record.follow_up_date && (
                        <span>
                          Follow-up: {record.follow_up_date}
                          {record.follow_up_completed ? " (done)" : ""}
                        </span>
                      )}
                      {record.follow_up_date && !record.follow_up_completed && (
                        <Can permission="health.create">
                          <button
                            type="button"
                            disabled={completeFollowUp.isPending}
                            onClick={() => completeFollowUp.mutate(record.id)}
                            className="text-forest underline underline-offset-4 disabled:opacity-50"
                          >
                            Mark follow-up done
                          </button>
                        </Can>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      )}

      <Modal open={healthModalOpen} onClose={() => setHealthModalOpen(false)} title="Add health record">
        <HealthRecordForm
          error={healthFormError}
          pending={createHealthRecord.isPending}
          onSubmit={(body) => createHealthRecord.mutate(body)}
        />
      </Modal>

      {tab === "Weights" && (
        <div>
          <div className="mb-4 flex justify-end">
            <Can permission="livestock.update"><Button onClick={() => { setWeightFormError(null); setWeightModalOpen(true); }}>
              + Record weight
            </Button></Can>
          </div>
          <Card>
            {weightsQuery.isLoading && <p className="text-sm text-muted">Loading…</p>}
            {weightsQuery.data && weightsQuery.data.length === 0 && (
              <p className="text-sm text-muted">No weight records yet.</p>
            )}
            {weightsQuery.data && weightsQuery.data.length > 0 && (
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-hairline text-xs uppercase tracking-wider text-muted">
                    <th className="pb-2 font-medium">Date</th>
                    <th className="pb-2 font-medium">Weight</th>
                    <th className="pb-2 font-medium">Avg. daily gain</th>
                    <th className="pb-2 font-medium">Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {weightsQuery.data.map((w) => (
                    <tr key={w.id} className="border-b border-hairline/60 last:border-0">
                      <td className="py-2">{new Date(w.recorded_at).toLocaleDateString()}</td>
                      <td className="py-2 font-medium text-ink">{w.weight_kg} kg</td>
                      <td className="py-2 text-muted">
                        {w.average_daily_gain ? `${w.average_daily_gain} kg/day` : "-"}
                      </td>
                      <td className="py-2 text-muted">{w.notes ?? "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </div>
      )}

      <Modal open={weightModalOpen} onClose={() => setWeightModalOpen(false)} title="Record weight">
        <WeightRecordForm
          error={weightFormError}
          pending={addWeight.isPending}
          onSubmit={(body) => addWeight.mutate(body)}
        />
      </Modal>

      {tab === "Breeding" && (
        <div>
          <div className="mb-4 flex justify-end">
            <Can permission="breeding.create"><Button onClick={() => { setBreedingFormError(null); setBreedingModalOpen(true); }}>
              + Record breeding
            </Button></Can>
          </div>
          {breedingQuery.isLoading && <p className="text-sm text-muted">Loading…</p>}
          {breedingQuery.data && breedingQuery.data.length === 0 && (
            <p className="text-sm text-muted">No breeding records yet.</p>
          )}
          <div className="space-y-4">
            {breedingQuery.data?.map((record) => (
              <Card key={record.id}>
                <div className="mb-2 flex items-center justify-between">
                  <p className="text-sm font-medium capitalize text-ink">
                    {record.method.replace(/_/g, " ")} - {record.mating_date}
                  </p>
                  <StatusBadge status={record.pregnancy_status} />
                </div>
                {record.expected_delivery_date && (
                  <p className="text-xs text-muted">Expected delivery: {record.expected_delivery_date}</p>
                )}
                {record.pregnancy_checks.length > 0 && (
                  <ul className="mt-2 space-y-1 text-xs text-muted">
                    {record.pregnancy_checks.map((c) => (
                      <li key={c.id}>
                        {c.check_date}: <span className="capitalize">{c.result.replace(/_/g, " ")}</span>
                      </li>
                    ))}
                  </ul>
                )}
                <Can permission="breeding.create"><div className="mt-3 flex gap-2">
                  {record.pregnancy_status === "bred" && (
                    <Button
                      variant="ghost"
                      className="px-3 py-1 text-xs"
                      onClick={() => { setCheckFormError(null); setCheckModalRecordId(record.id); }}
                    >
                      + Pregnancy check
                    </Button>
                  )}
                  {record.pregnancy_status === "confirmed_pregnant" && (
                    <Button
                      variant="ghost"
                      className="px-3 py-1 text-xs"
                      onClick={() => { setDeliveryFormError(null); setDeliveryModalRecordId(record.id); }}
                    >
                      Record delivery
                    </Button>
                  )}
                </div></Can>
              </Card>
            ))}
          </div>
        </div>
      )}

      <Modal open={breedingModalOpen} onClose={() => setBreedingModalOpen(false)} title="Record breeding">
        <BreedingForm
          error={breedingFormError}
          pending={createBreeding.isPending}
          onSubmit={(body) => createBreeding.mutate(body)}
        />
      </Modal>

      <Modal open={!!checkModalRecordId} onClose={() => setCheckModalRecordId(null)} title="Add pregnancy check">
        <PregnancyCheckForm
          error={checkFormError}
          pending={addPregnancyCheck.isPending}
          onSubmit={(body) => checkModalRecordId && addPregnancyCheck.mutate({ recordId: checkModalRecordId, body })}
        />
      </Modal>

      <Modal open={!!deliveryModalRecordId} onClose={() => setDeliveryModalRecordId(null)} title="Record delivery">
        <DeliveryForm
          error={deliveryFormError}
          pending={recordDelivery.isPending}
          onSubmit={(body) => deliveryModalRecordId && recordDelivery.mutate({ recordId: deliveryModalRecordId, body })}
        />
      </Modal>

      {tab === "Dairy" && (
        <div>
          <Can permission="dairy.create"><div className="mb-4 flex flex-wrap justify-end gap-2">
            <Button variant="ghost" onClick={() => startLactation.mutate(new Date().toISOString().slice(0, 10))}>
              Start lactation cycle
            </Button>
            <Button variant="ghost" onClick={() => dryOff.mutate(new Date().toISOString().slice(0, 10))}>
              Dry off
            </Button>
            <Button onClick={() => { setMilkFormError(null); setMilkModalOpen(true); }}>+ Record milk</Button>
          </div></Can>
          {dairyActionError && <div className="mb-4"><ErrorState message={dairyActionError} /></div>}
          <Card>
            {milkQuery.isLoading && <p className="text-sm text-muted">Loading…</p>}
            {milkQuery.data && milkQuery.data.length === 0 && <p className="text-sm text-muted">No milk records yet.</p>}
            {milkQuery.data && milkQuery.data.length > 0 && (
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-hairline text-xs uppercase tracking-wider text-muted">
                    <th className="pb-2 font-medium">Date</th>
                    <th className="pb-2 font-medium">Session</th>
                    <th className="pb-2 font-medium">Quantity</th>
                  </tr>
                </thead>
                <tbody>
                  {milkQuery.data.map((m) => (
                    <tr key={m.id} className="border-b border-hairline/60 last:border-0">
                      <td className="py-2">{m.production_date}</td>
                      <td className="py-2 capitalize">{m.session}</td>
                      <td className="py-2 font-medium text-ink">
                        {m.quantity_liters} L {m.rejected && <span className="text-clay">(rejected)</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </div>
      )}

      <Modal open={milkModalOpen} onClose={() => setMilkModalOpen(false)} title="Record milk">
        <MilkRecordForm error={milkFormError} pending={recordMilk.isPending} onSubmit={(body) => recordMilk.mutate(body)} />
      </Modal>

      {tab === "Movements" && (
        <div>
          <div className="mb-4 flex justify-end">
            <Can permission="livestock.update"><Button onClick={() => { setMovementFormError(null); setMovementModalOpen(true); }}>
              + Record movement
            </Button></Can>
          </div>
          <Card>
            {movementsQuery.isLoading && <p className="text-sm text-muted">Loading…</p>}
            {movementsQuery.data && movementsQuery.data.length === 0 && (
              <p className="text-sm text-muted">No movements recorded yet.</p>
            )}
            {movementsQuery.data && movementsQuery.data.length > 0 && (
              <ol className="relative space-y-4 border-l border-hairline pl-6">
                {movementsQuery.data.map((m) => (
                  <li key={m.id} className="relative">
                    <span className="absolute -left-[27px] top-1 h-2.5 w-2.5 rounded-full bg-brass" />
                    <p className="text-sm font-medium text-ink">
                      {m.from_location_id ? "Moved to new location" : "Initial location assigned"}
                    </p>
                    <p className="text-xs text-muted">{new Date(m.moved_at).toLocaleString()}</p>
                    {m.reason && <p className="text-xs text-muted">{m.reason}</p>}
                  </li>
                ))}
              </ol>
            )}
          </Card>
        </div>
      )}

      <Modal open={movementModalOpen} onClose={() => setMovementModalOpen(false)} title="Record movement">
        <MovementForm
          error={movementFormError}
          pending={recordMovement.isPending}
          farms={farmsQuery.data ?? []}
          onSubmit={(body) => recordMovement.mutate(body)}
        />
      </Modal>
    </AdminShell>
  );
}

function HealthRecordForm({
  onSubmit,
  error,
  pending,
}: {
  onSubmit: (body: { record_type: string; title: string; description?: string; cost?: string; follow_up_date?: string }) => void;
  error: string | null;
  pending: boolean;
}) {
  const [recordType, setRecordType] = useState<string>(RECORD_TYPES[0]);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [cost, setCost] = useState("");
  const [followUpDate, setFollowUpDate] = useState("");

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({
          record_type: recordType,
          title,
          description: description || undefined,
          cost: cost || undefined,
          follow_up_date: followUpDate || undefined,
        });
      }}
      className="space-y-3"
    >
      {error && <ErrorState message={error} />}
      <Select id="record_type" label="Type" value={recordType} onChange={(e) => setRecordType(e.target.value)}>
        {RECORD_TYPES.map((t) => (
          <option key={t} value={t}>
            {t.replace(/_/g, " ")}
          </option>
        ))}
      </Select>
      <Input id="title" label="Title" required value={title} onChange={(e) => setTitle(e.target.value)} />
      <Textarea
        id="description"
        label="Description"
        rows={3}
        value={description}
        onChange={(e) => setDescription(e.target.value)}
      />
      <div className="grid grid-cols-2 gap-4">
        <Input id="cost" label="Cost (KES)" type="number" min="0" step="0.01" value={cost} onChange={(e) => setCost(e.target.value)} />
        <Input
          id="follow_up_date"
          label="Follow-up date"
          type="date"
          value={followUpDate}
          onChange={(e) => setFollowUpDate(e.target.value)}
        />
      </div>
      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Saving…" : "Add record"}
      </Button>
    </form>
  );
}

function WeightRecordForm({
  onSubmit,
  error,
  pending,
}: {
  onSubmit: (body: { weight_kg: string; notes?: string }) => void;
  error: string | null;
  pending: boolean;
}) {
  const [weight, setWeight] = useState("");
  const [notes, setNotes] = useState("");

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ weight_kg: weight, notes: notes || undefined });
      }}
      className="space-y-3"
    >
      {error && <ErrorState message={error} />}
      <Input
        id="weight_kg"
        label="Weight (kg)"
        type="number"
        min="0"
        step="0.01"
        required
        value={weight}
        onChange={(e) => setWeight(e.target.value)}
      />
      <Textarea id="weight_notes" label="Notes" rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Saving…" : "Record weight"}
      </Button>
    </form>
  );
}

function BreedingForm({
  onSubmit,
  error,
  pending,
}: {
  onSubmit: (body: { method: string; mating_date: string; expected_delivery_date?: string; sire_external?: string }) => void;
  error: string | null;
  pending: boolean;
}) {
  const [method, setMethod] = useState<"natural" | "artificial_insemination">("natural");
  const [matingDate, setMatingDate] = useState(new Date().toISOString().slice(0, 10));
  const [expectedDelivery, setExpectedDelivery] = useState("");
  const [sireExternal, setSireExternal] = useState("");

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({
          method, mating_date: matingDate,
          expected_delivery_date: expectedDelivery || undefined,
          sire_external: sireExternal || undefined,
        });
      }}
      className="space-y-3"
    >
      {error && <ErrorState message={error} />}
      <Select id="breeding-method" label="Method" value={method} onChange={(e) => setMethod(e.target.value as typeof method)}>
        <option value="natural">Natural</option>
        <option value="artificial_insemination">Artificial insemination</option>
      </Select>
      <Input id="mating-date" label="Mating date" type="date" required value={matingDate} onChange={(e) => setMatingDate(e.target.value)} />
      <Input
        id="expected-delivery"
        label="Expected delivery date"
        type="date"
        value={expectedDelivery}
        onChange={(e) => setExpectedDelivery(e.target.value)}
      />
      <Input
        id="sire-external"
        label="Sire (if off-farm - AI straw/bull ID)"
        value={sireExternal}
        onChange={(e) => setSireExternal(e.target.value)}
      />
      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Saving…" : "Record breeding"}
      </Button>
    </form>
  );
}

function PregnancyCheckForm({
  onSubmit,
  error,
  pending,
}: {
  onSubmit: (body: { check_date: string; result: string }) => void;
  error: string | null;
  pending: boolean;
}) {
  const [checkDate, setCheckDate] = useState(new Date().toISOString().slice(0, 10));
  const [result, setResult] = useState("confirmed");

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ check_date: checkDate, result });
      }}
      className="space-y-3"
    >
      {error && <ErrorState message={error} />}
      <Input id="check-date" label="Check date" type="date" required value={checkDate} onChange={(e) => setCheckDate(e.target.value)} />
      <Select id="check-result" label="Result" value={result} onChange={(e) => setResult(e.target.value)}>
        <option value="confirmed">Confirmed pregnant</option>
        <option value="not_pregnant">Not pregnant</option>
        <option value="inconclusive">Inconclusive</option>
      </Select>
      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Saving…" : "Add check"}
      </Button>
    </form>
  );
}

function DeliveryForm({
  onSubmit,
  error,
  pending,
}: {
  onSubmit: (body: { actual_delivery_date: string; offspring_count: number }) => void;
  error: string | null;
  pending: boolean;
}) {
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [count, setCount] = useState("1");

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ actual_delivery_date: date, offspring_count: Number(count) });
      }}
      className="space-y-3"
    >
      {error && <ErrorState message={error} />}
      <Input id="delivery-date" label="Delivery date" type="date" required value={date} onChange={(e) => setDate(e.target.value)} />
      <Input id="offspring-count" label="Offspring count" type="number" min="0" required value={count} onChange={(e) => setCount(e.target.value)} />
      <p className="text-xs text-muted">Offspring will be automatically registered as new animals, linked to this dam.</p>
      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Saving…" : "Record delivery"}
      </Button>
    </form>
  );
}

function MilkRecordForm({
  onSubmit,
  error,
  pending,
}: {
  onSubmit: (body: { production_date: string; session: string; quantity_liters: string }) => void;
  error: string | null;
  pending: boolean;
}) {
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [session, setSession] = useState("morning");
  const [quantity, setQuantity] = useState("");

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ production_date: date, session, quantity_liters: quantity });
      }}
      className="space-y-3"
    >
      {error && <ErrorState message={error} />}
      <Input id="milk-date" label="Date" type="date" required value={date} onChange={(e) => setDate(e.target.value)} />
      <Select id="milk-session" label="Session" value={session} onChange={(e) => setSession(e.target.value)}>
        <option value="morning">Morning</option>
        <option value="midday">Midday</option>
        <option value="evening">Evening</option>
      </Select>
      <Input
        id="milk-quantity"
        label="Quantity (litres)"
        type="number"
        min="0"
        step="0.01"
        required
        value={quantity}
        onChange={(e) => setQuantity(e.target.value)}
      />
      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Saving…" : "Record milk"}
      </Button>
    </form>
  );
}

function MovementForm({
  onSubmit,
  error,
  pending,
  farms,
}: {
  onSubmit: (body: { to_location_id: string; reason?: string; notes?: string }) => void;
  error: string | null;
  pending: boolean;
  farms: Farm[];
}) {
  const [locationId, setLocationId] = useState("");
  const [reason, setReason] = useState("");
  const allLocations = farms.flatMap((f) =>
    f.branches.flatMap((b) => b.locations.map((l) => ({ ...l, farmName: f.name, branchName: b.name }))),
  );

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ to_location_id: locationId, reason: reason || undefined });
      }}
      className="space-y-3"
    >
      {error && <ErrorState message={error} />}
      {allLocations.length === 0 ? (
        <p className="rounded-md border border-hairline bg-paper px-3 py-2 text-sm text-muted">
          No locations exist yet - add a paddock/barn/pen under Farms first.
        </p>
      ) : (
        <Select id="movement-location" label="New location" required value={locationId} onChange={(e) => setLocationId(e.target.value)}>
          <option value="">Select a location…</option>
          {allLocations.map((l) => (
            <option key={l.id} value={l.id}>
              {l.farmName} - {l.branchName} - {l.name} ({l.location_type.replace(/_/g, " ")})
            </option>
          ))}
        </Select>
      )}
      <Input id="movement-reason" label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Rotational grazing, quarantine, etc." />
      <Button type="submit" disabled={pending || allLocations.length === 0} className="w-full">
        {pending ? "Recording…" : "Record movement"}
      </Button>
    </form>
  );
}

function AnimalQRCode({ animalId }: { animalId: string }) {
  const [imgSrc, setImgSrc] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;
    (async () => {
      try {
        const token = getAccessToken();
        const resp = await fetch(`${API_BASE}/api/v1/livestock/${animalId}/qrcode.svg`, {
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        });
        if (!resp.ok) throw new Error("Failed to load QR code");
        const blob = await resp.blob();
        objectUrl = URL.createObjectURL(blob);
        if (!cancelled) setImgSrc(objectUrl);
      } catch {
        if (!cancelled) setError("QR code unavailable");
      }
    })();
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [animalId]);

  return (
    <Card>
      <h2 className="mb-3 font-display text-lg text-forest">QR code</h2>
      <p className="mb-3 text-xs text-muted">
        Print this on a tag - scanning it opens the animal's public profile (species, breed, availability;
        never acquisition cost or internal notes).
      </p>
      {error && <ErrorState message={error} />}
      {!imgSrc && !error && <p className="text-sm text-muted">Loading…</p>}
      {imgSrc && (
        <div className="flex flex-col items-start gap-3">
          {/* eslint-disable-next-line @next/next/no-img-element -- fetched
              via authenticated blob URL, not a static/optimizable asset */}
          <img src={imgSrc} alt="Animal QR code" className="h-32 w-32 border border-hairline bg-white p-2" />
          <Button
            variant="ghost"
            className="text-xs"
            onClick={async () => {
              try {
                await apiDownload(`/api/v1/livestock/${animalId}/qrcode.svg`, `animal-${animalId}-qrcode.svg`);
                setDownloadError(null);
              } catch {
                setDownloadError("Download failed");
              }
            }}
          >
            Download SVG
          </Button>
          {downloadError && <ErrorState message={downloadError} />}
        </div>
      )}
    </Card>
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
