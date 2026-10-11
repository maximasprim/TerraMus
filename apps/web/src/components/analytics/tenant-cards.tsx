"use client";

import { BarChart, ChartCard, DonutChart, LineChart, SEMANTIC, STATUS_COLORS, colorAt, count, dayLabel, humanize, kes, liters, monthLabels, toNumber } from "@/components/charts";
import type { Slice } from "@/components/charts";
import type {
  CropAnalytics, DairyAnalytics, FinanceAnalytics, HealthAnalytics, HerdAnalytics, InventoryAnalytics, LabelCount, SalesAnalytics,
} from "@/lib/analytics-types";

/** Status/category counts -> donut slices, with fixed status colours where we have them. */
export function countSlices(items: LabelCount[]): Slice[] {
  return items.map((i) => ({ label: humanize(i.key), value: i.count, color: STATUS_COLORS[i.key] }));
}

const monthTitles = (months: string[]) => months.map((m) => {
  const [y, mo] = m.split("-");
  return `${["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"][Number(mo) - 1]} ${y}`;
});

/* ----------------------------------------------------------------- finance */

export function IncomeExpenseCard({ finance, className }: { finance: FinanceAnalytics; className?: string }) {
  const months = finance.monthly.map((m) => m.month);
  const empty = finance.monthly.every((m) => toNumber(m.income) === 0 && toNumber(m.expense) === 0);
  return (
    <ChartCard title="Income vs expenses" subtitle="From the finance ledger, per month" empty={empty} emptyText="No income or expenses recorded in this period." className={className}>
      <BarChart
        ariaLabel="Income and expenses per month"
        categories={monthLabels(months)} tooltipTitles={monthTitles(months)} format={kes}
        series={[
          { name: "Income", color: SEMANTIC.income, values: finance.monthly.map((m) => toNumber(m.income)) },
          { name: "Expenses", color: SEMANTIC.expense, values: finance.monthly.map((m) => toNumber(m.expense)) },
        ]}
      />
    </ChartCard>
  );
}

export function NetProfitCard({ finance, className }: { finance: FinanceAnalytics; className?: string }) {
  const months = finance.monthly.map((m) => m.month);
  const empty = finance.monthly.every((m) => toNumber(m.income) === 0 && toNumber(m.expense) === 0);
  return (
    <ChartCard title="Net profit" subtitle="Income minus expenses, per month" empty={empty} emptyText="No income or expenses recorded in this period." className={className}>
      <LineChart
        ariaLabel="Net profit per month" height={220}
        categories={monthLabels(months)} tooltipTitles={monthTitles(months)} format={kes}
        series={[{ name: "Net", color: SEMANTIC.net, values: finance.monthly.map((m) => toNumber(m.net)), area: true }]}
      />
    </ChartCard>
  );
}

export function ExpenseBreakdownCard({ finance, className }: { finance: FinanceAnalytics; className?: string }) {
  return (
    <ChartCard title="Where the money goes" subtitle="Expenses by category" empty={finance.expense_by_category.length === 0} emptyText="No expenses recorded in this period." className={className}>
      <DonutChart
        ariaLabel="Expenses by category" format={kes} centerLabel="Total spent" centerValue={kes(toNumber(finance.total_expense))}
        data={finance.expense_by_category.map((c, i) => ({ label: humanize(c.key), value: toNumber(c.amount), color: colorAt(i) }))}
      />
    </ChartCard>
  );
}

export function IncomeBreakdownCard({ finance, className }: { finance: FinanceAnalytics; className?: string }) {
  return (
    <ChartCard title="Where the money comes from" subtitle="Income by category" empty={finance.income_by_category.length === 0} emptyText="No income recorded in this period." className={className}>
      <DonutChart
        ariaLabel="Income by category" format={kes} centerLabel="Total earned" centerValue={kes(toNumber(finance.total_income))}
        data={finance.income_by_category.map((c, i) => ({ label: humanize(c.key), value: toNumber(c.amount), color: colorAt(i) }))}
      />
    </ChartCard>
  );
}

/* ------------------------------------------------------------------- sales */

