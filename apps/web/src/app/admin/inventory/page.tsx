"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { Can } from "@/components/can";
import { Card, Button, Input, Select, Modal, ErrorState, EmptyState } from "@/components/ui";
import { BulkImportModal } from "@/components/bulk-import-modal";
import { apiFetch, ApiError } from "@/lib/api";
import type { InventoryItem } from "@/lib/types";
import { clsx } from "clsx";

const CATEGORIES = ["feed", "medicine", "vaccine", "supply", "equipment", "consumable"] as const;

export default function InventoryPage() {
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data, isLoading, error: loadError } = useQuery<InventoryItem[]>({
    queryKey: ["inventory-items"],
    queryFn: () => apiFetch<InventoryItem[]>("/api/v1/inventory/items"),
  });

  const create = useMutation({
    mutationFn: (body: { name: string; category: string; unit: string; reorder_level: string }) =>
      apiFetch("/api/v1/inventory/items", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["inventory-items"] });
      setModalOpen(false);
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Failed to create item"),
  });

  return (
    <AdminShell>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl text-forest">Inventory</h1>
          <p className="text-sm text-muted">Feed, medicine, and supplies - stock is always the sum of the ledger.</p>
        </div>
        <div className="flex gap-2">
          <Link href="/admin/inventory/valuation">
            <Button variant="ghost">Valuation report</Button>
          </Link>
          <Button variant="ghost" onClick={() => setImportOpen(true)}>Import CSV</Button>
          <Can permission="inventory.adjust"><Button onClick={() => { setError(null); setModalOpen(true); }}>+ New item</Button></Can>
        </div>
      </div>

      {loadError && <ErrorState message={loadError instanceof ApiError ? loadError.message : "Failed to load inventory"} />}
      {isLoading && <p className="text-sm text-muted">Loading…</p>}
      {data && data.length === 0 && (
        <EmptyState title="No inventory items yet" body="Add feed, medicine, or supplies to start tracking stock." />
      )}

      {data && data.length > 0 && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {data.map((item) => {
            const low = Number(item.current_stock) <= Number(item.reorder_level);
            return (
              <Link key={item.id} href={`/admin/inventory/${item.id}`}>
                <Card className={clsx("h-full", low && "border-clay/40 bg-clay/5")}>
                  <div className="mb-1 flex items-center justify-between">
                    <h2 className="font-display text-lg text-forest">{item.name}</h2>
                    {low && (
                      <span className="rounded-full border border-clay/30 bg-clay/10 px-2 py-0.5 text-xs text-clay">
                        Low stock
                      </span>
                    )}
                  </div>
                  <p className="text-xs capitalize text-muted">{item.category}</p>
                  <p className="mt-3 font-display text-2xl text-ink">
                    {item.current_stock} <span className="text-sm font-body text-muted">{item.unit}</span>
                  </p>
                  <p className="text-xs text-muted">Reorder at {item.reorder_level} {item.unit}</p>
                </Card>
              </Link>
            );
          })}
        </div>
      )}

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title="New inventory item">
        <ItemForm error={error} pending={create.isPending} onSubmit={(body) => create.mutate(body)} />
      </Modal>

      <BulkImportModal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        endpoint="/api/v1/bulk-import/inventory-items"
        invalidateKeys={[["inventory-items"]]}
      />
    </AdminShell>
  );
}

function ItemForm({
  onSubmit,
  error,
  pending,
}: {
  onSubmit: (body: { name: string; category: string; unit: string; reorder_level: string }) => void;
  error: string | null;
  pending: boolean;
}) {
  const [name, setName] = useState("");
  const [category, setCategory] = useState<string>(CATEGORIES[0]);
  const [unit, setUnit] = useState("kg");
  const [reorderLevel, setReorderLevel] = useState("0");

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ name, category, unit, reorder_level: reorderLevel });
      }}
      className="space-y-3"
    >
      {error && <ErrorState message={error} />}
      <Input id="item-name" label="Name" required value={name} onChange={(e) => setName(e.target.value)} />
      <Select id="item-category" label="Category" value={category} onChange={(e) => setCategory(e.target.value)}>
        {CATEGORIES.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </Select>
      <div className="grid grid-cols-2 gap-4">
        <Input id="item-unit" label="Unit" required value={unit} onChange={(e) => setUnit(e.target.value)} placeholder="kg, bag, litre…" />
        <Input
          id="item-reorder"
          label="Reorder level"
          type="number"
          min="0"
          step="0.01"
          value={reorderLevel}
          onChange={(e) => setReorderLevel(e.target.value)}
        />
      </div>
      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Creating…" : "Create item"}
      </Button>
    </form>
  );
}
