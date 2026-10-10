"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { clsx } from "clsx";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { PlatformShell } from "@/components/platform-shell";
import { Card, Button, ErrorState } from "@/components/ui";
import { platformApiFetch, PlatformApiError } from "@/lib/platform-api";
import { usePlatformMe } from "@/lib/use-platform-auth";
import type {
  OrganizationSummaryOut,
  TenantCatalogSettings,
  TenantCatalogSettingsUpdate,
} from "@/lib/platform-types";
import type { SpeciesCatalogEntry, CropTypeCatalogEntry } from "@/lib/types";

/* ------------------------------------------------------------------ draft state */

interface Draft {
  livestockEnabled: boolean;
  cropsEnabled: boolean;
  restrictSpecies: boolean; // false = every species (the API's null)
  species: string[];
  restrictCrops: boolean;
  cropTypes: string[];
}

function toDraft(s: TenantCatalogSettings): Draft {
  return {
    livestockEnabled: s.livestock_enabled,
    cropsEnabled: s.crops_enabled,
    restrictSpecies: s.enabled_species !== null,
    species: s.enabled_species ?? [],
    restrictCrops: s.enabled_crop_types !== null,
    cropTypes: s.enabled_crop_types ?? [],
  };
}

const sameSet = (a: string[], b: string[]) => a.length === b.length && a.every((x) => b.includes(x));

/** Only what actually changed, in the API's PATCH vocabulary (null = nothing to save). */
function buildPatch(d: Draft, s: TenantCatalogSettings, order: { species: string[]; crops: string[] }): TenantCatalogSettingsUpdate | null {
  const body: TenantCatalogSettingsUpdate = {};
  if (d.livestockEnabled !== s.livestock_enabled) body.livestock_enabled = d.livestockEnabled;
  if (d.cropsEnabled !== s.crops_enabled) body.crops_enabled = d.cropsEnabled;

  if (!d.restrictSpecies) {
    if (s.enabled_species !== null) body.clear_species_restriction = true;
  } else if (s.enabled_species === null || !sameSet(d.species, s.enabled_species)) {
    body.enabled_species = order.species.filter((c) => d.species.includes(c));
  }

  if (!d.restrictCrops) {
    if (s.enabled_crop_types !== null) body.clear_crop_type_restriction = true;
  } else if (s.enabled_crop_types === null || !sameSet(d.cropTypes, s.enabled_crop_types)) {
    body.enabled_crop_types = order.crops.filter((c) => d.cropTypes.includes(c));
  }
  return Object.keys(body).length ? body : null;
}

const CROP_CATEGORY_LABELS: Record<string, string> = {
  cash_crop: "Cash crops",
  cereal: "Cereals",
  flower: "Flowers",
  fodder: "Fodder",
  horticulture: "Horticulture",
  legume: "Legumes",
  root_tuber: "Roots & tubers",
};
const categoryLabel = (c: string) => CROP_CATEGORY_LABELS[c] ?? c.replace(/_/g, " ");

/* ------------------------------------------------------------------ small controls */

function Switch({ checked, onChange, disabled, label }: { checked: boolean; onChange: (v: boolean) => void; disabled?: boolean; label: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={clsx(
        "relative inline-flex h-6 w-11 shrink-0 items-center rounded-full border transition-colors",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-brass focus-visible:ring-offset-2 focus-visible:ring-offset-paper",
        "disabled:cursor-not-allowed disabled:opacity-50",
        checked ? "border-forest bg-forest" : "border-hairline bg-hairline",
      )}
    >
      <span
        className={clsx(
          "inline-block h-4 w-4 rounded-full bg-paper shadow transition-transform",
          checked ? "translate-x-6" : "translate-x-1",
        )}
      />
    </button>
  );
}

function CheckTile({ checked, onChange, disabled, title, hint }: { checked: boolean; onChange: () => void; disabled?: boolean; title: string; hint?: string }) {
  return (
    <label
      className={clsx(
        "flex cursor-pointer items-start gap-2.5 rounded-md border px-3 py-2 text-sm transition-colors",
        checked ? "border-forest/60 bg-forest/5" : "border-hairline bg-white/50 hover:bg-white",
        disabled && "cursor-not-allowed opacity-60",
      )}
    >
      <input type="checkbox" className="mt-0.5 accent-forest" checked={checked} onChange={onChange} disabled={disabled} />
      <span>
        <span className="block text-ink">{title}</span>
        {hint && <span className="block text-xs text-muted">{hint}</span>}
      </span>
    </label>
  );
}

