"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, ErrorState } from "@/components/ui";
import { platformApiFetch, PlatformApiError } from "@/lib/platform-api";
import { openTenantWorkspace } from "@/lib/platform-workspace";
import type { PlatformMenuEntry, TenantCatalogSettings } from "@/lib/platform-types";

/**
 * Every menu the organization's own admin app has - read from the backend's menu list, so a menu added to the
 * tenant sidebar later appears here with no change to this file. Opening one starts a superadmin workspace
 * session and lands on that page in the tenant app, where everything a tenant can do works.
 */
export function PlatformWorkspacePanel({ orgId, canWrite }: { orgId: string; orgName?: string; canWrite: boolean }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const menusQuery = useQuery<PlatformMenuEntry[]>({
    queryKey: ["platform-catalog-menus"],
    queryFn: () => platformApiFetch<PlatformMenuEntry[]>("/api/v1/platform/catalog/menus"),
  });
  // Shares its cache key with the organization page, so this costs no extra request.
  const catalogQuery = useQuery<TenantCatalogSettings>({
    queryKey: ["platform-catalog-settings", orgId],
    queryFn: () => platformApiFetch<TenantCatalogSettings>(`/api/v1/platform/organizations/${orgId}/catalog-settings`),
  });
  const hidden = useMemo(() => new Set(catalogQuery.data?.hidden_menus ?? []), [catalogQuery.data]);

  const groups = useMemo(() => {
    const out: { group: string; entries: PlatformMenuEntry[] }[] = [];
    for (const entry of menusQuery.data ?? []) {
      let g = out.find((x) => x.group === entry.group);
      if (!g) { g = { group: entry.group, entries: [] }; out.push(g); }
      g.entries.push(entry);
    }
    return out;
  }, [menusQuery.data]);

  async function open(path: string) {
    setError(null);
    setBusy(path);
    try {
      await openTenantWorkspace(orgId, path);
    } catch (err) {
      setBusy(null);
      setError(err instanceof PlatformApiError ? err.message : "Could not open the workspace");
    }
  }

  return (
    <Card>
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <p className="text-xs font-medium uppercase tracking-wider text-muted">Tenant workspace</p>
        <p className="text-xs text-muted">Open any menu as this organization. Changes are recorded under your account.</p>
      </div>
      {!canWrite && <p className="mt-2 text-sm text-clay">Only superadmins can open a tenant workspace.</p>}
      {error && <div className="mt-3"><ErrorState message={error} /></div>}
      {menusQuery.error && <div className="mt-3"><ErrorState message="Could not load the menu list" /></div>}
      {menusQuery.isLoading && <p className="mt-3 text-sm text-muted">Loading…</p>}

      <dl className="mt-3 divide-y divide-hairline">
        {groups.map(({ group, entries }) => (
          <div key={group} className="grid gap-x-4 gap-y-1 py-2 sm:grid-cols-[7.5rem_1fr]">
            <dt className="text-xs text-muted sm:pt-0.5">{group}</dt>
            <dd className="flex flex-wrap gap-x-4 gap-y-1">
              {entries.map((m) => (
                <button
                  key={m.key}
                  type="button"
                  disabled={!canWrite || busy !== null}
                  onClick={() => open(m.key)}
                  title={hidden.has(m.key) ? "Hidden for this organization - you can still use it" : undefined}
                  className="rounded text-sm text-forest underline-offset-4 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-forest disabled:opacity-50 disabled:no-underline"
                >
                  {busy === m.key ? "Opening…" : m.label}
                  {hidden.has(m.key) && <span className="ml-1 text-xs text-muted">· hidden</span>}
                </button>
              ))}
            </dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}