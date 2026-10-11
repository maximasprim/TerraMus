"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { AdminShell } from "@/components/admin-shell";
import { TenantInsights } from "@/components/analytics/tenant-insights";
import { StatCard, ErrorState } from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { ApiError } from "@/lib/api";
import type { DashboardSummary } from "@/lib/types";

export default function DashboardPage() {
  const { data, isLoading, error } = useQuery<DashboardSummary>({
    queryKey: ["dashboard"],
    queryFn: () => apiFetch<DashboardSummary>("/api/v1/reports/dashboard"),
  });

  return (
    <AdminShell>
      <div className="mb-1 flex items-center justify-between">
        <h1 className="font-display text-2xl text-forest">Farm overview</h1>
        <div className="flex gap-4">
          <Link href="/admin/reports" className="text-sm text-forest hover:underline">
            All reports →
          </Link>
          <Link href="/admin/reports/profitability" className="text-sm text-forest hover:underline">
            Profitability report →
          </Link>
        </div>
      </div>
      <p className="mb-6 text-sm text-muted">
        Everything you need to know about the farm, at a glance.
      </p>

      {error && <ErrorState message={error instanceof ApiError ? error.message : "Failed to load dashboard"} />}
      {isLoading && <p className="text-sm text-muted">Loading…</p>}

      {data && (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <StatCard label="Total herd" value={String(data.total_animals)} hint={`${data.active_animals} active`} />
            <StatCard label="Herd value" value={`KES ${Number(data.herd_value).toLocaleString()}`} />
            <StatCard label="For sale" value={String(data.animals_for_sale)} />
            <StatCard label="Reserved" value={String(data.animals_reserved)} />
            <StatCard label="Today's milk" value={`${data.todays_milk_liters} L`} />
            <StatCard label="Inventory value" value={`KES ${Number(data.inventory_value).toLocaleString()}`} />
            <StatCard
              label="This month's revenue"
              value={`KES ${Number(data.monthly_revenue).toLocaleString()}`}
            />
            <StatCard
              label="Est. monthly profit"
              value={`KES ${Number(data.estimated_monthly_profit).toLocaleString()}`}
            />
            < StatCard
              label="Crop Plantings"
              value={String(data.total_crop_plantings)}
              hint={`${data.active_crop_plantings} active`}
            />
            <StatCard label="Crop planting value" value={`KES ${Number(data.crop_planting_value).toLocaleString()}`} />
             <StatCard
              label="Low-stock crop listings"
              value={String(data.low_stock_crop_listing_count)}
              hint={data.low_stock_crop_listing_count > 0 ? "Restock or deactivate soon" : "All good"}
            />
          </div>

          <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2">
            {data.low_stock_item_count > 0 && (
              <div className="rounded-lg border border-brass/30 bg-brass/5 px-4 py-3 text-sm text-brass-dark">
                {data.low_stock_item_count} inventory item{data.low_stock_item_count === 1 ? "" : "s"} running low
              </div>
            )}
            {data.vaccinations_due_count > 0 && (
              <div className="rounded-lg border border-clay/30 bg-clay/5 px-4 py-3 text-sm text-clay">
                {data.vaccinations_due_count} vaccination{data.vaccinations_due_count === 1 ? "" : "s"}/follow-up{data.vaccinations_due_count === 1 ? "" : "s"} due within 14 days
              </div>
            )}
          </div>
        </>
      )}

      <TenantInsights />
    </AdminShell>
  );
}