function ScopeChoice({
  name, restricted, onChange, disabled, allLabel, someLabel,
}: { name: string; restricted: boolean; onChange: (restricted: boolean) => void; disabled?: boolean; allLabel: string; someLabel: string }) {
  const option = (value: boolean, label: string) => (
    <label className={clsx("flex cursor-pointer items-center gap-2 text-sm", disabled && "cursor-not-allowed opacity-60")}>
      <input type="radio" name={name} className="accent-forest" checked={restricted === value} onChange={() => onChange(value)} disabled={disabled} />
      {label}
    </label>
  );
  return (
    <fieldset className="flex flex-wrap gap-x-6 gap-y-2">
      <legend className="sr-only">Which options this organization can use</legend>
      {option(false, allLabel)}
      {option(true, someLabel)}
    </fieldset>
  );
}

function ModuleCard({
  title, blurb, enabled, onEnabledChange, readOnly, offNote, children,
}: { title: string; blurb: string; enabled: boolean; onEnabledChange: (v: boolean) => void; readOnly: boolean; offNote: string; children: React.ReactNode }) {
  return (
    <Card>
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="font-display text-xl text-forest">{title}</h2>
          <p className="mt-0.5 text-sm text-muted">{blurb}</p>
        </div>
        <div className="flex items-center gap-2">
          <span className={clsx("text-sm", enabled ? "text-moss" : "text-muted")}>{enabled ? "On" : "Off"}</span>
          <Switch checked={enabled} onChange={onEnabledChange} disabled={readOnly} label={`${title} module`} />
        </div>
      </div>
      <div className="mt-5 border-t border-hairline pt-5">
        {enabled ? children : <p className="text-sm text-muted">{offNote}</p>}
      </div>
    </Card>
  );
}

/* ------------------------------------------------------------------ page */