export function SalesRevenueCard({ sales, className }: { sales: SalesAnalytics; className?: string }) {
  const months = sales.monthly.map((m) => m.month);
  return (
    <ChartCard title="Sales revenue" subtitle="Paid orders, per month" empty={sales.total_orders === 0} emptyText="No paid orders in this period." className={className}>
      <BarChart
        ariaLabel="Sales revenue per month" showLegend={false}
        categories={monthLabels(months)} tooltipTitles={monthTitles(months)} format={kes}
        series={[{ name: "Revenue", color: SEMANTIC.income, values: sales.monthly.map((m) => toNumber(m.revenue)) }]}
      />
    </ChartCard>
  );
}

export function OrdersByStatusCard({ sales, className }: { sales: SalesAnalytics; className?: string }) {
  return (
    <ChartCard title="Orders by status" subtitle="Every order in this period" empty={sales.orders_by_status.length === 0} emptyText="No orders in this period." className={className}>
      <DonutChart ariaLabel="Orders by status" centerLabel="Orders" data={countSlices(sales.orders_by_status)} />
    </ChartCard>
  );
}

export function PaymentsByProviderCard({ sales, className }: { sales: SalesAnalytics; className?: string }) {
  return (
    <ChartCard title="How customers pay" subtitle="Successful payments by method" empty={sales.payments_by_provider.length === 0} emptyText="No successful payments in this period." className={className}>
      <DonutChart
        ariaLabel="Successful payments by method" format={kes} centerLabel="Collected"
        data={sales.payments_by_provider.map((p, i) => ({ label: humanize(p.key), value: toNumber(p.amount), color: colorAt(i) }))}
      />
    </ChartCard>
  );
}

/* -------------------------------------------------------------------- herd */

export function HerdBySpeciesCard({ herd, className }: { herd: HerdAnalytics; className?: string }) {
  return (
    <ChartCard title="Herd by species" subtitle="Active animals" empty={herd.by_species.length === 0} emptyText="No active animals yet." className={className}>
      <DonutChart
        ariaLabel="Active animals by species" centerLabel="Active animals" centerValue={count(herd.active)}
        data={herd.by_species.map((s, i) => ({ label: humanize(s.key), value: s.count, color: colorAt(i) }))}
      />
    </ChartCard>
  );
}

export function HerdByStatusCard({ herd, className }: { herd: HerdAnalytics; className?: string }) {
  return (
    <ChartCard title="Herd by status" subtitle="Every animal on record" empty={herd.by_status.length === 0} emptyText="No animals yet." className={className}>
      <BarChart
        horizontal showLegend={false} ariaLabel="Animals by status"
        categories={herd.by_status.map((s) => humanize(s.key))}
        series={[{ name: "Animals", color: SEMANTIC.net, values: herd.by_status.map((s) => s.count) }]}
      />
    </ChartCard>
  );
}

export function MilkProductionCard({ dairy, className }: { dairy: DairyAnalytics; className?: string }) {
  const empty = toNumber(dairy.total_liters) === 0 && toNumber(dairy.rejected_liters) === 0;
  return (
    <ChartCard
      title="Milk production" subtitle={`Last 30 days · ${liters(toNumber(dairy.total_liters))} total · ${liters(toNumber(dairy.average_per_day))}/day`}
      empty={empty} emptyText="No milk recorded in the last 30 days." className={className}
    >
      <LineChart
        ariaLabel="Milk produced per day over the last 30 days" height={220} format={liters} showLegend={false}
        categories={dairy.daily.map((d) => dayLabel(d.date))}
        series={[{ name: "Milk", color: SEMANTIC.income, values: dairy.daily.map((d) => toNumber(d.liters)), area: true }]}
      />
      {toNumber(dairy.rejected_liters) > 0 && (
        <p className="mt-2 text-xs text-muted">{liters(toNumber(dairy.rejected_liters))} was rejected and is not counted above.</p>
      )}
    </ChartCard>
  );
}

/* ------------------------------------------------------------------- crops */

