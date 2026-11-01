export type CycleStatus = "planned" | "running" | "closed";
export const ENTERPRISES = ["feedlot", "fodder", "crops", "poultry", "fish", "rabbits", "training", "mixed"] as const;

export interface ProductionCycle {
  id: string;
  cycle_number: number;
  name: string;
  enterprise: string;
  status: CycleStatus;
  farm_id: string | null;
  start_date: string | null;
  end_date: string | null;
  closed_at: string | null;
  close_summary: Record<string, unknown> | null;
  notes: string | null;
  created_at: string;
  head_registered: number;
  head_active: number;
  intake_batches: number;
}

export interface CycleSummary {
  cycle: { id: string; name: string; cycle_number: number; enterprise: string; status: CycleStatus; start_date: string | null; end_date: string | null; days: number | null };
  as_of: string;
  feedlot: {
    head: number; active: number; sold: number; culled: number; died: number; market_ready: number; avg_adg_active: number | null; loss_rate_pct: number;
    revenue: number; landed_cost: number; feed_cost: number; ops_cost: number; total_cost: number; profit: number; profit_per_head: number;
    avg_adg: number | null; avg_days_on_farm: number | null; cost_per_kg_gain: number | null; head_realised: number; head_open: number; unrealised_projected_profit: number;
    by_intake_batch: { intake_batch: string; head_total: number; head_sold: number; head_active: number; profit: number; profit_per_head: number; avg_adg: number | null; loss_rate_pct: number }[];
  };
  finance: {
    income: number; expense: number; net: number;
    income_by_category: Record<string, number>; expense_by_category: Record<string, number>;
    shared_in_window?: { from: string; to: string; expense: number; income: number; note: string; estimated_share_of_expense?: number; method?: string };
  };
  receivables: { charged: number; collected: number; written_off: number; outstanding: number };
  fuel: { fills: number; litres: number; cost: number };
  groups: { groups: number; initial_count: number; current_count: number; acquisition_cost: number };
  fodder: { plantings: number; acres: number; harvested_kg: number; total_cost: number };
  crops: { plantings: number; area: number };
  training: { sessions: number; participants: number; fees_charged: number };
  inventory: { consumption_movements: number; consumption_value: number };
  procurement: { purchase_orders: number; value: number };
}

export interface CyclePreferences { default_view: "all" | "running"; default_cycle_id: string | null; running_cycles: number }

export interface CompareRow {
  id: string; name: string; cycle_number: number; status: CycleStatus; days: number | null; head: number; sold: number; loss_rate_pct: number;
  avg_adg: number | null; avg_days_on_farm: number | null; cost_per_kg_gain: number | null; revenue: number; total_cost: number; profit: number;
  profit_per_head: number; margin_pct: number | null; ledger_income: number; ledger_expense: number; ledger_net: number; outstanding_receivables: number;
}

export interface AssignReport {
  cycle: string; dry_run: boolean;
  intake_batches: { id: string; batch: number; from: string | null }[];
  sale_batches: { id: string; batch: number; from: string | null }[];
  tagged: Record<string, { label: string; records: number }>;
  skipped: { id: string; batch: number; reason: string }[];
}
