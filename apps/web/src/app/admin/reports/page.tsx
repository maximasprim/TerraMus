"use client";

import { useState, type ReactNode } from "react";
import Link from "next/link";
import { AdminShell } from "@/components/admin-shell";
import { Button, ErrorState, StatCard } from "@/components/ui";
import { downloadCsv, kes, liters, toNumber } from "@/components/charts";
import { RangePicker } from "@/components/analytics/range-picker";
import { useAnalytics } from "@/components/analytics/tenant-insights";
import { tenantSectionRows, type TenantSection } from "@/components/analytics/exports";
import {
  CropStatusCard, CropsByTypeCard, ExpenseBreakdownCard, HarvestCard, HealthByTypeCard, HealthCostCard, HerdBySpeciesCard,
  HerdByStatusCard, IncomeBreakdownCard, IncomeExpenseCard, InventoryValueCard, MilkProductionCard, NetProfitCard,
  OrdersByStatusCard, PaymentsByProviderCard, SalesRevenueCard,
} from "@/components/analytics/tenant-cards";
import { ApiError } from "@/lib/api";
import { useCatalog } from "@/lib/use-catalog";

const RANGES = [3, 6, 12, 24];

function Section({ id, title, blurb, actions, children }: { id: string; title: string; blurb: string; actions?: ReactNode; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-heading`} className="mt-10">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 id={`${id}-heading`} className="font-display text-xl text-forest">{title}</h2>
          <p className="text-sm text-muted">{blurb}</p>
        </div>
        <div className="no-print flex gap-2">{actions}</div>
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 [&>*]:avoid-break">{children}</div>
    </section>
  );
}

export default function ReportsPage() {
  const [months, setMonths] = useState(6);
  const { data, isLoading, error, isFetching } = useAnalytics(months);
  const { data: catalog } = useCatalog(); // fail-open
  const livestock = catalog?.livestock_enabled !== false;
  const crops = catalog?.crops_enabled !== false;

  const exportCsv = (section: TenantSection) => {
    if (!data) return;
    downloadCsv(`terramus-${section}-${data.start_date}-to-${data.end_date}.csv`, tenantSectionRows(data, section));
  };
  const csvButton = (section: TenantSection, label = "Export CSV") => (
    <Button key={section} variant="ghost" onClick={() => exportCsv(section)}>{label}</Button>
  );

  return (
    <AdminShell>
      <div className="printable-report">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="font-display text-2xl text-forest">Reports &amp; analytics</h1>
            <p className="text-sm text-muted">
              {data ? `${data.start_date} to ${data.end_date} · ${data.timezone}` : "Everything about the farm, charted."}
              {isFetching && !isLoading && " · updating…"}
            </p>
          </div>
          <div className="no-print flex flex-wrap items-center gap-3">
            <RangePicker value={months} options={RANGES} onChange={setMonths} label="Months to show" />
            <Button variant="ghost" onClick={() => window.print()}>Print / save as PDF</Button>
          </div>
        </div>
        <div className="no-print mt-2 flex gap-4 text-sm">
          <Link href="/admin/reports/profitability" className="text-forest hover:underline">Profitability report →</Link>
          <Link href="/admin/dashboard" className="text-forest hover:underline">Back to dashboard</Link>
        </div>

        {error && <div className="mt-6"><ErrorState message={error instanceof ApiError ? error.message : "Failed to load analytics"} /></div>}
        {isLoading && <p className="mt-6 text-sm text-muted">Loading analytics…</p>}

        {data && (
          <>
            <div className="mt-6 grid grid-cols-2 gap-4 md:grid-cols-4">
              <StatCard label="Income" value={kes(toNumber(data.finance.total_income))} hint={`last ${data.months} month${data.months === 1 ? "" : "s"}`} />
              <StatCard label="Expenses" value={kes(toNumber(data.finance.total_expense))} />
              <StatCard label="Net profit" value={kes(toNumber(data.finance.net))} hint={toNumber(data.finance.net) < 0 ? "Spending exceeded income" : undefined} />
              <StatCard label="Paid orders" value={String(data.sales.total_orders)} hint={`${kes(toNumber(data.sales.total_revenue))} revenue`} />
              {livestock && <StatCard label="Active herd" value={String(data.herd.active)} hint={`${data.herd.total} animals on record`} />}
              {livestock && <StatCard label="Milk / day" value={liters(toNumber(data.dairy.average_per_day))} hint="30-day average" />}
              {crops && <StatCard label="Active plantings" value={String(data.crops.active)} hint={`${data.crops.total} on record`} />}
              <StatCard label="Inventory value" value={kes(toNumber(data.inventory.total_value))} hint={`${data.inventory.total_items} items`} />
            </div>

            <Section id="finance" title="Finance" blurb="Income and expenses from the finance ledger." actions={csvButton("finance")}>
              <IncomeExpenseCard finance={data.finance} className="lg:col-span-2" />
              <NetProfitCard finance={data.finance} className="lg:col-span-2" />
              <IncomeBreakdownCard finance={data.finance} />
              <ExpenseBreakdownCard finance={data.finance} />
            </Section>

            <Section id="sales" title="Sales" blurb={`Average paid order: ${kes(toNumber(data.sales.average_order_value))}.`} actions={csvButton("sales")}>
              <SalesRevenueCard sales={data.sales} className="lg:col-span-2" />
              <OrdersByStatusCard sales={data.sales} />
              <PaymentsByProviderCard sales={data.sales} />
            </Section>

            {livestock && (
              <Section
                id="livestock" title="Livestock, dairy & health" blurb="Herd make-up, milk production and animal-health spending."
                actions={[csvButton("herd", "Herd CSV"), csvButton("dairy", "Milk CSV"), csvButton("health", "Health CSV")]}
              >
                <HerdBySpeciesCard herd={data.herd} />
                <HerdByStatusCard herd={data.herd} />
                <MilkProductionCard dairy={data.dairy} className="lg:col-span-2" />
                <HealthCostCard health={data.health} />
                <HealthByTypeCard health={data.health} />
              </Section>
            )}

            {crops && (
              <Section id="crops" title="Crops" blurb="Plantings and harvests." actions={csvButton("crops")}>
                <CropsByTypeCard crops={data.crops} />
                <CropStatusCard crops={data.crops} />
                <HarvestCard crops={data.crops} className="lg:col-span-2" />
              </Section>
            )}

            <Section id="inventory" title="Inventory" blurb="What is on the shelves, valued at the latest purchase cost." actions={csvButton("inventory")}>
              <InventoryValueCard inventory={data.inventory} className="lg:col-span-2" />
            </Section>
          </>
        )}
      </div>
    </AdminShell>
  );
}
