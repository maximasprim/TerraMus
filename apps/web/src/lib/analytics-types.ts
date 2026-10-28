/** Mirrors reporting/analytics_schemas.py and platform_admin/analytics_schemas.py.
 *  Money arrives as decimal strings (like the rest of the API) - convert with toNumber(). */

export interface LabelCount { key: string; count: number }
export interface LabelAmount { key: string; amount: string }

// ---- tenant: GET /api/v1/reports/analytics ----
export interface MonthlyFinance { month: string; income: string; expense: string; net: string }
export interface FinanceAnalytics {
  monthly: MonthlyFinance[];
  total_income: string; total_expense: string; net: string;
  income_by_category: LabelAmount[]; expense_by_category: LabelAmount[];
}
export interface MonthlySales { month: string; orders: number; revenue: string; feedlot_head?: number; feedlot_revenue?: string; feedlot_purchase_head?: number; feedlot_purchases?: string }
export interface ProviderTotal { key: string; amount: string; count: number }
export interface SalesAnalytics {
  monthly: MonthlySales[]; orders_by_status: LabelCount[]; payments_by_provider: ProviderTotal[];
  total_orders: number; total_revenue: string; average_order_value: string;
  // animals sold outside the web shop (feedlot); optional so older API responses still type-check
  feedlot_head?: number; feedlot_revenue?: string; combined_revenue?: string;
  // bulls bought into the feedlot (by delivery date): the money out against feedlot_revenue
  feedlot_purchase_head?: number; feedlot_purchases?: string;
}
export interface HerdAnalytics { total: number; active: number; by_species: LabelCount[]; by_status: LabelCount[] }
export interface DailyMilk { date: string; liters: string }
export interface DairyAnalytics { daily: DailyMilk[]; total_liters: string; average_per_day: string; rejected_liters: string }
export interface CropTypeStat { key: string; plantings: number; area: string }
export interface HarvestUnitTotal { unit: string; quantity: string; records: number }
export interface MonthlyCount { month: string; count: number }
export interface CropAnalytics {
  total: number; active: number; by_status: LabelCount[]; by_type: CropTypeStat[];
  harvest_by_unit: HarvestUnitTotal[]; harvests_monthly: MonthlyCount[];
}
export interface InventoryCategoryStat { key: string; items: number; value: string }
export interface InventoryAnalytics { total_items: number; total_value: string; by_category: InventoryCategoryStat[] }
export interface MonthlyAmount { month: string; amount: string }
export interface HealthAnalytics { total_records: number; total_cost: string; by_type: LabelCount[]; cost_monthly: MonthlyAmount[] }

export interface AnalyticsReport {
  start_date: string; end_date: string; months: number; timezone: string;
  finance: FinanceAnalytics; sales: SalesAnalytics; herd: HerdAnalytics; dairy: DairyAnalytics;
  crops: CropAnalytics; inventory: InventoryAnalytics; health: HealthAnalytics;
}

// ---- superadmin: GET /api/v1/platform/analytics ----
export interface TierStat { key: string; count: number; mrr_kes: string }
export interface MonthlySignups { month: string; count: number; cumulative: number }
export interface MonthlyMoney { month: string; amount: string; payments: number }
export interface TopTenant {
  organization_id: string; name: string; is_suspended: boolean;
  users: number; animals: number; crop_plantings: number; orders: number; gmv: string;
}
export interface PlatformTotals {
  organizations: number; users: number; animals: number; crop_plantings: number; orders: number;
  mrr_kes: string; subscription_revenue: string; gmv: string;
}
export interface PlatformAnalytics {
  start_date: string; end_date: string; months: number; timezone: string;
  totals: PlatformTotals;
  signups_monthly: MonthlySignups[];
  organizations_by_status: LabelCount[];
  organizations_by_tier: TierStat[];
  subscriptions_by_status: LabelCount[];
  subscription_revenue_monthly: MonthlyMoney[];
  tenant_gmv_monthly: MonthlyMoney[];
  tenant_payments_by_provider: ProviderTotal[];
  species_distribution: LabelCount[];
  top_tenants: TopTenant[];
}