export default function OrganizationCatalogPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const { data: me } = usePlatformMe();
  const canWrite = me?.role === "superadmin";

  const orgQuery = useQuery<OrganizationSummaryOut>({
    queryKey: ["platform-organization", id],
    queryFn: () => platformApiFetch<OrganizationSummaryOut>(`/api/v1/platform/organizations/${id}`),
  });
  const settingsQuery = useQuery<TenantCatalogSettings>({
    queryKey: ["platform-catalog-settings", id],
    queryFn: () => platformApiFetch<TenantCatalogSettings>(`/api/v1/platform/organizations/${id}/catalog-settings`),
  });
  const speciesQuery = useQuery<SpeciesCatalogEntry[]>({
    queryKey: ["platform-catalog-species"],
    queryFn: () => platformApiFetch<SpeciesCatalogEntry[]>("/api/v1/platform/catalog/species"),
    staleTime: 5 * 60_000,
  });
  const cropsQuery = useQuery<CropTypeCatalogEntry[]>({
    queryKey: ["platform-catalog-crop-types"],
    queryFn: () => platformApiFetch<CropTypeCatalogEntry[]>("/api/v1/platform/catalog/crop-types"),
    staleTime: 5 * 60_000,
  });

  const [draft, setDraft] = useState<Draft | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [cropFilter, setCropFilter] = useState("");

  // Seed the editable draft once the server copy arrives; after that the draft is the user's.
  useEffect(() => {
    if (settingsQuery.data && draft === null) setDraft(toDraft(settingsQuery.data));
  }, [settingsQuery.data, draft]);

  const species = speciesQuery.data ?? [];
  const cropTypes = cropsQuery.data ?? [];
  const server = settingsQuery.data;

  const patch = useMemo(
    () => (draft && server ? buildPatch(draft, server, { species: species.map((s) => s.code), crops: cropTypes.map((c) => c.code) }) : null),
    [draft, server, species, cropTypes],
  );
  const dirty = patch !== null;

  const speciesEmpty = !!draft && draft.livestockEnabled && draft.restrictSpecies && draft.species.length === 0;
  const cropsEmpty = !!draft && draft.cropsEnabled && draft.restrictCrops && draft.cropTypes.length === 0;
  const invalid = speciesEmpty || cropsEmpty;

  // Don't let a stray tab-close throw away unsaved edits.
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const save = useMutation({
    mutationFn: (body: TenantCatalogSettingsUpdate) =>
      platformApiFetch<TenantCatalogSettings>(`/api/v1/platform/organizations/${id}/catalog-settings`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["platform-catalog-settings", id], updated);
      setDraft(toDraft(updated));
      setError(null);
      setSavedAt(Date.now());
    },
    onError: (err) => setError(err instanceof PlatformApiError ? err.message : "Failed to save catalog settings"),
  });

  const update = (changes: Partial<Draft>) => {
    setDraft((d) => (d ? { ...d, ...changes } : d));
    setSavedAt(null);
  };
  const toggleIn = (list: string[], code: string) => (list.includes(code) ? list.filter((c) => c !== code) : [...list, code]);

  const loadError = orgQuery.error ?? settingsQuery.error ?? speciesQuery.error ?? cropsQuery.error;
  if (loadError) {
    return (
      <PlatformShell>
        <ErrorState message={loadError instanceof PlatformApiError ? loadError.message : "Failed to load catalog settings"} />
      </PlatformShell>
    );
  }
  if (!orgQuery.data || !server || !draft || !speciesQuery.data || !cropsQuery.data) {
    return (
      <PlatformShell>
        <p className="text-sm text-muted">Loading…</p>
      </PlatformShell>
    );
  }

  const org = orgQuery.data;
  const readOnly = !canWrite;

  const filter = cropFilter.trim().toLowerCase();
  const visibleCrops = filter
    ? cropTypes.filter((c) => c.label.toLowerCase().includes(filter) || categoryLabel(c.category).toLowerCase().includes(filter))
    : cropTypes;
  const cropGroups = visibleCrops.reduce<Record<string, CropTypeCatalogEntry[]>>((acc, c) => {
    (acc[c.category] ??= []).push(c);
    return acc;
  }, {});

  const setGroup = (codes: string[], on: boolean) =>
    update({ cropTypes: on ? Array.from(new Set([...draft.cropTypes, ...codes])) : draft.cropTypes.filter((c) => !codes.includes(c)) });

  return (
    <PlatformShell>
      <Link href={`/platform/organizations/${org.id}`} className="text-sm text-muted hover:text-forest">
        ← {org.name}
      </Link>
      <div className="mb-6 mt-2">
        <h1 className="font-display text-2xl text-forest">Products &amp; catalog</h1>
        <p className="max-w-2xl text-sm text-muted">
          Choose what {org.name} can deal in. This limits what they can register from now on; animals and
          plantings they already have are never changed or hidden.
        </p>
      </div>

      {readOnly && (
        <div className="mb-4 rounded-lg border border-hairline bg-white/60 px-4 py-3 text-sm text-muted">
          You have view-only access. Only a superadmin can change these settings.
        </div>
      )}
      {error && <div className="mb-4"><ErrorState message={error} /></div>}

      <div className="max-w-4xl space-y-6">
        {/* ---------------------------------------------------------------- livestock */}
        <ModuleCard
          title="Livestock"
          blurb="Animal registration, health, breeding, dairy and herd listings."
          enabled={draft.livestockEnabled}
          onEnabledChange={(v) => update({ livestockEnabled: v })}
          readOnly={readOnly}
          offNote="Livestock is off: it disappears from this organization's sidebar and they can't register animals. Existing records stay viewable."
        >
          <ScopeChoice
            name="species-scope"
            restricted={draft.restrictSpecies}
            onChange={(v) => update({ restrictSpecies: v })}
            disabled={readOnly}
            allLabel={`All species (${species.length})`}
            someLabel="Only selected species"
          />
          {draft.restrictSpecies && (
            <div className="mt-4">
              <div className="mb-2 flex items-center justify-between text-xs text-muted">
                <span>{draft.species.length} of {species.length} selected</span>
                {!readOnly && (
                  <span className="space-x-3">
                    <button type="button" className="hover:text-forest" onClick={() => update({ species: species.map((s) => s.code) })}>Select all</button>
                    <button type="button" className="hover:text-forest" onClick={() => update({ species: [] })}>Clear</button>
                  </span>
                )}
              </div>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {species.map((s) => (
                  <CheckTile
                    key={s.code}
                    title={s.label}
                    hint={s.suggested_categories.map((c) => c.replace(/_/g, " ")).join(", ")}
                    checked={draft.species.includes(s.code)}
                    onChange={() => update({ species: toggleIn(draft.species, s.code) })}
                    disabled={readOnly}
                  />
                ))}
              </div>
              {speciesEmpty && (
                <p className="mt-3 text-sm text-clay">Select at least one species, or choose &ldquo;All species&rdquo; - or switch Livestock off.</p>
              )}
            </div>
          )}
        </ModuleCard>

        {/* ---------------------------------------------------------------- crops */}
        <ModuleCard
          title="Crops"
          blurb="Plantings, harvests, field activity and produce listings."
          enabled={draft.cropsEnabled}
          onEnabledChange={(v) => update({ cropsEnabled: v })}
          readOnly={readOnly}
          offNote="Crops is off: it disappears from this organization's sidebar and they can't register plantings. Existing records stay viewable."
        >
          <ScopeChoice
            name="crop-scope"
            restricted={draft.restrictCrops}
            onChange={(v) => update({ restrictCrops: v })}
            disabled={readOnly}
            allLabel={`All crop types (${cropTypes.length})`}
            someLabel="Only selected crop types"
          />
          {draft.restrictCrops && (
            <div className="mt-4">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <input
                  type="search"
                  value={cropFilter}
                  onChange={(e) => setCropFilter(e.target.value)}
                  placeholder="Find a crop type…"
                  aria-label="Find a crop type"
                  className="w-full rounded-md border border-hairline bg-white/70 px-3 py-1.5 text-sm outline-none focus:border-forest sm:w-64"
                />
                <div className="flex items-center gap-3 text-xs text-muted">
                  <span>{draft.cropTypes.length} of {cropTypes.length} selected</span>
                  {!readOnly && (
                    <>
                      <button type="button" className="hover:text-forest" onClick={() => update({ cropTypes: cropTypes.map((c) => c.code) })}>Select all</button>
                      <button type="button" className="hover:text-forest" onClick={() => update({ cropTypes: [] })}>Clear</button>
                    </>
                  )}
                </div>
              </div>

              {Object.keys(cropGroups).length === 0 && <p className="text-sm text-muted">No crop types match &ldquo;{cropFilter}&rdquo;.</p>}
              <div className="space-y-5">
                {Object.entries(cropGroups).map(([category, items]) => {
                  const codes = items.map((c) => c.code);
                  const picked = codes.filter((c) => draft.cropTypes.includes(c)).length;
                  return (
                    <section key={category} aria-label={categoryLabel(category)}>
                      <div className="mb-1.5 flex items-center justify-between">
                        <h3 className="text-sm font-medium text-ink">
                          {categoryLabel(category)} <span className="font-normal text-muted">({picked}/{items.length})</span>
                        </h3>
                        {!readOnly && (
                          <button
                            type="button"
                            className="text-xs text-muted hover:text-forest"
                            onClick={() => setGroup(codes, picked !== items.length)}
                          >
                            {picked === items.length ? "Clear group" : "Select group"}
                          </button>
                        )}
                      </div>
                      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                        {items.map((c) => (
                          <CheckTile
                            key={c.code}
                            title={c.label}
                            hint={c.is_perennial ? "Perennial" : undefined}
                            checked={draft.cropTypes.includes(c.code)}
                            onChange={() => update({ cropTypes: toggleIn(draft.cropTypes, c.code) })}
                            disabled={readOnly}
                          />
                        ))}
                      </div>
                    </section>
                  );
                })}
              </div>
              {cropsEmpty && (
                <p className="mt-3 text-sm text-clay">Select at least one crop type, or choose &ldquo;All crop types&rdquo; - or switch Crops off.</p>
              )}
            </div>
          )}
        </ModuleCard>
      </div>

      {/* ---------------------------------------------------------------- save bar */}
      {!readOnly && (
        <div className="sticky bottom-4 mt-6 max-w-4xl">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-hairline bg-white px-4 py-3 shadow-sm">
            <p className="text-sm" aria-live="polite">
              {invalid ? (
                <span className="text-clay">Fix the highlighted selection before saving.</span>
              ) : dirty ? (
                <span className="text-ink">You have unsaved changes.</span>
              ) : savedAt ? (
                <span className="text-moss">Saved. The change applies to {org.name} immediately.</span>
              ) : (
                <span className="text-muted">No changes.</span>
              )}
            </p>
            <div className="flex gap-2">
              <Button
                variant="ghost"
                disabled={!dirty || save.isPending}
                onClick={() => { setDraft(toDraft(server)); setError(null); }}
              >
                Discard
              </Button>
              <Button disabled={!dirty || invalid || save.isPending} onClick={() => patch && save.mutate(patch)}>
                {save.isPending ? "Saving…" : "Save changes"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </PlatformShell>
  );
}
