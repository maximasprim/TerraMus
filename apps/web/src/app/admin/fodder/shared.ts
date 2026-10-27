import { ApiError } from "@/lib/api";

export interface Product { id: string; name: string; category: string; unit_label: string; kg_per_unit: number; reorder_days: number; is_active: boolean; current_price_per_kg: number | null }
export interface Plot { id: string; name: string; acres: number; acres_in_use: number; acres_free: number; irrigated: boolean; crop: string | null; status: string; farm_id: string | null }
export interface Econ {
  harvested_kg: number; harvested_units: number | null; direct_cost: number; amortised_cost: number; total_cost: number; cost_per_kg: number | null; cost_per_unit: number | null;
  cost_per_acre: number | null; yield_kg_per_acre: number | null; replacement_value: number; saving_vs_buying: number | null; unpriced_kg: number;
  cost_per_kg_vs_budget_pct?: number; yield_vs_target_pct?: number;
}
export interface Cycle {
  id: string; label: string; plot: string; plot_id: string; product: string; product_id: string; unit_label: string; start_date: string; end_date: string | null;
  acres: number; status: string; budget_name: string | null; economics: Econ | null;
}
export interface CycleDetail extends Cycle {
  costs: { id: string; date: string; category: string; amount: number; description: string | null }[];
  harvests: { id: string; date: string; quantity: number; kg: number; quality: string | null }[];
  cost_by_category: Record<string, number>;
}
export interface StockRow {
  product_id: string; name: string; unit_label: string; is_active: boolean; balance_kg: number; balance_units: number; avg_cost_per_kg: number | null; stock_value: number | null;
  market_price_per_kg: number | null; replacement_value: number | null; issued_last_30d_kg: number; days_of_cover: number | null; reorder_days: number; low_cover: boolean;
}
export interface Investment {
  id: string; name: string; plot_id: string | null; shared: boolean; cost: number; in_service_on: string; life_years: number; disposed_on: string | null; per_year: number;
  per_day: number; amortised_to_date: number; book_value: number; allocated_to_cycles?: number; idle_capacity_cost?: number;
}
export interface Schedule { totals: { cost: number; amortised_to_date: number; book_value: number; per_year: number; allocated_to_cycles: number; idle_capacity_cost: number }; investments: Investment[] }
export interface Summary {
  production: { total_cost: number; replacement_value: number; saving_vs_buying: number };
  products: { product: string; harvested_kg: number; purchased_kg: number; issued_kg: number; lost_kg: number; loss_pct_of_inflow: number | null; self_sufficiency_pct: number | null }[];
}

export const money = (n: number | null | undefined, d = 0) => (n == null ? "-" : new Intl.NumberFormat("en-KE", { maximumFractionDigits: d, minimumFractionDigits: d }).format(n));
export const errMsg = (e: unknown, f: string) => (e instanceof ApiError ? e.message : f);
export const todayIso = () => new Date().toISOString().slice(0, 10);
export const COST_CATEGORIES = ["seed", "fertilizer", "chemicals", "labour", "fuel", "machinery_hire", "irrigation", "transport", "packaging", "other"] as const;
