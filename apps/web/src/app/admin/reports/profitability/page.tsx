"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { AdminShell } from "@/components/admin-shell";
import { Card, ErrorState, EmptyState } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import type { ProfitabilityReport } from "@/lib/types";

export default function ProfitabilityReportPage() {
  const { data, isLoading, error } = useQuery<ProfitabilityReport>({
    queryKey: ["profitability"],
    queryFn: () => apiFetch<ProfitabilityReport>("/api/v1/reports/profitability"),
  });

  return (
    <AdminShell>
      <div className="mb-6">
        <h1 className="font-display text-2xl text-forest">Profitability</h1>
        <p className="text-sm text-muted">
          Per-animal investment vs. profit - actual for sold animals, estimated for the rest.
        </p>
      </div>

      {error && <ErrorState message={error instanceof ApiError ? error.message : "Failed to load report"} />}
      {isLoading && <p className="text-sm text-muted">Loading…</p>}
      {data && data.animals.length === 0 && <EmptyState title="No data yet" body="Profitability appears once animals have recorded costs." />}

      {data && data.animals.length > 0 && (
        <>
          {data.average_profit && (
            <div className="mb-4 rounded-lg border border-hairline bg-white/60 px-4 py-3">
              <span className="text-xs uppercase tracking-wider text-muted">Average profit per animal</span>
              <p className="font-display text-2xl text-forest">KES {Number(data.average_profit).toLocaleString()}</p>
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

          <h2 className="mb-3 font-display text-lg text-forest">All animals</h2>
          <div className="overflow-hidden rounded-lg border border-hairline">
            <table className="w-full text-left text-sm">
              <thead className="bg-forest text-paper">
                <tr>
                  <th className="px-4 py-3 font-medium">Animal</th>
                  <th className="px-4 py-3 font-medium">Investment</th>
                  <th className="px-4 py-3 font-medium">Sale price</th>
                  <th className="px-4 py-3 font-medium">Profit</th>
                  <th className="px-4 py-3 font-medium">Basis</th>
                </tr>
              </thead>
              <tbody>
                {data.animals.map((a, i) => (
                  <tr key={a.animal_id} className={i % 2 === 0 ? "bg-white/40" : "bg-white/70"}>
                    <td className="px-4 py-3">
                      <Link href={`/admin/livestock/${a.animal_id}`} className="text-forest hover:underline">
                        {a.animal_number}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-muted">KES {Number(a.total_investment).toLocaleString()}</td>
                    <td className="px-4 py-3 text-muted">
                      {a.sale_price ? `KES ${Number(a.sale_price).toLocaleString()}` : a.expected_sale_price ? `~KES ${Number(a.expected_sale_price).toLocaleString()}` : "-"}
                    </td>
                    <td className={`px-4 py-3 font-medium ${a.profit && Number(a.profit) < 0 ? "text-clay" : "text-ink"}`}>
                      {a.profit ? `KES ${Number(a.profit).toLocaleString()}` : "-"}
                    </td>
                    <td className="px-4 py-3 text-xs text-muted">{a.is_actual ? "Actual" : "Estimated"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </AdminShell>
  );
}

function ProfitCard({ row }: { row: ProfitabilityReport["animals"][number] }) {
  return (
    <Card>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-ink">{row.animal_number}</p>
          <p className="text-xs text-muted">{row.is_actual ? "Actual" : "Estimated"}</p>
        </div>
        <p className={`font-display text-lg ${row.profit && Number(row.profit) < 0 ? "text-clay" : "text-forest"}`}>
          {row.profit ? `KES ${Number(row.profit).toLocaleString()}` : "-"}
        </p>
      </div>
    </Card>
  );
}
