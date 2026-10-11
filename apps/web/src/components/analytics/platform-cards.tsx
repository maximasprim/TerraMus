"use client";

import Link from "next/link";
import { BarChart, ChartCard, DonutChart, LineChart, SEMANTIC, STATUS_COLORS, colorAt, count, humanize, kes, monthLabels, toNumber } from "@/components/charts";
import type { PlatformAnalytics } from "@/lib/analytics-types";
import { countSlices } from "./tenant-cards";

const monthTitles = (months: string[]) => months.map((m) => {
  const [y, mo] = m.split("-");
  return `${["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"][Number(mo) - 1]} ${y}`;
});

export function SignupsCard({ data, className }: { data: PlatformAnalytics; className?: string }) {
  const months = data.signups_monthly.map((m) => m.month);
  return (
    <ChartCard title="New organizations" subtitle="Signups per month" empty={data.signups_monthly.every((m) => m.count === 0)} emptyText="No signups in this period." className={className}>
      <BarChart
        ariaLabel="New organizations per month" showLegend={false}
        categories={monthLabels(months)} tooltipTitles={monthTitles(months)}
        series={[{ name: "New organizations", color: SEMANTIC.income, values: data.signups_monthly.map((m) => m.count) }]}
      />
    </ChartCard>
  );
}

export function GrowthCard({ data, className }: { data: PlatformAnalytics; className?: string }) {
  const months = data.signups_monthly.map((m) => m.month);
  return (
    <ChartCard title="Total organizations" subtitle="Cumulative, at the end of each month" empty={data.totals.organizations === 0} emptyText="No organizations yet." className={className}>
      <LineChart
        ariaLabel="Total organizations over time" showLegend={false} height={220}
        categories={monthLabels(months)} tooltipTitles={monthTitles(months)}
        series={[{ name: "Organizations", color: SEMANTIC.net, values: data.signups_monthly.map((m) => m.cumulative), area: true }]}
      />
    </ChartCard>
  );
}

export function TierMixCard({ data, className }: { data: PlatformAnalytics; className?: string }) {
  return (
    <ChartCard title="Organizations by plan" subtitle="Organizations that haven't opened billing count as Free" empty={data.organizations_by_tier.length === 0} emptyText="No organizations yet." className={className}>
      <DonutChart
        ariaLabel="Organizations by plan" centerLabel="Organizations" centerValue={count(data.totals.organizations)}
        data={data.organizations_by_tier.map((t, i) => ({ label: t.key, value: t.count, color: colorAt(i) }))}
      />
    </ChartCard>
  );
}

export function MrrByTierCard({ data, className }: { data: PlatformAnalytics; className?: string }) {
  const paid = data.organizations_by_tier.filter((t) => toNumber(t.mrr_kes) > 0);
  return (
    <ChartCard title="Monthly recurring revenue" subtitle={`${kes(toNumber(data.totals.mrr_kes))} from active subscriptions`} empty={paid.length === 0} emptyText="No active paid subscriptions yet." className={className}>
      <DonutChart
        ariaLabel="MRR by plan" format={kes} centerLabel="MRR" centerValue={kes(toNumber(data.totals.mrr_kes))}
        data={paid.map((t, i) => ({ label: t.key, value: toNumber(t.mrr_kes), color: colorAt(i) }))}
      />
    </ChartCard>
  );
}

export function SubscriptionStatusCard({ data, className }: { data: PlatformAnalytics; className?: string }) {
  return (
    <ChartCard title="Subscription health" subtitle="Subscriptions by status" empty={data.subscriptions_by_status.length === 0} emptyText="No subscriptions yet." className={className}>
      <DonutChart ariaLabel="Subscriptions by status" centerLabel="Subscriptions" data={countSlices(data.subscriptions_by_status)} />
    </ChartCard>
  );
}

export function OrgStatusCard({ data, className }: { data: PlatformAnalytics; className?: string }) {
  return (
    <ChartCard title="Active vs suspended" subtitle="Organizations" empty={data.totals.organizations === 0} emptyText="No organizations yet." className={className}>
      <DonutChart
        ariaLabel="Organizations by status" centerLabel="Organizations"
        data={data.organizations_by_status.map((s) => ({ label: humanize(s.key), value: s.count, color: STATUS_COLORS[s.key] ?? (s.key === "active" ? "#3F6B4A" : undefined) }))}
      />
    </ChartCard>
  );
}

