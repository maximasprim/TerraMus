"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { Card, Button, Input, Select, Modal, ErrorState } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import type { InventoryItem, StockMovement } from "@/lib/types";

const MOVEMENT_TYPES = [
  "purchase", "sale", "consumption", "transfer", "adjustment",
  "wastage", "return", "expired", "opening_balance",
] as const;

export default function InventoryItemDetailPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const itemsQuery = useQuery<InventoryItem[]>({
    queryKey: ["inventory-items"],
    queryFn: () => apiFetch<InventoryItem[]>("/api/v1/inventory/items"),
  });
  const movementsQuery = useQuery<StockMovement[]>({
    queryKey: ["inventory-item", id, "movements"],
    queryFn: () => apiFetch<StockMovement[]>(`/api/v1/inventory/items/${id}/movements`),
  });

  const recordMovement = useMutation({
    mutationFn: (body: { movement_type: string; quantity: string; unit_cost?: string; notes?: string }) =>
      apiFetch(`/api/v1/inventory/items/${id}/movements`, { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["inventory-item", id, "movements"] });
      queryClient.invalidateQueries({ queryKey: ["inventory-items"] });
      setModalOpen(false);
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Failed to record movement"),
  });

  const item = itemsQuery.data?.find((i) => i.id === id);

  return (
    <AdminShell>
      {item && (
        <div className="mb-6 flex items-start justify-between">
          <div>
            <h1 className="font-display text-2xl text-forest">{item.name}</h1>
            <p className="text-sm capitalize text-muted">
              {item.category} · reorder at {item.reorder_level} {item.unit}
            </p>
          </div>
          <div className="text-right">
            <p className="text-xs uppercase tracking-wider text-muted">Current stock</p>
            <p className="font-display text-2xl text-forest">
              {item.current_stock} {item.unit}
            </p>
          </div>
        </div>
      )}

      <div className="mb-4 flex justify-end">
        <Button onClick={() => { setError(null); setModalOpen(true); }}>+ Record movement</Button>
      </div>

      <Card>
        {movementsQuery.isLoading && <p className="text-sm text-muted">Loading…</p>}
        {movementsQuery.data && movementsQuery.data.length === 0 && (
          <p className="text-sm text-muted">No movements recorded yet.</p>
        )}
        {movementsQuery.data && movementsQuery.data.length > 0 && (
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-hairline text-xs uppercase tracking-wider text-muted">
                <th className="pb-2 font-medium">Date</th>
                <th className="pb-2 font-medium">Type</th>
                <th className="pb-2 font-medium">Quantity</th>
                <th className="pb-2 font-medium">Unit cost</th>
                <th className="pb-2 font-medium">Notes</th>
              </tr>
            </thead>
            <tbody>
              {movementsQuery.data.map((m) => (
                <tr key={m.id} className="border-b border-hairline/60 last:border-0">
                  <td className="py-2">{new Date(m.moved_at).toLocaleDateString()}</td>
                  <td className="py-2 capitalize">{m.movement_type.replace(/_/g, " ")}</td>
                  <td className={`py-2 font-medium ${Number(m.quantity) < 0 ? "text-clay" : "text-moss"}`}>
                    {Number(m.quantity) > 0 ? "+" : ""}
                    {m.quantity}
                  </td>
                  <td className="py-2 text-muted">{m.unit_cost ? `KES ${Number(m.unit_cost).toLocaleString()}` : "-"}</td>
                  <td className="py-2 text-muted">{m.notes ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title="Record stock movement">
        <MovementForm error={error} pending={recordMovement.isPending} onSubmit={(body) => recordMovement.mutate(body)} />
      </Modal>
    </AdminShell>
  );
}

function MovementForm({
  onSubmit,
  error,
  pending,
}: {
  onSubmit: (body: { movement_type: string; quantity: string; unit_cost?: string; notes?: string }) => void;
  error: string | null;
  pending: boolean;
}) {
  const [type, setType] = useState<string>(MOVEMENT_TYPES[0]);
  const [quantity, setQuantity] = useState("");
  const [unitCost, setUnitCost] = useState("");
  const [notes, setNotes] = useState("");
  const isAdjustment = type === "adjustment";

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ movement_type: type, quantity, unit_cost: unitCost || undefined, notes: notes || undefined });
      }}
      className="space-y-3"
    >
      {error && <ErrorState message={error} />}
      <Select id="movement-type" label="Type" value={type} onChange={(e) => setType(e.target.value)}>
        {MOVEMENT_TYPES.map((t) => (
          <option key={t} value={t}>
            {t.replace(/_/g, " ")}
          </option>
        ))}
      </Select>
      <Input
        id="movement-quantity"
        label={isAdjustment ? "Quantity (signed - negative to decrease)" : "Quantity"}
        type="number"
        step="0.01"
        required
        value={quantity}
        onChange={(e) => setQuantity(e.target.value)}
      />
      <Input
        id="movement-cost"
        label="Unit cost (KES, optional)"
        type="number"
        min="0"
        step="0.01"
        value={unitCost}
        onChange={(e) => setUnitCost(e.target.value)}
      />
      <Input id="movement-notes" label="Notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Recording…" : "Record movement"}
      </Button>
    </form>
  );
}
