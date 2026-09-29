"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { Card, StatusBadge, ErrorState, Button } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import type { PurchaseOrderDetail, Supplier } from "@/lib/types";

const PO_TRANSITIONS: Record<string, string[]> = {
  requested: ["approved", "rejected", "cancelled"],
  approved: ["ordered", "cancelled"],
  ordered: ["received", "cancelled"],
  received: ["invoiced"],
  invoiced: ["paid"],
  paid: [],
  rejected: [],
  cancelled: [],
};

export default function PurchaseOrderDetailPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [statusError, setStatusError] = useState<string | null>(null);

  const poQuery = useQuery<PurchaseOrderDetail>({
    queryKey: ["purchase-order", id],
    queryFn: () => apiFetch<PurchaseOrderDetail>(`/api/v1/procurement/purchase-orders/${id}`),
  });
  const suppliersQuery = useQuery<Supplier[]>({
    queryKey: ["suppliers"],
    queryFn: () => apiFetch<Supplier[]>("/api/v1/procurement/suppliers"),
  });

  const changeStatus = useMutation({
    mutationFn: (status: string) =>
      apiFetch(`/api/v1/procurement/purchase-orders/${id}/status`, {
        method: "PATCH", body: JSON.stringify({ status }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["purchase-order", id] });
      queryClient.invalidateQueries({ queryKey: ["purchase-orders"] });
      queryClient.invalidateQueries({ queryKey: ["inventory-items"] });
      setStatusError(null);
    },
    onError: (err) => setStatusError(err instanceof ApiError ? err.message : "Failed to change status"),
  });

  if (poQuery.error) {
    return (
      <AdminShell>
        <ErrorState message={poQuery.error instanceof ApiError ? poQuery.error.message : "Failed to load purchase order"} />
      </AdminShell>
    );
  }
  if (!poQuery.data) {
    return (
      <AdminShell>
        <p className="text-sm text-muted">Loading…</p>
      </AdminShell>
    );
  }

  const po = poQuery.data;
  const supplier = suppliersQuery.data?.find((s) => s.id === po.supplier_id);
  const nextStatuses = PO_TRANSITIONS[po.status] ?? [];

  return (
    <AdminShell>
      <div className="mb-6 flex items-start justify-between">
        <div>
          <div className="mb-2"><StatusBadge status={po.status} /></div>
          <h1 className="font-display text-2xl text-forest">{po.po_number}</h1>
          <p className="text-sm text-muted">{supplier?.name ?? "Unknown supplier"}</p>
        </div>
        <div className="text-right">
          <p className="text-xs uppercase tracking-wider text-muted">Total</p>
          <p className="font-display text-2xl text-forest">KES {Number(po.total_amount).toLocaleString()}</p>
        </div>
      </div>

      {nextStatuses.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <span className="text-xs uppercase tracking-wider text-muted">Advance:</span>
          {nextStatuses.map((next) => (
            <Button
              key={next}
              variant="ghost"
              className="px-3 py-1 text-xs capitalize"
              disabled={changeStatus.isPending}
              onClick={() => changeStatus.mutate(next)}
            >
              → {next.replace(/_/g, " ")}
            </Button>
          ))}
        </div>
      )}
      {statusError && <div className="mb-4"><ErrorState message={statusError} /></div>}
      {po.status === "ordered" && (
        <p className="mb-4 text-xs text-muted">
          Marking this "received" will post a real stock movement for every line linked to a tracked inventory item.
        </p>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card>
          <h2 className="mb-3 font-display text-lg text-forest">Line items</h2>
          <div className="space-y-2 text-sm">
            {po.items.map((item) => (
              <div key={item.id} className="flex justify-between border-b border-hairline/60 pb-2">
                <span className="text-ink">{item.description}</span>
                <span className="font-medium text-ink">
                  {item.quantity} × KES {Number(item.unit_cost).toLocaleString()}
                </span>
              </div>
            ))}
          </div>
          {po.notes && <p className="mt-3 border-t border-hairline pt-3 text-sm text-muted">{po.notes}</p>}
        </Card>

        <Card>
          <h2 className="mb-3 font-display text-lg text-forest">Status history</h2>
          {po.status_history.length === 0 ? (
            <p className="text-sm text-muted">No status changes yet.</p>
          ) : (
            <ol className="relative space-y-4 border-l border-hairline pl-6">
              {po.status_history.map((event, i) => (
                <li key={i} className="relative">
                  <span className="absolute -left-[27px] top-1 h-2.5 w-2.5 rounded-full bg-brass" />
                  <p className="text-sm font-medium capitalize text-ink">
                    {event.from_status ? `${event.from_status.replace(/_/g, " ")} → ` : ""}
                    {event.to_status.replace(/_/g, " ")}
                  </p>
                  <p className="text-xs text-muted">{new Date(event.changed_at).toLocaleString()}</p>
                  {event.reason && <p className="text-xs text-muted">{event.reason}</p>}
                </li>
              ))}
            </ol>
          )}
        </Card>
      </div>
    </AdminShell>
  );
}
