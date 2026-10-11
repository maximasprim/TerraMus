"use client";

import { useState } from "react";
import { PlatformShell } from "@/components/platform-shell";
import { Button, ErrorState, StatCard } from "@/components/ui";
import { downloadCsv, count, kes, toNumber } from "@/components/charts";
import { RangePicker } from "@/components/analytics/range-picker";
import { platformRows } from "@/components/analytics/exports";
import { usePlatformAnalytics } from "@/components/analytics/platform-insights";
import {
  GrowthCard, MrrByTierCard, OrgStatusCard, PaymentMethodsCard, SignupsCard, SpeciesMixCard, SubscriptionRevenueCard,
  SubscriptionStatusCard, TenantGmvCard, TierMixCard, TopTenantsCard,
} from "@/components/analytics/platform-cards";
import { PlatformApiError } from "@/lib/platform-api";

const RANGES = [3, 6, 12, 24, 36];

export default function PlatformAnalyticsPage() {
  const [months, setMonths] = useState(12);
  const { data, isLoading, error, isFetching } = usePlatformAnalytics(months);

  return (
    <PlatformShell>
      <div className="printable-report">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="font-display text-2xl text-forest">Platform analytics</h1>
            <p className="text-sm text-muted">
              {data ? `${data.start_date} to ${data.end_date} · ${data.timezone}` : "Growth, revenue and usage across every tenant."}
              {isFetching && !isLoading && " · updating…"}
            </p>
          </div>
          <div className="no-print flex flex-wrap items-center gap-3">
            <RangePicker value={months} options={RANGES} onChange={setMonths} label="Months to show" />
            <Button variant="ghost" disabled={!data} onClick={() => data && downloadCsv(`terramus-platform-${data.start_date}-to-${data.end_date}.csv`, platformRows(data))}>
              Export CSV
            </Button>
            <Button variant="ghost" onClick={() => window.print()}>Print / save as PDF</Button>
          </div>
        </div>

        {error && <div className="mt-6"><ErrorState message={error instanceof PlatformApiError ? error.message : "Failed to load analytics"} /></div>}
        {isLoading && <p className="mt-6 text-sm text-muted">Loading analytics…</p>}

        {data && (
          <>
            <div className="mt-6 grid grid-cols-2 gap-4 md:grid-cols-4">
              <StatCard label="Organizations" value={count(data.totals.organizations)} hint={`${count(data.totals.users)} users`} />
              <StatCard label="MRR" value={kes(toNumber(data.totals.mrr_kes))} hint="active subscriptions" />
              <StatCard label="Subscription revenue" value={kes(toNumber(data.totals.subscription_revenue))} hint={`collected, last ${data.months}M`} />
              <StatCard label="Tenant sales volume" value={kes(toNumber(data.totals.gmv))} hint={`processed, last ${data.months}M`} />
              <StatCard label="Active animals" value={count(data.totals.animals)} />
              <StatCard label="Crop plantings" value={count(data.totals.crop_plantings)} />
              <StatCard label="Orders (all time)" value={count(data.totals.orders)} />
            </div>

            <section className="mt-10" aria-labelledby="growth-heading">
              <h2 id="growth-heading" className="mb-4 font-display text-xl text-forest">Growth</h2>
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 [&>*]:avoid-break">
                <SignupsCard data={data} />
                <GrowthCard data={data} />
                <OrgStatusCard data={data} />
              </div>
            </section>

            <section className="mt-10" aria-labelledby="revenue-heading">
              <h2 id="revenue-heading" className="mb-4 font-display text-xl text-forest">Plans &amp; revenue</h2>
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 [&>*]:avoid-break">
                <TierMixCard data={data} />
                <MrrByTierCard data={data} />
                <SubscriptionStatusCard data={data} />
                <SubscriptionRevenueCard data={data} />
              </div>
            </section>

            <section className="mt-10" aria-labelledby="usage-heading">
              <h2 id="usage-heading" className="mb-4 font-display text-xl text-forest">Tenant activity</h2>
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 [&>*]:avoid-break">
                <TenantGmvCard data={data} className="lg:col-span-2" />
                <PaymentMethodsCard data={data} />
                <SpeciesMixCard data={data} />
                <TopTenantsCard data={data} className="lg:col-span-2" />
              </div>
            </section>
          </>
        )}
      </div>
    </PlatformShell>
  );
}
