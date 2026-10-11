import type { CsvCell } from "@/components/charts";
import { humanize, toNumber } from "@/components/charts";
import type { AnalyticsReport, PlatformAnalytics } from "@/lib/analytics-types";

export type TenantSection = "finance" | "sales" | "herd" | "dairy" | "crops" | "inventory" | "health";

const num = (v: string | number) => toNumber(v);
const table = (title: string, header: string[], rows: CsvCell[][]): CsvCell[][] => [[title], header, ...rows, []];

/** Rows for one report section, ready for downloadCsv(). Figures are plain numbers so spreadsheets can sum them. */
export function tenantSectionRows(report: AnalyticsReport, section: TenantSection): CsvCell[][] {
  const period: CsvCell[][] = [[`Period: ${report.start_date} to ${report.end_date} (${report.timezone})`], []];
  switch (section) {
    case "finance":
      return [
        ...period,
        ...table("Monthly", ["Month", "Income", "Expenses", "Net"], report.finance.monthly.map((m) => [m.month, num(m.income), num(m.expense), num(m.net)])),
        ...table("Income by category", ["Category", "Amount"], report.finance.income_by_category.map((c) => [humanize(c.key), num(c.amount)])),
        ...table("Expenses by category", ["Category", "Amount"], report.finance.expense_by_category.map((c) => [humanize(c.key), num(c.amount)])),
      ];
    case "sales":
      return [
        ...period,
        ...table("Monthly (paid orders)", ["Month", "Orders", "Revenue"], report.sales.monthly.map((m) => [m.month, m.orders, num(m.revenue)])),
        ...table("Orders by status", ["Status", "Orders"], report.sales.orders_by_status.map((s) => [humanize(s.key), s.count])),
        ...table("Payments by method", ["Method", "Payments", "Amount"], report.sales.payments_by_provider.map((p) => [humanize(p.key), p.count, num(p.amount)])),
      ];
    case "herd":
      return [
        ...table("Active herd by species", ["Species", "Animals"], report.herd.by_species.map((s) => [humanize(s.key), s.count])),
        ...table("All animals by status", ["Status", "Animals"], report.herd.by_status.map((s) => [humanize(s.key), s.count])),
      ];
    case "dairy":
      return table("Milk per day (last 30 days, rejected milk excluded)", ["Date", "Litres"], report.dairy.daily.map((d) => [d.date, num(d.liters)]));
    case "crops":
      return [
        ...table("Active plantings by crop", ["Crop", "Plantings", "Area"], report.crops.by_type.map((c) => [humanize(c.key), c.plantings, num(c.area)])),
        ...table("Plantings by status", ["Status", "Plantings"], report.crops.by_status.map((s) => [humanize(s.key), s.count])),
        ...table("Harvest totals by unit", ["Unit", "Quantity", "Records"], report.crops.harvest_by_unit.map((u) => [u.unit, num(u.quantity), u.records])),
        ...table("Harvest records per month", ["Month", "Records"], report.crops.harvests_monthly.map((m) => [m.month, m.count])),
      ];
    case "inventory":
      return table("Inventory by category", ["Category", "Items", "Value"], report.inventory.by_category.map((c) => [humanize(c.key), c.items, num(c.value)]));
    case "health":
      return [
        ...period,
        ...table("Records by type", ["Type", "Records"], report.health.by_type.map((t) => [humanize(t.key), t.count])),
        ...table("Cost per month", ["Month", "Cost"], report.health.cost_monthly.map((m) => [m.month, num(m.amount)])),
      ];
  }
}

export function platformRows(data: PlatformAnalytics): CsvCell[][] {
  return [
    [`Period: ${data.start_date} to ${data.end_date} (${data.timezone})`],
    [],
    ...table("Signups", ["Month", "New organizations", "Total organizations"], data.signups_monthly.map((m) => [m.month, m.count, m.cumulative])),
    ...table("Subscription revenue collected", ["Month", "Amount (KES)", "Payments"], data.subscription_revenue_monthly.map((m) => [m.month, num(m.amount), m.payments])),
    ...table("Tenant sales volume (GMV)", ["Month", "Amount (KES)", "Payments"], data.tenant_gmv_monthly.map((m) => [m.month, num(m.amount), m.payments])),
    ...table("Organizations by plan", ["Plan", "Organizations", "MRR (KES)"], data.organizations_by_tier.map((t) => [t.key, t.count, num(t.mrr_kes)])),
    ...table("Top tenants", ["Organization", "Status", "Users", "Animals", "Plantings", "Orders", "GMV in period (KES)"],
      data.top_tenants.map((t) => [t.name, t.is_suspended ? "Suspended" : "Active", t.users, t.animals, t.crop_plantings, t.orders, num(t.gmv)])),
  ];
}
