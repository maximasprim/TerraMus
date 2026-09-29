"use client";

import { useQuery } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { ErrorState, EmptyState } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import type { ValuationRow } from "@/lib/types";

export default function InventoryValuationPage() {
  const { data, isLoading, error } = useQuery<ValuationRow[]>({
    queryKey: ["inventory-valuation"],
    queryFn: () => apiFetch<ValuationRow[]>("/api/v1/inventory/valuation"),
  });

  const totalValue = data?.reduce((sum, r) => sum + Number(r.total_value), 0) ?? 0;

  return (
    <AdminShell>
      <div className="mb-6">
        <h1 className="font-display text-2xl text-forest">Inventory valuation</h1>
        <p className="text-sm text-muted">
          FIFO-costed - value reflects the actual purchase batches still on hand, oldest first.
        </p>
      </div>

      {error && <ErrorState message={error instanceof ApiError ? error.message : "Failed to load valuation"} />}
      {isLoading && <p className="text-sm text-muted">Loading…</p>}
      {data && data.length === 0 && <EmptyState title="No inventory items yet" body="Nothing to value." />}

      {data && data.length > 0 && (
        <>
          <div className="mb-4 rounded-lg border border-hairline bg-white/60 px-4 py-3">
            <span className="text-xs uppercase tracking-wider text-muted">Total inventory value</span>
            <p className="font-display text-2xl text-forest">KES {totalValue.toLocaleString()}</p>
          </div>
          <div className="overflow-hidden rounded-lg border border-hairline">
            <table className="w-full text-left text-sm">
              <thead className="bg-forest text-paper">
                <tr>
                  <th className="px-4 py-3 font-medium">Item</th>
                  <th className="px-4 py-3 font-medium">On hand</th>
                  <th className="px-4 py-3 font-medium">Priced quantity</th>
                  <th className="px-4 py-3 font-medium">Avg unit cost</th>
                  <th className="px-4 py-3 font-medium">Total value</th>
                </tr>
              </thead>
              <tbody>
                {data.map((row, i) => (
                  <tr key={row.item_id} className={i % 2 === 0 ? "bg-white/40" : "bg-white/70"}>
                    <td className="px-4 py-3 font-medium text-ink">{row.item_name}</td>
                    <td className="px-4 py-3 text-muted">{row.quantity_on_hand} {row.unit}</td>
                    <td className="px-4 py-3 text-muted">{row.priced_quantity} {row.unit}</td>
                    <td className="px-4 py-3 text-muted">
                      {row.avg_unit_cost ? `KES ${Number(row.avg_unit_cost).toLocaleString()}` : "Unknown"}
                    </td>
                    <td className="px-4 py-3 font-medium text-ink">KES {Number(row.total_value).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.some((r) => Number(r.priced_quantity) < Number(r.quantity_on_hand)) && (
            <p className="mt-3 text-xs text-muted">
              Some stock on hand has no purchase-cost history behind it (e.g. an old opening balance recorded
              without a unit cost) - its quantity is included in "on hand" but excluded from "priced quantity" and value.
            </p>
          )}
        </>
      )}
    </AdminShell>
  );
}