export function CropsByTypeCard({ crops, className }: { crops: CropAnalytics; className?: string }) {
  return (
    <ChartCard title="Plantings by crop" subtitle="Active plantings" empty={crops.by_type.length === 0} emptyText="No active plantings yet." className={className}>
      <BarChart
        horizontal showLegend={false} ariaLabel="Active plantings by crop type"
        categories={crops.by_type.map((c) => humanize(c.key))}
        tooltipTitles={crops.by_type.map((c) => `${humanize(c.key)} · ${toNumber(c.area).toLocaleString("en-US")} area`)}
        series={[{ name: "Plantings", color: SEMANTIC.income, values: crops.by_type.map((c) => c.plantings) }]}
      />
    </ChartCard>
  );
}

export function CropStatusCard({ crops, className }: { crops: CropAnalytics; className?: string }) {
  return (
    <ChartCard title="Plantings by stage" subtitle="Every planting on record" empty={crops.by_status.length === 0} emptyText="No plantings yet." className={className}>
      <DonutChart ariaLabel="Plantings by status" centerLabel="Plantings" data={countSlices(crops.by_status)} />
    </ChartCard>
  );
}

export function HarvestCard({ crops, className }: { crops: CropAnalytics; className?: string }) {
  const months = crops.harvests_monthly.map((m) => m.month);
  const empty = crops.harvest_by_unit.length === 0;
  return (
    <ChartCard title="Harvests" subtitle="Harvest records per month" empty={empty} emptyText="No harvests recorded in this period." className={className}>
      <BarChart
        ariaLabel="Harvest records per month" showLegend={false} height={200}
        categories={monthLabels(months)} tooltipTitles={monthTitles(months)}
        series={[{ name: "Harvests", color: SEMANTIC.net, values: crops.harvests_monthly.map((m) => m.count) }]}
      />
      {/* units differ (kg, bags, crates...) so quantities are listed per unit, never added together */}
      <ul className="mt-3 flex flex-wrap gap-2 text-xs">
        {crops.harvest_by_unit.map((u) => (
          <li key={u.unit} className="rounded-md border border-hairline bg-white/60 px-2.5 py-1 text-ink">
            <span className="font-medium tabular-nums">{toNumber(u.quantity).toLocaleString("en-US")}</span> {u.unit}
            <span className="text-muted"> · {u.records} record{u.records === 1 ? "" : "s"}</span>
          </li>
        ))}
      </ul>
    </ChartCard>
  );
}

/* --------------------------------------------------------------- inventory */

export function InventoryValueCard({ inventory, className }: { inventory: InventoryAnalytics; className?: string }) {
  const hasValue = inventory.by_category.some((c) => toNumber(c.value) > 0);
  return (
    <ChartCard title="Inventory value" subtitle="Stock on hand x latest purchase cost, by category" empty={!hasValue} emptyText="No stock with a known cost yet." className={className}>
      <DonutChart
        ariaLabel="Inventory value by category" format={kes} centerLabel="Stock value" centerValue={kes(toNumber(inventory.total_value))}
        data={inventory.by_category.map((c, i) => ({ label: humanize(c.key), value: toNumber(c.value), color: colorAt(i) }))}
      />
    </ChartCard>
  );
}

/* ------------------------------------------------------------------ health */

export function HealthCostCard({ health, className }: { health: HealthAnalytics; className?: string }) {
  const months = health.cost_monthly.map((m) => m.month);
  return (
    <ChartCard title="Health spending" subtitle="Treatment and vaccination costs, per month" empty={health.total_records === 0} emptyText="No health records in this period." className={className}>
      <BarChart
        ariaLabel="Health costs per month" showLegend={false} height={200} format={kes}
        categories={monthLabels(months)} tooltipTitles={monthTitles(months)}
        series={[{ name: "Cost", color: SEMANTIC.expense, values: health.cost_monthly.map((m) => toNumber(m.amount)) }]}
      />
    </ChartCard>
  );
}

export function HealthByTypeCard({ health, className }: { health: HealthAnalytics; className?: string }) {
  return (
    <ChartCard title="Health records by type" subtitle="In this period" empty={health.by_type.length === 0} emptyText="No health records in this period." className={className}>
      <DonutChart
        ariaLabel="Health records by type" centerLabel="Records" centerValue={count(health.total_records)}
        data={health.by_type.map((t, i) => ({ label: humanize(t.key), value: t.count, color: colorAt(i) }))}
      />
    </ChartCard>
  );
}
