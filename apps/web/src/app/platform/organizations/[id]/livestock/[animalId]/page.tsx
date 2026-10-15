"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { PlatformShell } from "@/components/platform-shell";
import { PlatformEditModal } from "@/components/platform-resource-browser";
import { Button, Card, ErrorState, EmptyState, StatusBadge } from "@/components/ui";
import { platformApiFetch, PlatformApiError } from "@/lib/platform-api";
import { getModuleConfig } from "@/lib/platform-modules";
import { usePlatformMe } from "@/lib/use-platform-auth";

/** The animal's editable details, shown on the page so a saved edit is visible straight away. */
const DETAIL_FIELDS: { key: string; label: string; money?: boolean }[] = [
  { key: "name", label: "Name" },
  { key: "ear_tag", label: "Ear tag" },
  { key: "rfid", label: "RFID" },
  { key: "breed", label: "Breed" },
  { key: "category", label: "Category" },
  { key: "health_status", label: "Health status" },
  { key: "reproductive_status", label: "Reproductive status" },
  { key: "current_value", label: "Current value", money: true },
  { key: "expected_sale_price", label: "Expected sale price", money: true },
  { key: "target_weight", label: "Target weight (kg)" },
  { key: "notes", label: "Notes" },
];

const showDetail = (value: unknown, money?: boolean) => {
  if (value === null || value === undefined || value === "") return <span className="text-muted">-</span>;
  return money ? `KES ${Number(value).toLocaleString("en-US", { maximumFractionDigits: 2 })}` : String(value);
};

/** Health, breeding, and dairy records are per-animal in the API (see
 * platform-modules.ts's comment on why they're not in the generic
 * per-org module browser) - this page is the actual fix for that: land
 * here from a livestock row (rowHref in platform-modules.ts's livestock
 * entry) and see all three histories for that one animal. The histories
 * are read-only - they're workflow-driven records (a pregnancy check, a
 * delivery, a milk session) rather than simple edit-in-place data, so a
 * generic form doesn't fit - but the animal itself can be edited here with
 * the same form as the list (superadmins only). */
