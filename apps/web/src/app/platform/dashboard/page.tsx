"use client";

import { useQuery } from "@tanstack/react-query";
import { PlatformShell } from "@/components/platform-shell";
import { PlatformInsights } from "@/components/analytics/platform-insights";
import { StatCard, ErrorState, Card } from "@/components/ui";
import { platformApiFetch, PlatformApiError } from "@/lib/platform-api";
import type { PlatformDashboardStats } from "@/lib/platform-types";

export default function PlatformDashboardPage() {
  const { data, isLoading, error } = useQuery<PlatformDashboardStats>({
    queryKey: ["platform-dashboard"],
    queryFn: () => platformApiFetch<PlatformDashboardStats>("/api/v1/platform/dashboard"),
  });

  return (
    <PlatformShell>
      <h1 className="mb-1 font-display text-2xl text-forest">TerraMus overview</h1>
      <p className="mb-6 text-sm text-muted">Every tenant, at a glance.</p>

      {error && <ErrorState message={error instanceof PlatformApiError ? error.message : "Failed to load dashboard"} />}
      {isLoading && <p className="text-sm text-muted">Loading…</p>}

      {data && (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <StatCard label="Organizations" value={String(data.total_organizations)} hint={`${data.active_organizations} active`} />
            <StatCard label="Suspended" value={String(data.suspended_organizations)} />
            <StatCard label="Total users" value={String(data.total_users)} />
            <StatCard label="New orgs (30d)" value={String(data.signups_last_30_days)} />
            <StatCard label="MRR" value={`KES ${data.mrr_kes.toLocaleString()}`} hint="active subscriptions only" />
          </div>

          <Card className="mt-6">
            <p className="mb-3 text-sm font-medium text-ink">Organizations by tier</p>
            {Object.keys(data.organizations_by_tier).length === 0 ? (
              <p className="text-sm text-muted">No active subscriptions yet.</p>
            ) : (
              <div className="flex flex-wrap gap-3">
                {Object.entries(data.organizations_by_tier).map(([tier, count]) => (
                  <div key={tier} className="rounded-md border border-hairline bg-white/60 px-3 py-2 text-sm">
                    <span className="font-medium text-ink">{tier}</span>{" "}
                    <span className="text-muted">- {count}</span>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </>
      )}

      <PlatformInsights />
    </PlatformShell>
  );
}
