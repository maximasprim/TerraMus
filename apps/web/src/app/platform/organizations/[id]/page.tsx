"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { PlatformShell } from "@/components/platform-shell";
import { Card, Button, ErrorState } from "@/components/ui";
import { platformApiFetch, PlatformApiError } from "@/lib/platform-api";
import { usePlatformMe } from "@/lib/use-platform-auth";
import { PLATFORM_MODULES } from "@/lib/platform-modules";
import type { OrganizationSummaryOut, PlatformPlan, TenantCatalogSettings } from "@/lib/platform-types";

/** "Livestock: 3 species" / "Livestock: all species" / "Livestock: off". */
function catalogSummary(module: string, enabled: boolean, list: string[] | null, noun: string): string {
  if (!enabled) return `${module}: off`;
  if (list === null) return `${module}: all ${noun}`;
  return `${module}: ${list.length} ${noun}`;
}

export default function OrganizationDetailPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const { data: me } = usePlatformMe();
  const canWrite = me?.role === "superadmin";
  const [error, setError] = useState<string | null>(null);

  const orgQuery = useQuery<OrganizationSummaryOut>({
    queryKey: ["platform-organization", id],
    queryFn: () => platformApiFetch<OrganizationSummaryOut>(`/api/v1/platform/organizations/${id}`),
  });

  // Shares its cache key with the catalog page, so opening that page afterwards is instant.
  const catalogQuery = useQuery<TenantCatalogSettings>({
    queryKey: ["platform-catalog-settings", id],
    queryFn: () => platformApiFetch<TenantCatalogSettings>(`/api/v1/platform/organizations/${id}/catalog-settings`),
  });

  // Plan management (superadmin): choose a plan, status and optional period end, then save - no payment involved.
  const plansQuery = useQuery<PlatformPlan[]>({
    queryKey: ["platform-plans"],
    queryFn: () => platformApiFetch<PlatformPlan[]>("/api/v1/platform/billing/tiers"),
  });
  const [planSlug, setPlanSlug] = useState("");
  const [planStatus, setPlanStatus] = useState("active");
  const [planEnd, setPlanEnd] = useState("");
  const [planMsg, setPlanMsg] = useState<string | null>(null);
  const changePlan = useMutation({
    mutationFn: () =>
      platformApiFetch<OrganizationSummaryOut>(`/api/v1/platform/organizations/${id}/subscription`, {
        method: "PATCH",
        body: JSON.stringify({
          tier_slug: planSlug,
          status: planStatus,
          current_period_end: planEnd ? new Date(`${planEnd}T23:59:59`).toISOString() : null,
        }),
      }),
    onSuccess: (o) => {
      queryClient.invalidateQueries({ queryKey: ["platform-organization", id] });
      queryClient.invalidateQueries({ queryKey: ["platform-organizations"] });
      queryClient.invalidateQueries({ queryKey: ["platform-dashboard"] });
      setError(null);
      setPlanMsg(`Plan set to ${o.subscription_tier} (${o.subscription_status}).`);
    },
    onError: (err) => {
      setPlanMsg(null);
      setError(err instanceof PlatformApiError ? err.message : "Failed to change plan");
    },
  });

  const toggleSuspend = useMutation({
    mutationFn: (isSuspended: boolean) =>
      platformApiFetch(`/api/v1/platform/organizations/${id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ is_suspended: isSuspended }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["platform-organization", id] });
      queryClient.invalidateQueries({ queryKey: ["platform-organizations"] });
      setError(null);
    },
    onError: (err) => setError(err instanceof PlatformApiError ? err.message : "Failed to update organization"),
  });

  if (orgQuery.error) {
    return (
      <PlatformShell>
        <ErrorState message={orgQuery.error instanceof PlatformApiError ? orgQuery.error.message : "Failed to load organization"} />
      </PlatformShell>
    );
  }
  if (!orgQuery.data) {
    return (
      <PlatformShell>
        <p className="text-sm text-muted">Loading…</p>
      </PlatformShell>
    );
  }

  const org = orgQuery.data;

  return (
    <PlatformShell>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl text-forest">{org.name}</h1>
          <p className="text-sm text-muted">{org.slug} · {org.currency}</p>
        </div>
        {canWrite && (
          <Button
            variant={org.is_suspended ? "primary" : "ghost"}
            disabled={toggleSuspend.isPending}
            onClick={() => toggleSuspend.mutate(!org.is_suspended)}
          >
            {org.is_suspended ? "Reactivate organization" : "Suspend organization"}
          </Button>
        )}
      </div>

      {error && <div className="mb-4"><ErrorState message={error} /></div>}

      {org.is_suspended && (
        <div className="mb-6 rounded-lg border border-clay/30 bg-clay/5 px-4 py-3 text-sm text-clay">
          This organization is suspended. Its users cannot log in or make any API requests until reactivated.
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <Card>
          <p className="text-xs font-medium uppercase tracking-wider text-muted">Users</p>
          <p className="font-display text-2xl text-forest">{org.user_count}</p>
        </Card>
        <Card>
          <p className="text-xs font-medium uppercase tracking-wider text-muted">Subscription tier</p>
          <p className="font-display text-2xl text-forest">{org.subscription_tier ?? "-"}</p>
        </Card>
        <Card>
          <p className="text-xs font-medium uppercase tracking-wider text-muted">Subscription status</p>
          <p className="font-display text-2xl text-forest capitalize">{org.subscription_status ?? "-"}</p>
        </Card>
      </div>

      {canWrite && (
        <Card>
          <p className="text-xs font-medium uppercase tracking-wider text-muted">Change plan</p>
          <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-4">
            <label className="text-sm">
              <span className="mb-1 block text-muted">Plan</span>
              <select
                value={planSlug || org.subscription_tier_slug || ""}
                onChange={(e) => { setPlanSlug(e.target.value); setPlanMsg(null); }}
                className="block w-full rounded-md border border-hairline bg-white px-2 py-1.5 text-sm"
              >
                {!(planSlug || org.subscription_tier_slug) && <option value="" disabled>Choose a plan…</option>}
                {(plansQuery.data ?? []).map((p) => (
                  <option key={p.slug} value={p.slug}>
                    {p.name} - KES {Number(p.monthly_price_kes).toLocaleString()}/mo · {p.max_animals ?? "unlimited"} animals · {p.max_users ?? "unlimited"} users
                  </option>
                ))}
              </select>
            </label>
            <label className="text-sm">
              <span className="mb-1 block text-muted">Status</span>
              <select
                value={planStatus}
                onChange={(e) => setPlanStatus(e.target.value)}
                className="block w-full rounded-md border border-hairline bg-white px-2 py-1.5 text-sm"
              >
                <option value="active">Active</option>
                <option value="trialing">Trialing</option>
                <option value="past_due">Past due</option>
                <option value="cancelled">Cancelled</option>
              </select>
            </label>
            <label className="text-sm">
              <span className="mb-1 block text-muted">Period ends (optional)</span>
              <input
                type="date"
                value={planEnd}
                onChange={(e) => setPlanEnd(e.target.value)}
                className="block w-full rounded-md border border-hairline bg-white px-2 py-1.5 text-sm"
              />
            </label>
            <div className="flex items-end">
              <Button
                disabled={changePlan.isPending || !(planSlug || org.subscription_tier_slug)}
                onClick={() => { if (!planSlug && org.subscription_tier_slug) setPlanSlug(org.subscription_tier_slug); changePlan.mutate(); }}
              >
                {changePlan.isPending ? "Saving…" : "Save plan"}
              </Button>
            </div>
          </div>
          <p className="mt-2 text-xs text-muted">
            Takes effect immediately, with no payment. If the period has already ended it is extended by 30 days. A plan the
            organization already exceeds (users or animals) is refused.
            {org.subscription_period_end ? ` Current period ends ${new Date(org.subscription_period_end).toLocaleDateString()}.` : ""}
          </p>
          {planMsg && <p className="mt-2 text-sm text-forest">{planMsg}</p>}
        </Card>
      )}

      <Link
        href={`/platform/organizations/${org.id}/catalog`}
        className="mt-4 flex items-center justify-between gap-4 rounded-lg border border-hairline bg-white/60 p-6 transition-colors hover:bg-white"
      >
        <div>
          <p className="font-display text-lg text-forest">Products &amp; catalog</p>
          <p className="text-sm text-muted">
            {catalogQuery.data
              ? `${catalogSummary("Livestock", catalogQuery.data.livestock_enabled, catalogQuery.data.enabled_species, "species")} · ${catalogSummary("Crops", catalogQuery.data.crops_enabled, catalogQuery.data.enabled_crop_types, "crop types")}`
              : "Choose which livestock species and crop types this organization can deal in."}
          </p>
        </div>
        <span className="shrink-0 text-sm text-forest">{canWrite ? "Manage" : "View"} →</span>
      </Link>

      <p className="mt-6 text-xs text-muted">
        Created {new Date(org.created_at).toLocaleDateString()}.
      </p>

      <div className="mb-2 mt-8 flex flex-wrap gap-1 border-b border-hairline">
        {PLATFORM_MODULES.map((m) => (
          <Link
            key={m.slug}
            href={`/platform/organizations/${org.id}/${m.slug}`}
            className="rounded-t-md px-3 py-2 text-sm text-muted hover:bg-white/40"
          >
            {m.label}
          </Link>
        ))}
      </div>
      <p className="text-xs text-muted">
        Browse this organization&apos;s data by module above - health, breeding, and dairy records
        are per-animal and aren&apos;t covered by this tab bar; use the API directly for those.
      </p>
    </PlatformShell>
  );
}