export default function AnimalDetailPage() {
  const { id: orgId, animalId } = useParams<{ id: string; animalId: string }>();
  const [tab, setTab] = useState<"health" | "breeding" | "dairy">("health");
  const [editing, setEditing] = useState(false);
  const queryClient = useQueryClient();
  const { data: me } = usePlatformMe();
  const canWrite = me?.role === "superadmin"; // same rule as the module lists: viewers can look, not edit
  const livestockConfig = getModuleConfig("livestock")!;

  const animalQuery = useQuery<Record<string, unknown>>({
    queryKey: ["platform-animal", orgId, animalId],
    queryFn: () => platformApiFetch<Record<string, unknown>>(`/api/v1/platform/organizations/${orgId}/livestock/${animalId}`),
  });

  const healthQuery = useQuery<Record<string, unknown>[]>({
    queryKey: ["platform-animal-health", orgId, animalId],
    queryFn: () => platformApiFetch<Record<string, unknown>[]>(`/api/v1/platform/organizations/${orgId}/livestock/${animalId}/health`),
    enabled: tab === "health",
  });

  const breedingQuery = useQuery<Record<string, unknown>[]>({
    queryKey: ["platform-animal-breeding", orgId, animalId],
    queryFn: () => platformApiFetch<Record<string, unknown>[]>(`/api/v1/platform/organizations/${orgId}/livestock/${animalId}/breeding`),
    enabled: tab === "breeding",
  });

  const dairyQuery = useQuery<Record<string, unknown>[]>({
    queryKey: ["platform-animal-dairy", orgId, animalId],
    queryFn: () => platformApiFetch<Record<string, unknown>[]>(`/api/v1/platform/organizations/${orgId}/livestock/${animalId}/milk-records`),
    enabled: tab === "dairy",
  });

  const animal = animalQuery.data;

  return (
    <PlatformShell>
      <div className="mb-1 flex items-center gap-2 text-sm text-muted">
        <Link href="/platform/organizations" className="hover:underline">Organizations</Link>
        <span>/</span>
        <Link href={`/platform/organizations/${orgId}`} className="hover:underline">Overview</Link>
        <span>/</span>
        <Link href={`/platform/organizations/${orgId}/livestock`} className="hover:underline">Livestock</Link>
      </div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h1 className="font-display text-2xl text-forest">
          {animal ? `${animal.animal_number} - ${animal.breed ?? animal.species}` : "Animal"}
        </h1>
        {canWrite && animal && <Button onClick={() => setEditing(true)}>Edit</Button>}
      </div>

      {animalQuery.error && (
        <ErrorState message={animalQuery.error instanceof PlatformApiError ? animalQuery.error.message : "Failed to load animal"} />
      )}

      {animal && (
        <Card className="mb-6">
          <div className="flex flex-wrap gap-6 text-sm">
            <span><span className="text-muted">Species:</span> {String(animal.species)}</span>
            <span><span className="text-muted">Sex:</span> {String(animal.sex)}</span>
            <span><span className="text-muted">Status:</span> <StatusBadge status={String(animal.status)} /></span>
          </div>
          <dl className="mt-4 grid grid-cols-1 gap-x-8 gap-y-3 border-t border-hairline pt-4 text-sm sm:grid-cols-2 lg:grid-cols-3">
            {DETAIL_FIELDS.map((f) => (
              <div key={f.key} className={f.key === "notes" ? "sm:col-span-2 lg:col-span-3" : undefined}>
                <dt className="text-xs uppercase tracking-wider text-muted">{f.label}</dt>
                <dd className="mt-0.5 whitespace-pre-wrap text-ink">{showDetail(animal[f.key], f.money)}</dd>
              </div>
            ))}
          </dl>
        </Card>
      )}

      <PlatformEditModal
        orgId={orgId}
        config={livestockConfig}
        record={editing && animal ? animal : null}
        onClose={() => setEditing(false)}
        onSaved={() => {
          // refresh this page and the livestock list it came from
          queryClient.invalidateQueries({ queryKey: ["platform-animal", orgId, animalId] });
          queryClient.invalidateQueries({ queryKey: ["platform-resource", "livestock", orgId] });
        }}
      />

      <div className="mb-6 flex gap-1 border-b border-hairline">
        {(["health", "breeding", "dairy"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={
              "rounded-t-md px-3 py-2 text-sm capitalize " +
              (tab === t ? "bg-white/70 font-medium text-forest" : "text-muted hover:bg-white/40")
            }
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "health" && <HealthTab query={healthQuery} />}
      {tab === "breeding" && <BreedingTab query={breedingQuery} />}
      {tab === "dairy" && <DairyTab query={dairyQuery} />}
    </PlatformShell>
  );
}

function HealthTab({ query }: { query: ReturnType<typeof useQuery<Record<string, unknown>[]>> }) {
  if (query.error) return <ErrorState message={query.error instanceof PlatformApiError ? query.error.message : "Failed to load"} />;
  if (query.data && query.data.length === 0) return <EmptyState title="No health records" body="Nothing recorded for this animal yet." />;
  if (!query.data) return <p className="text-sm text-muted">Loading…</p>;
  return (
    <div className="space-y-3">
      {query.data.map((r) => (
        <Card key={String(r.id)}>
          <div className="flex items-center justify-between">
            <p className="font-medium text-ink">{String(r.title)}</p>
            <StatusBadge status={String(r.record_type)} />
          </div>
          <p className="mt-1 text-xs text-muted">{new Date(String(r.performed_at)).toLocaleString()}</p>
          {typeof r.diagnosis === "string" && r.diagnosis && <p className="mt-2 text-sm">Diagnosis: {r.diagnosis}</p>}
          {typeof r.medication === "string" && r.medication && (
            <p className="text-sm text-muted">Medication: {r.medication} {typeof r.dosage === "string" ? `(${r.dosage})` : ""}</p>
          )}
        </Card>
      ))}
    </div>
  );
}

function BreedingTab({ query }: { query: ReturnType<typeof useQuery<Record<string, unknown>[]>> }) {
  if (query.error) return <ErrorState message={query.error instanceof PlatformApiError ? query.error.message : "Failed to load"} />;
  if (query.data && query.data.length === 0) return <EmptyState title="No breeding records" body="Nothing recorded for this animal yet." />;
  if (!query.data) return <p className="text-sm text-muted">Loading…</p>;
  return (
    <div className="space-y-3">
      {query.data.map((r) => (
        <Card key={String(r.id)}>
          <div className="flex items-center justify-between">
            <p className="font-medium text-ink capitalize">{String(r.method)} - mated {new Date(String(r.mating_date)).toLocaleDateString()}</p>
            <StatusBadge status={String(r.pregnancy_status)} />
          </div>
          {typeof r.expected_delivery_date === "string" && (
            <p className="mt-1 text-sm text-muted">Expected delivery: {new Date(r.expected_delivery_date).toLocaleDateString()}</p>
          )}
          {typeof r.actual_delivery_date === "string" && r.actual_delivery_date && (
            <p className="text-sm">
              Delivered {new Date(r.actual_delivery_date).toLocaleDateString()}
              {typeof r.offspring_count === "number" ? ` - ${r.offspring_count} offspring` : ""}
            </p>
          )}
        </Card>
      ))}
    </div>
  );
}

function DairyTab({ query }: { query: ReturnType<typeof useQuery<Record<string, unknown>[]>> }) {
  if (query.error) return <ErrorState message={query.error instanceof PlatformApiError ? query.error.message : "Failed to load"} />;
  if (query.data && query.data.length === 0) return <EmptyState title="No milk records" body="Nothing recorded for this animal yet." />;
  if (!query.data) return <p className="text-sm text-muted">Loading…</p>;
  return (
    <div className="overflow-hidden rounded-lg border border-hairline">
      <table className="w-full text-left text-sm">
        <thead className="bg-ink text-paper">
          <tr>
            <th className="px-4 py-3 font-medium">Date</th>
            <th className="px-4 py-3 font-medium">Session</th>
            <th className="px-4 py-3 font-medium">Quantity (L)</th>
            <th className="px-4 py-3 font-medium">Rejected</th>
          </tr>
        </thead>
        <tbody>
          {query.data.map((r, i) => (
            <tr key={String(r.id)} className={i % 2 === 0 ? "bg-white/40" : "bg-white/70"}>
              <td className="px-4 py-3">{new Date(String(r.production_date)).toLocaleDateString()}</td>
              <td className="px-4 py-3 capitalize">{String(r.session)}</td>
              <td className="px-4 py-3">{String(r.quantity_liters)}</td>
              <td className="px-4 py-3">{r.rejected ? "Yes" : "No"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
