"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { Card, Input, ErrorState, EmptyState } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import type { SearchResult } from "@/lib/types";

const TYPE_LABELS: Record<string, string> = {
  animal: "Animal", customer: "Customer", order: "Order", invoice: "Invoice",
  supplier: "Supplier", inventory_item: "Inventory item", employee: "Employee", asset: "Asset",
  crop_planting: "Crop planting",
};

/** Only types with an actual detail page get a link - search surfaces
 * every entity type the backend covers, but not every entity has its own
 * detail route in apps/web yet (e.g. suppliers and invoices are list-only
 * so far). Null means "shown, not clickable" rather than a broken link. */
function detailHref(result: SearchResult): string | null {
  switch (result.type) {
    case "animal": return `/admin/livestock/${result.id}`;
    case "crop_planting": return `/admin/crops/${result.id}`;
    case "order": return `/admin/orders/${result.id}`;
    case "inventory_item": return `/admin/inventory/${result.id}`;
    case "employee": return `/admin/employees/${result.id}`;
    case "asset": return `/admin/assets/${result.id}`;
    default: return null;
  }
}

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");

  const { data, isLoading, error } = useQuery<SearchResult[]>({
    queryKey: ["search", submitted],
    queryFn: () => apiFetch<SearchResult[]>(`/api/v1/search?q=${encodeURIComponent(submitted)}`),
    enabled: submitted.length >= 2,
  });

  return (
    <AdminShell>
      <div className="mb-6">
        <h1 className="font-display text-2xl text-forest">Search</h1>
        <p className="text-sm text-muted">Animal IDs, ear tags, crop plantings, customers, orders, invoices, suppliers, inventory, staff, assets.</p>
      </div>

      <form
        onSubmit={(e) => { e.preventDefault(); setSubmitted(query.trim()); }}
        className="mb-6 max-w-lg"
      >
        <Input
          placeholder="Search everything…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </form>

      {error && <ErrorState message={error instanceof ApiError ? error.message : "Search failed"} />}
      {isLoading && <p className="text-sm text-muted">Searching…</p>}
      {submitted.length > 0 && submitted.length < 2 && (
        <p className="text-sm text-muted">Type at least 2 characters.</p>
      )}
      {data && data.length === 0 && (
        <EmptyState title="No results" body={`Nothing matched "${submitted}".`} />
      )}

      {data && data.length > 0 && (
        <div className="space-y-2">
          {data.map((result) => {
            const href = detailHref(result);
            const content = (
              <Card className="flex items-center justify-between">
                <div>
                  <p className="font-medium text-ink">{result.label}</p>
                  {result.subtitle && <p className="text-xs text-muted">{result.subtitle}</p>}
                </div>
                <span className="rounded-full border border-hairline bg-paper px-2 py-0.5 text-xs text-muted">
                  {TYPE_LABELS[result.type] ?? result.type}
                </span>
              </Card>
            );
            return href ? (
              <Link key={`${result.type}-${result.id}`} href={href}>{content}</Link>
            ) : (
              <div key={`${result.type}-${result.id}`}>{content}</div>
            );
          })}
        </div>
      )}
    </AdminShell>
  );
}
