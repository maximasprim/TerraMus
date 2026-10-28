"use client";

import { Fragment, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { AdminShell } from "@/components/admin-shell";
import { Card, ErrorState, EmptyState } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import type { AnimalProfitabilityBreakdown, AnimalProfitabilityDetail, ProfitabilityReport } from "@/lib/types";

type Row = AnimalProfitabilityDetail;
type Filter = "all" | "sold" | "loss" | "active";

const kes = (v: string | number | null | undefined) =>
  v === null || v === undefined || v === "" ? "-" : `KES ${Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
const num = (v: string | number | null | undefined, digits = 1) =>
  v === null || v === undefined || v === "" ? "-" : Number(v).toLocaleString(undefined, { maximumFractionDigits: digits });
const isLoss = (v: string | null) => v !== null && Number(v) < 0;
const outcomeOf = (r: Row) => r.outcome ?? (r.is_actual ? "sold" : "active");

function basisLabel(r: Row): string {
  if (r.estimate_source === "sale_price_missing") return "Sold - price not recorded";
  if (outcomeOf(r) === "culled" || outcomeOf(r) === "died") return "Actual loss";
  if (r.is_actual) return r.sale_channel === "feedlot" ? "Actual (feedlot sale)" : "Actual";
  if (r.estimate_source === "feedlot_projection") return "Projected from weight";
  return "Estimated";
}

function salePriceCell(r: Row): string {
  const o = outcomeOf(r);
  if (r.sale_price) return kes(r.sale_price);
  if (o === "culled" || o === "died") return "No sale";
  if (r.estimate_source === "sale_price_missing") return "Price not set";
  if (r.expected_sale_price) return `~${kes(r.expected_sale_price)}`;
  return "-";
}

const OUTCOME_STYLE: Record<string, string> = {
  sold: "bg-forest/10 text-forest",
  culled: "bg-clay/15 text-clay",
  died: "bg-clay/15 text-clay",
  active: "bg-black/5 text-muted",
};
const OUTCOME_LABEL: Record<string, string> = { sold: "Sold", culled: "Culled", died: "Died", active: "On farm" };

export default function ProfitabilityReportPage() {
  const [filter, setFilter] = useState<Filter>("all");
  const [expanded, setExpanded] = useState<string | null>(null);
  const { data, isLoading, error } = useQuery<ProfitabilityReport>({
    queryKey: ["profitability"],
    queryFn: () => apiFetch<ProfitabilityReport>("/api/v1/reports/profitability"),
  });

  const rows = (data?.animals ?? []).filter((a) => {
    const o = outcomeOf(a);
    if (filter === "sold") return o === "sold";
    if (filter === "loss") return o === "culled" || o === "died";
    if (filter === "active") return o === "active";
    return true;
  });
  const totals = data?.totals;

  return (
    <AdminShell>
      <div className="mb-6">
        <h1 className="font-display text-2xl text-forest">Profitability</h1>
        <p className="text-sm text-muted">
          Per-animal investment vs. profit - actual for sold animals (web orders and sales recorded in the feedlot),
          losses for culled or dead animals, estimated for the rest. Click a row to see what went in and what came back.
        </p>
      </div>

      {error && <ErrorState message={error instanceof ApiError ? error.message : "Failed to load report"} />}
      {isLoading && <p className="text-sm text-muted">Loading…</p>}
      {data && data.animals.length === 0 && <EmptyState title="No data yet" body="Profitability appears once animals have recorded costs." />}

      {data && data.animals.length > 0 && (
        <>
          {totals && (
            <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
              <Stat label="Realised revenue" value={kes(totals.realised_revenue)} />
              <Stat label="Realised cost" value={kes(totals.realised_cost)} />
              <Stat label="Realised profit" value={kes(totals.realised_profit)} negative={isLoss(totals.realised_profit)} />
              <Stat
                label="Lost on culled / died"
                value={kes(totals.loss_from_culled_died)}
                negative={isLoss(totals.loss_from_culled_died)}
                hint={`${totals.head_culled} culled, ${totals.head_died} died`}
              />
            </div>
          )}
          {totals && (
            <p className="mb-4 text-xs text-muted">
              {totals.head_sold} sold · {totals.head_culled + totals.head_died} culled or died · {totals.head_active} still on the farm
              {totals.by_channel.length > 0 && " · "}
              {totals.by_channel
                .map((c) => `${c.channel === "web" ? "Web shop" : "Feedlot / manual"}: ${c.head} sold, ${kes(c.profit)} profit`)
                .join(" · ")}
            </p>
          )}

          {data.average_profit && (
            <div className="mb-4 rounded-lg border border-hairline bg-white/60 px-4 py-3">
              <span className="text-xs uppercase tracking-wider text-muted">Average profit per animal (actual and estimated)</span>
              <p className="font-display text-2xl text-forest">{kes(data.average_profit)}</p>
            </div>
          )}

          <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-2">
            <div>
              <h2 className="mb-2 font-display text-lg text-forest">Most profitable</h2>
              <div className="space-y-2">
                {data.most_profitable.map((a) => (
                  <ProfitCard key={a.animal_id} row={a} />
                ))}
              </div>
            </div>
            <div>
              <h2 className="mb-2 font-display text-lg text-forest">Least profitable</h2>
              <div className="space-y-2">
                {data.least_profitable.map((a) => (
                  <ProfitCard key={a.animal_id} row={a} />
                ))}
              </div>
            </div>
          </div>

          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-display text-lg text-forest">All animals</h2>
            <div className="flex gap-1 text-xs">
              {(
                [
                  ["all", "All"],
                  ["sold", "Sold"],
                  ["loss", "Culled / died"],
                  ["active", "On farm"],
                ] as [Filter, string][]
              ).map(([key, label]) => (
                <button
                  key={key}
                  onClick={() => setFilter(key)}
                  className={`rounded-full border px-3 py-1 ${filter === key ? "border-forest bg-forest text-paper" : "border-hairline bg-white/60 text-muted hover:text-ink"}`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div className="overflow-x-auto rounded-lg border border-hairline">
            <table className="w-full text-left text-sm">
              <thead className="bg-forest text-paper">
                <tr>
                  <th className="px-4 py-3 font-medium">Animal</th>
                  <th className="px-4 py-3 font-medium">Outcome</th>
                  <th className="px-4 py-3 font-medium">Investment</th>
                  <th className="px-4 py-3 font-medium">Sale price</th>
                  <th className="px-4 py-3 font-medium">Profit</th>
                  <th className="px-4 py-3 font-medium">Basis</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((a, i) => {
                  const open = expanded === a.animal_id;
                  const o = outcomeOf(a);
                  return (
                    <Fragment key={a.animal_id}>
                      <tr
                        onClick={() => setExpanded(open ? null : a.animal_id)}
                        className={`cursor-pointer hover:bg-forest/5 ${i % 2 === 0 ? "bg-white/40" : "bg-white/70"}`}
                      >
                        <td className="px-4 py-3">
                          <span className="mr-2 text-xs text-muted">{open ? "▾" : "▸"}</span>
                          <Link
                            href={`/admin/livestock/${a.animal_id}`}
                            onClick={(e) => e.stopPropagation()}
                            className="text-forest hover:underline"
                          >
                            {a.animal_number}
                          </Link>
                        </td>
                        <td className="px-4 py-3">
                          <span className={`rounded-full px-2 py-0.5 text-xs ${OUTCOME_STYLE[o] ?? OUTCOME_STYLE.active}`}>{OUTCOME_LABEL[o] ?? o}</span>
                        </td>
                        <td className="px-4 py-3 text-muted">{kes(a.total_investment)}</td>
                        <td className="px-4 py-3 text-muted">{salePriceCell(a)}</td>
                        <td className={`px-4 py-3 font-medium ${isLoss(a.profit) ? "text-clay" : "text-ink"}`}>{kes(a.profit)}</td>
                        <td className="px-4 py-3 text-xs text-muted">{basisLabel(a)}</td>
                      </tr>
                      {open && (
                        <tr className="bg-paper">
                          <td colSpan={6} className="px-4 py-4">
                            <Breakdown animalId={a.animal_id} />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
                {rows.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-4 py-6 text-center text-sm text-muted">
                      No animals match this filter.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </AdminShell>
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

function Breakdown({ animalId }: { animalId: string }) {
  const { data, isLoading, error } = useQuery<AnimalProfitabilityBreakdown>({
    queryKey: ["profitability-breakdown", animalId],
    queryFn: () => apiFetch<AnimalProfitabilityBreakdown>(`/api/v1/reports/profitability/animals/${animalId}`),
  });
  if (isLoading) return <p className="text-sm text-muted">Loading breakdown…</p>;
  if (error || !data) return <ErrorState message={error instanceof ApiError ? error.message : "Failed to load breakdown"} />;

  const s = data.summary;
  const hasGrowth = s.entry_weight_kg || s.end_weight_kg || s.days_on_farm;
  return (
    <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
      <div>
        <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-muted">What was used</h3>
        <Lines lines={data.costs} />
        <Total label="Total cost" value={data.total_cost} />
      </div>
      <div>
        <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-muted">
          {data.net_is_actual ? "What came back" : "What is expected back"}
        </h3>
        {data.returns.length > 0 ? <Lines lines={data.returns} /> : <p className="text-sm text-muted">Nothing recorded yet.</p>}
        <Total label={data.net_is_actual ? "Net profit / loss" : "Projected profit / loss"} value={data.net} negative={isLoss(data.net)} />
        {data.reason && <p className="mt-2 text-xs text-muted">Reason: {data.reason}</p>}
      </div>

      {hasGrowth && (
        <div className="md:col-span-2">
          <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-muted">Growth</h3>
          <div className="grid grid-cols-2 gap-3 text-sm md:grid-cols-6">
            <Fact label="Entry weight" value={s.entry_weight_kg ? `${num(s.entry_weight_kg)} kg` : "-"} />
            <Fact label={outcomeOf(s) === "active" ? "Latest weight" : "Exit weight"} value={s.end_weight_kg ? `${num(s.end_weight_kg)} kg` : "-"} />
            <Fact label="Gain" value={s.weight_gain_kg ? `${num(s.weight_gain_kg)} kg` : "-"} />
            <Fact label="Days on farm" value={s.days_on_farm != null ? String(s.days_on_farm) : "-"} />
            <Fact label="Daily gain" value={s.avg_daily_gain_kg ? `${num(s.avg_daily_gain_kg, 2)} kg` : "-"} />
            <Fact label="Break-even price" value={s.breakeven_price_per_kg ? `KES ${num(s.breakeven_price_per_kg, 0)}/kg` : "-"} />
          </div>
          {data.weight_history.length > 0 && (
            <p className="mt-2 text-xs text-muted">
              {data.weight_history.length} weigh interval{data.weight_history.length === 1 ? "" : "s"}:{" "}
              {data.weight_history.map((w) => `${w.end}: +${num(w.gain_kg)} kg`).join(" · ")}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function Lines({ lines }: { lines: AnimalProfitabilityBreakdown["costs"] }) {
  return (
    <ul className="divide-y divide-hairline rounded-lg border border-hairline bg-white/60">
      {lines.map((l) => (
        <li key={l.category + l.label} className="flex items-start justify-between gap-4 px-3 py-2">
          <div>
            <p className="text-sm text-ink">{l.label}</p>
            {l.note && <p className="text-xs text-muted">{l.note}</p>}
          </div>
          <p className="whitespace-nowrap text-sm text-ink">{kes(l.amount)}</p>
        </li>
      ))}
    </ul>
  );
}

function Total({ label, value, negative }: { label: string; value: string | null; negative?: boolean }) {
  return (
    <div className="mt-2 flex items-center justify-between px-3">
      <span className="text-sm font-medium text-ink">{label}</span>
      <span className={`font-display text-lg ${negative ? "text-clay" : "text-forest"}`}>{kes(value)}</span>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-muted">{label}</p>
      <p className="text-ink">{value}</p>
    </div>
  );
}

function ProfitCard({ row }: { row: Row }) {
  const o = outcomeOf(row);
  return (
    <Card>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-ink">{row.animal_number}</p>
          <p className="text-xs text-muted">
            {OUTCOME_LABEL[o] ?? o} · {basisLabel(row)}
          </p>
        </div>
        <p className={`font-display text-lg ${isLoss(row.profit) ? "text-clay" : "text-forest"}`}>{kes(row.profit)}</p>
      </div>
    </Card>
  );
}
