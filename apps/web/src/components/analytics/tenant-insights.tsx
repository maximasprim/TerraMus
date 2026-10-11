"use client";

import Link from "next/link";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import { useCatalog } from "@/lib/use-catalog";
import type { AnalyticsReport } from "@/lib/analytics-types";
import { ExpenseBreakdownCard, HerdBySpeciesCard, IncomeExpenseCard, CropsByTypeCard, MilkProductionCard, OrdersByStatusCard } from "./tenant-cards";

/** Query shared by the dashboard (6 months) and the reports page (user-chosen range). */
export function useAnalytics(months: number) {
  return useQuery<AnalyticsReport>({
    queryKey: ["analytics", months],
    queryFn: () => apiFetch<AnalyticsReport>(`/api/v1/reports/analytics?months=${months}`),
    staleTime: 60_000,
    // Changing the range keeps the current charts on screen (dimmed "updating…" label) instead of blanking the page.
    placeholderData: keepPreviousData,
  });
}

/**
 * Charts section appended to the existing farm dashboard. Fully self-contained:
 * if it is loading or the request fails, the dashboard above it is unaffected.
 */
export function TenantInsights() {
  const { data, isLoading, isError } = useAnalytics(6);
  const { data: catalog } = useCatalog(); // fail-open: charts for a switched-off module are hidden
  const livestock = catalog?.livestock_enabled !== false;
  const crops = catalog?.crops_enabled !== false;

  return (
    <section className="mt-10" aria-labelledby="insights-heading">
      <div className="mb-4 flex items-end justify-between">
        <div>
          <h2 id="insights-heading" className="font-display text-xl text-forest">Insights</h2>
          <p className="text-sm text-muted">The last 6 months, at a glance.</p>
        </div>
        <Link href="/admin/reports" className="text-sm text-forest hover:underline">All reports →</Link>
      </div>

      {isLoading && <p className="text-sm text-muted">Loading charts…</p>}
      {isError && <p className="rounded-lg border border-hairline bg-white/60 px-4 py-3 text-sm text-muted">Charts are unavailable right now. The figures above are unaffected.</p>}

      {data && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <IncomeExpenseCard finance={data.finance} className="lg:col-span-2" />
          <ExpenseBreakdownCard finance={data.finance} />
          {livestock ? <HerdBySpeciesCard herd={data.herd} /> : <OrdersByStatusCard sales={data.sales} />}
          {livestock && <MilkProductionCard dairy={data.dairy} className="lg:col-span-2" />}
          {crops && <CropsByTypeCard crops={data.crops} className={livestock ? "" : "lg:col-span-2"} />}
          {livestock && <OrdersByStatusCard sales={data.sales} />}
        </div>
      )}
    </section>
  );
}