export function SubscriptionRevenueCard({ data, className }: { data: PlatformAnalytics; className?: string }) {
  const months = data.subscription_revenue_monthly.map((m) => m.month);
  return (
    <ChartCard
      title="Subscription revenue collected" subtitle={`${kes(toNumber(data.totals.subscription_revenue))} in this period · actual payments, not forecast`}
      empty={data.subscription_revenue_monthly.every((m) => toNumber(m.amount) === 0)} emptyText="No subscription payments in this period." className={className}
    >
      <BarChart
        ariaLabel="Subscription revenue collected per month" showLegend={false} format={kes}
        categories={monthLabels(months)} tooltipTitles={monthTitles(months)}
        series={[{ name: "Collected", color: SEMANTIC.income, values: data.subscription_revenue_monthly.map((m) => toNumber(m.amount)) }]}
      />
    </ChartCard>
  );
}

export function TenantGmvCard({ data, className }: { data: PlatformAnalytics; className?: string }) {
  const months = data.tenant_gmv_monthly.map((m) => m.month);
  return (
    <ChartCard
      title="Tenant sales volume" subtitle={`${kes(toNumber(data.totals.gmv))} of customer payments processed for tenants`}
      empty={data.tenant_gmv_monthly.every((m) => toNumber(m.amount) === 0)} emptyText="No customer payments in this period." className={className}
    >
      <LineChart
        ariaLabel="Tenant sales volume per month" showLegend={false} format={kes} height={220}
        categories={monthLabels(months)} tooltipTitles={monthTitles(months)}
        series={[{ name: "GMV", color: SEMANTIC.net, values: data.tenant_gmv_monthly.map((m) => toNumber(m.amount)), area: true }]}
      />
    </ChartCard>
  );
}

export function PaymentMethodsCard({ data, className }: { data: PlatformAnalytics; className?: string }) {
  return (
    <ChartCard title="Payment methods" subtitle="Successful customer payments" empty={data.tenant_payments_by_provider.length === 0} emptyText="No customer payments in this period." className={className}>
      <DonutChart
        ariaLabel="Customer payments by method" format={kes} centerLabel="Processed"
        data={data.tenant_payments_by_provider.map((p, i) => ({ label: humanize(p.key), value: toNumber(p.amount), color: colorAt(i) }))}
      />
    </ChartCard>
  );
}

export function SpeciesMixCard({ data, className }: { data: PlatformAnalytics; className?: string }) {
  return (
    <ChartCard title="Livestock across the platform" subtitle="Active animals by species" empty={data.species_distribution.length === 0} emptyText="No animals registered yet." className={className}>
      <DonutChart
        ariaLabel="Active animals by species across all organizations" centerLabel="Animals" centerValue={count(data.totals.animals)}
        data={data.species_distribution.map((s, i) => ({ label: humanize(s.key), value: s.count, color: colorAt(i) }))}
      />
    </ChartCard>
  );
}

export function TopTenantsCard({ data, className }: { data: PlatformAnalytics; className?: string }) {
  return (
    <ChartCard title="Top tenants" subtitle="Ranked by customer payments processed in this period" empty={data.top_tenants.length === 0} emptyText="No organizations yet." className={className}>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-hairline text-left text-xs uppercase tracking-wider text-muted">
              <th className="py-2 pr-3 font-medium">Organization</th>
              <th className="px-3 py-2 text-right font-medium">Users</th>
              <th className="px-3 py-2 text-right font-medium">Animals</th>
              <th className="px-3 py-2 text-right font-medium">Plantings</th>
              <th className="px-3 py-2 text-right font-medium">Orders</th>
              <th className="py-2 pl-3 text-right font-medium">GMV</th>
            </tr>
          </thead>
          <tbody>
            {data.top_tenants.map((t) => (
              <tr key={t.organization_id} className="border-b border-hairline/60 last:border-0">
                <td className="py-2 pr-3">
                  <Link href={`/platform/organizations/${t.organization_id}`} className="text-forest hover:underline">{t.name}</Link>
                  {t.is_suspended && <span className="ml-2 rounded bg-clay/10 px-1.5 py-0.5 text-xs text-clay">Suspended</span>}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">{count(t.users)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{count(t.animals)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{count(t.crop_plantings)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{count(t.orders)}</td>
                <td className="py-2 pl-3 text-right tabular-nums">{kes(toNumber(t.gmv))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </ChartCard>
  );
}
