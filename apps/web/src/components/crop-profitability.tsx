"use client";

import { Fragment, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { EmptyState, ErrorState } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import type { CropEconomicsReport, PlantingBreakdown, PlantingEconomics } from "@/lib/types";

const kes = (v: string | number | null | undefined) =>
  v === null || v === undefined || v === "" ? "-" : `KES ${Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
const qty = (v: string | number, unit?: string | null) => `${Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 })}${unit ? ` ${unit}` : ""}`;
const neg = (v: string | number) => Number(v) < 0;
type Filter = "all" | "closed" | "open";

export function CropProfitability() {
  const [filter, setFilter] = useState<Filter>("all");
  const [expanded, setExpanded] = useState<string | null>(null);
  const { data, isLoading, error } = useQuery<CropEconomicsReport>({
    queryKey: ["profitability-crops"],
    queryFn: () => apiFetch<CropEconomicsReport>("/api/v1/reports/profitability/crops"),
  });
  if (isLoading) return <p className="text-sm text-muted">Loading…</p>;
  if (error || !data) return <ErrorState message={error instanceof ApiError ? error.message : "Failed to load crop profitability"} />;
  if (data.plantings.length === 0) return <EmptyState title="No crop plantings yet" body="Crop profit appears once plantings exist. Record costs and sales on each planting's Money tab." />;

  const t = data.totals;
  const rows = data.plantings.filter((p) => (filter === "closed" ? p.is_closed : filter === "open" ? !p.is_closed : true));
  return (
    <>
      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Spent" value={kes(t.total_investment)} />
        <Stat label="Sold" value={kes(t.total_revenue)} hint={`web ${kes(t.revenue_web)} · direct ${kes(t.revenue_direct)}`} />
        <Stat label="Profit / loss so far" value={kes(t.profit)} negative={neg(t.profit)} hint="includes crops still growing" />
        <Stat label="Finished cycles" value={kes(t.closed_profit)} negative={neg(t.closed_profit)} hint={`${t.closed_plantings} of ${t.plantings} plantings finished`} />
      </div>

      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-display text-lg text-forest">All plantings</h2>
        <div className="flex gap-1 text-xs">
          {([["all", "All"], ["closed", "Finished"], ["open", "In progress"]] as [Filter, string][]).map(([k, label]) => (
            <button key={k} onClick={() => setFilter(k)}
              className={`rounded-full border px-3 py-1 ${filter === k ? "border-forest bg-forest text-paper" : "border-hairline bg-white/60 text-muted hover:text-ink"}`}>{label}</button>
          ))}
        </div>
      </div>

      <div className="overflow-x-auto rounded-lg border border-hairline">
        <table className="w-full text-left text-sm">
          <thead className="bg-forest text-paper"><tr>
            <th className="px-4 py-3 font-medium">Planting</th><th className="px-4 py-3 font-medium">Status</th><th className="px-4 py-3 font-medium">Spent</th>
            <th className="px-4 py-3 font-medium">Sold</th><th className="px-4 py-3 font-medium">Profit / loss</th><th className="px-4 py-3 font-medium">Stock left</th>
          </tr></thead>
          <tbody>
            {rows.map((p, i) => {
              const open = expanded === p.planting_id;
              return (
                <Fragment key={p.planting_id}>
                  <tr onClick={() => setExpanded(open ? null : p.planting_id)} className={`cursor-pointer hover:bg-forest/5 ${i % 2 === 0 ? "bg-white/40" : "bg-white/70"}`}>
                    <td className="px-4 py-3"><span className="mr-2 text-xs text-muted">{open ? "▾" : "▸"}</span>
                      <Link href={`/admin/crops/${p.planting_id}`} onClick={(e) => e.stopPropagation()} className="text-forest hover:underline">{p.planting_number}</Link>
                      <span className="ml-2 text-xs capitalize text-muted">{p.crop_type}{p.variety ? ` · ${p.variety}` : ""}</span></td>
                    <td className="px-4 py-3 text-xs capitalize text-muted">{p.status.replace(/_/g, " ")}{p.is_closed ? "" : " · in progress"}</td>
                    <td className="px-4 py-3 text-muted">{kes(p.total_investment)}</td>
                    <td className="px-4 py-3 text-muted">{kes(p.total_revenue)}</td>
                    <td className={`px-4 py-3 font-medium ${neg(p.profit) ? "text-clay" : "text-ink"}`}>{kes(p.profit)}</td>
                    <td className={`px-4 py-3 text-xs ${neg(p.stock_on_hand) ? "text-clay" : "text-muted"}`}>{qty(p.stock_on_hand, p.unit)}</td>
                  </tr>
                  {open && <tr className="bg-paper"><td colSpan={6} className="px-4 py-4"><Breakdown row={p} /></td></tr>}
                </Fragment>
              );
            })}
            {rows.length === 0 && <tr><td colSpan={6} className="px-4 py-6 text-center text-sm text-muted">No plantings match this filter.</td></tr>}
          </tbody>
        </table>
      </div>
    </>
  );
}

function Stat({ label, value, hint, negative }: { label: string; value: string; hint?: string; negative?: boolean }) {
  return (
    <div className="rounded-lg border border-hairline bg-white/60 px-4 py-3">
      <span className="text-xs uppercase tracking-wider text-muted">{label}</span>
      <p className={`font-display text-xl ${negative ? "text-clay" : "text-forest"}`}>{value}</p>
      {hint && <p className="text-xs text-muted">{hint}</p>}
    </div>
  );
}

function Breakdown({ row }: { row: PlantingEconomics }) {
  const { data } = useQuery<PlantingBreakdown>({
    queryKey: ["crop-planting", row.planting_id, "economics"],
    queryFn: () => apiFetch<PlantingBreakdown>(`/api/v1/crops/${row.planting_id}/economics`),
  });
  const live = (a: { voided_at: string | null }[]) => a.filter((x) => !x.voided_at).length;
  return (
    <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
      <div>
        <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-muted">What was spent</h3>
        <Lines lines={[["Planting cost", row.acquisition_cost], ["Seed, fertiliser, chemicals", row.input_cost], ["Labour", row.labour_cost], ["Other costs", row.other_cost]]} />
        <Total label="Total spent" value={row.total_investment} />
        {row.cost_per_unit && <p className="mt-1 px-3 text-xs text-muted">{kes(row.cost_per_unit)} per {row.unit ?? "unit"} harvested</p>}
        {data && <p className="mt-1 px-3 text-xs text-muted">{live(data.costs)} cost entr{live(data.costs) === 1 ? "y" : "ies"} recorded</p>}
      </div>
      <div>
        <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-muted">What came back</h3>
        <Lines lines={[
          [`Web shop (${qty(row.quantity_sold_web, row.unit)})`, row.revenue_web],
          [`Sold directly (${qty(row.quantity_sold_direct, row.unit)})`, row.revenue_direct],
        ]} />
        <Total label={row.is_closed ? "Final profit / loss" : "Profit / loss so far"} value={row.profit} negative={neg(row.profit)} />
        <p className="mt-2 px-3 text-xs text-muted">
          Harvested {qty(row.quantity_harvested, row.unit)} · stock left {qty(row.stock_on_hand, row.unit)}
          {row.stock_value ? ` (about ${kes(row.stock_value)} at the listed price: an estimate, not counted above)` : ""}
          {row.avg_price_per_unit ? ` · average price ${kes(row.avg_price_per_unit)}` : ""}
        </p>
        <p className="mt-2 px-3 text-xs"><Link href={`/admin/crops/${row.planting_id}`} className="text-forest underline">Open to record sales or costs</Link></p>
      </div>
    </div>
  );
}

function Lines({ lines }: { lines: [string, string][] }) {
  return (
    <ul className="divide-y divide-hairline rounded-lg border border-hairline bg-white/60">
      {lines.map(([label, amount]) => (
        <li key={label} className="flex items-center justify-between px-3 py-2"><span className="text-sm">{label}</span><span className="text-sm">{kes(amount)}</span></li>
      ))}
    </ul>
  );
}

function Total({ label, value, negative }: { label: string; value: string; negative?: boolean }) {
  return (
    <div className="mt-2 flex items-center justify-between px-3">
      <span className="text-sm font-medium">{label}</span>
      <span className={`font-display text-lg ${negative ? "text-clay" : "text-forest"}`}>{kes(value)}</span>
    </div>
  );
}
