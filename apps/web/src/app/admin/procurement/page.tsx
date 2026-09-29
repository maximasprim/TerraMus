"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { Card, Button, Input, Select, Textarea, Modal, ErrorState, EmptyState, StatusBadge } from "@/components/ui";
import { BulkImportModal } from "@/components/bulk-import-modal";
import { apiFetch, ApiError } from "@/lib/api";
import type { Supplier, PurchaseOrder, InventoryItem } from "@/lib/types";

export default function ProcurementPage() {
  const queryClient = useQueryClient();
  const [supplierModalOpen, setSupplierModalOpen] = useState(false);
  const [poModalOpen, setPoModalOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [supplierError, setSupplierError] = useState<string | null>(null);
  const [poError, setPoError] = useState<string | null>(null);

  const suppliersQuery = useQuery<Supplier[]>({
    queryKey: ["suppliers"],
    queryFn: () => apiFetch<Supplier[]>("/api/v1/procurement/suppliers"),
  });
  const poQuery = useQuery<PurchaseOrder[]>({
    queryKey: ["purchase-orders"],
    queryFn: () => apiFetch<PurchaseOrder[]>("/api/v1/procurement/purchase-orders"),
  });
  const itemsQuery = useQuery<InventoryItem[]>({
    queryKey: ["inventory-items"],
    queryFn: () => apiFetch<InventoryItem[]>("/api/v1/inventory/items"),
    enabled: poModalOpen,
  });

  const createSupplier = useMutation({
    mutationFn: (body: { name: string; phone?: string; email?: string; contact_person?: string }) =>
      apiFetch("/api/v1/procurement/suppliers", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["suppliers"] });
      setSupplierModalOpen(false);
      setSupplierError(null);
    },
    onError: (err) => setSupplierError(err instanceof ApiError ? err.message : "Failed to create supplier"),
  });

  const createPo = useMutation({
    mutationFn: (body: {
      supplier_id: string;
      notes?: string;
      items: { inventory_item_id?: string; description: string; quantity: string; unit_cost: string }[];
    }) => apiFetch("/api/v1/procurement/purchase-orders", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["purchase-orders"] });
      setPoModalOpen(false);
      setPoError(null);
    },
    onError: (err) => setPoError(err instanceof ApiError ? err.message : "Failed to create purchase order"),
  });

  return (
    <AdminShell>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl text-forest">Procurement</h1>
          <p className="text-sm text-muted">Suppliers and purchase orders - receiving goods posts real stock movements.</p>
        </div>
        <Button variant="ghost" onClick={() => setImportOpen(true)}>Import suppliers CSV</Button>
      </div>

      <div className="mb-8">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-display text-lg text-forest">Suppliers</h2>
          <Button onClick={() => { setSupplierError(null); setSupplierModalOpen(true); }}>+ New supplier</Button>
        </div>
        {suppliersQuery.error && (
          <ErrorState message={suppliersQuery.error instanceof ApiError ? suppliersQuery.error.message : "Failed to load suppliers"} />
        )}
        {suppliersQuery.data && suppliersQuery.data.length === 0 && (
          <EmptyState title="No suppliers yet" body="Add a supplier before creating a purchase order." />
        )}
        {suppliersQuery.data && suppliersQuery.data.length > 0 && (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {suppliersQuery.data.map((s) => (
              <Card key={s.id}>
                <h3 className="font-display text-lg text-forest">{s.name}</h3>
                <p className="text-sm text-muted">{s.contact_person ?? "-"}</p>
                <p className="text-xs text-muted">{s.phone ?? s.email ?? "No contact info"}</p>
              </Card>
            ))}
          </div>
        )}
      </div>

      <div>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-display text-lg text-forest">Purchase orders</h2>
          <Button onClick={() => { setPoError(null); setPoModalOpen(true); }}>+ New purchase order</Button>
        </div>
        {poQuery.error && (
          <ErrorState message={poQuery.error instanceof ApiError ? poQuery.error.message : "Failed to load purchase orders"} />
        )}
        {poQuery.data && poQuery.data.length === 0 && (
          <EmptyState title="No purchase orders yet" body="Create one to start tracking goods on order." />
        )}
        {poQuery.data && poQuery.data.length > 0 && (
          <div className="overflow-hidden rounded-lg border border-hairline">
            <table className="w-full text-left text-sm">
              <thead className="bg-forest text-paper">
                <tr>
                  <th className="px-4 py-3 font-medium">PO Number</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Total</th>
                  <th className="px-4 py-3 font-medium">Expected delivery</th>
                </tr>
              </thead>
              <tbody>
                {poQuery.data.map((po, i) => (
                  <tr key={po.id} className={i % 2 === 0 ? "bg-white/40" : "bg-white/70"}>
                    <td className="px-4 py-3">
                      <Link href={`/admin/procurement/purchase-orders/${po.id}`} className="font-mono text-xs text-forest hover:underline">
                        {po.po_number}
                      </Link>
                    </td>
                    <td className="px-4 py-3"><StatusBadge status={po.status} /></td>
                    <td className="px-4 py-3 text-ink">KES {Number(po.total_amount).toLocaleString()}</td>
                    <td className="px-4 py-3 text-muted">{po.expected_delivery_date ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <Modal open={supplierModalOpen} onClose={() => setSupplierModalOpen(false)} title="New supplier">
        <SupplierForm error={supplierError} pending={createSupplier.isPending} onSubmit={(b) => createSupplier.mutate(b)} />
      </Modal>

      <Modal open={poModalOpen} onClose={() => setPoModalOpen(false)} title="New purchase order">
        <PoForm
          error={poError}
          pending={createPo.isPending}
          suppliers={suppliersQuery.data ?? []}
          items={itemsQuery.data ?? []}
          onSubmit={(b) => createPo.mutate(b)}
        />
      </Modal>

      <BulkImportModal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        endpoint="/api/v1/bulk-import/suppliers"
        invalidateKeys={[["suppliers"]]}
      />
    </AdminShell>
  );
}

function SupplierForm({
  onSubmit,
  error,
  pending,
}: {
  onSubmit: (body: { name: string; phone?: string; email?: string; contact_person?: string }) => void;
  error: string | null;
  pending: boolean;
}) {
  const [name, setName] = useState("");
  const [contactPerson, setContactPerson] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({
          name, contact_person: contactPerson || undefined,
          phone: phone || undefined, email: email || undefined,
        });
      }}
      className="space-y-3"
    >
      {error && <ErrorState message={error} />}
      <Input id="sup-name" label="Supplier name" required value={name} onChange={(e) => setName(e.target.value)} />
      <Input id="sup-contact" label="Contact person" value={contactPerson} onChange={(e) => setContactPerson(e.target.value)} />
      <Input id="sup-phone" label="Phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
      <Input id="sup-email" label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Creating…" : "Create supplier"}
      </Button>
    </form>
  );
}

interface PoLine {
  inventory_item_id: string;
  description: string;
  quantity: string;
  unit_cost: string;
}

function PoForm({
  onSubmit,
  error,
  pending,
  suppliers,
  items,
}: {
  onSubmit: (body: {
    supplier_id: string;
    notes?: string;
    items: { inventory_item_id?: string; description: string; quantity: string; unit_cost: string }[];
  }) => void;
  error: string | null;
  pending: boolean;
  suppliers: Supplier[];
  items: InventoryItem[];
}) {
  const [supplierId, setSupplierId] = useState("");
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState<PoLine[]>([{ inventory_item_id: "", description: "", quantity: "1", unit_cost: "0" }]);

  const updateLine = (i: number, patch: Partial<PoLine>) =>
    setLines((prev) => prev.map((l, idx) => (idx === i ? { ...l, ...patch } : l)));

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({
          supplier_id: supplierId,
          notes: notes || undefined,
          items: lines.map((l) => ({
            inventory_item_id: l.inventory_item_id || undefined,
            description: l.description,
            quantity: l.quantity,
            unit_cost: l.unit_cost,
          })),
        });
      }}
      className="space-y-3"
    >
      {error && <ErrorState message={error} />}
      <Select id="po-supplier" label="Supplier" required value={supplierId} onChange={(e) => setSupplierId(e.target.value)}>
        <option value="">Select a supplier…</option>
        {suppliers.map((s) => (
          <option key={s.id} value={s.id}>{s.name}</option>
        ))}
      </Select>

      <div className="space-y-2">
        <p className="text-sm font-medium text-ink">Line items</p>
        {lines.map((line, i) => (
          <div key={i} className="grid grid-cols-12 gap-2">
            <Select
              className="col-span-4"
              value={line.inventory_item_id}
              onChange={(e) => updateLine(i, { inventory_item_id: e.target.value })}
            >
              <option value="">Not tracked in inventory</option>
              {items.map((it) => (
                <option key={it.id} value={it.id}>{it.name}</option>
              ))}
            </Select>
            <Input
              className="col-span-4"
              placeholder="Description"
              required
              value={line.description}
              onChange={(e) => updateLine(i, { description: e.target.value })}
            />
            <Input
              className="col-span-2"
              type="number" min="0.01" step="0.01" placeholder="Qty"
              value={line.quantity}
              onChange={(e) => updateLine(i, { quantity: e.target.value })}
            />
            <Input
              className="col-span-2"
              type="number" min="0" step="0.01" placeholder="Unit cost"
              value={line.unit_cost}
              onChange={(e) => updateLine(i, { unit_cost: e.target.value })}
            />
          </div>
        ))}
        <Button
          type="button"
          variant="ghost"
          className="text-xs"
          onClick={() => setLines((prev) => [...prev, { inventory_item_id: "", description: "", quantity: "1", unit_cost: "0" }])}
        >
          + Add line
        </Button>
      </div>

      <Textarea id="po-notes" label="Notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
      <Button type="submit" disabled={pending || !supplierId} className="w-full">
        {pending ? "Creating…" : "Create purchase order"}
      </Button>
    </form>
  );
}
