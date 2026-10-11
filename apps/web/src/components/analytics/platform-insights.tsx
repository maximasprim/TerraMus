"use client";

import Link from "next/link";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { platformApiFetch } from "@/lib/platform-api";
import type { PlatformAnalytics } from "@/lib/analytics-types";
import { SignupsCard, SubscriptionRevenueCard, TenantGmvCard, TierMixCard } from "./platform-cards";

export function usePlatformAnalytics(months: number) {
  return useQuery<PlatformAnalytics>({
    queryKey: ["platform-analytics", months],
    queryFn: () => platformApiFetch<PlatformAnalytics>(`/api/v1/platform/analytics?months=${months}`),
    staleTime: 60_000,
    placeholderData: keepPreviousData, // keep the charts visible while a new range loads
  });
}

/** Charts appended to the existing superadmin dashboard. Self-contained: a failure here never affects the cards above. */
export function PlatformInsights() {
  const { data, isLoading, isError } = usePlatformAnalytics(6);
  return (
    <section className="mt-10" aria-labelledby="platform-insights-heading">
      <div className="mb-4 flex items-end justify-between">
        <div>
          <h2 id="platform-insights-heading" className="font-display text-xl text-forest">Insights</h2>
          <p className="text-sm text-muted">The last 6 months across every tenant.</p>
        </div>
        <Link href="/platform/analytics" className="text-sm text-forest hover:underline">Full analytics →</Link>
      </div>
      {isLoading && <p className="text-sm text-muted">Loading charts…</p>}
      {isError && <p className="rounded-lg border border-hairline bg-white/60 px-4 py-3 text-sm text-muted">Charts are unavailable right now. The figures above are unaffected.</p>}
      {data && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <SignupsCard data={data} />
          <TierMixCard data={data} />
          <SubscriptionRevenueCard data={data} />
          <TenantGmvCard data={data} />
        </div>
      )}
    </section>
  );
}
