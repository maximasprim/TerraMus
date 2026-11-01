"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { EditEntityModal } from "@/components/edit-entity-modal";
import { useCan } from "@/lib/use-auth";
import { Card, Button, Input, Select, Textarea, Modal, ErrorState, EmptyState, StatusBadge } from "@/components/ui";
import { BulkImportModal } from "@/components/bulk-import-modal";
import { apiFetch, ApiError } from "@/lib/api";
import type { Supplier, PurchaseOrder, InventoryItem } from "@/lib/types";

export default function ProcurementPage() {
  const queryClient = useQueryClient();
  const [supplierModalOpen, setSupplierModalOpen] = useState(false);
  const [editingSupplier, setEditingSupplier] = useState<Supplier | null>(null);
  const can = useCan();
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
      expected_delivery_date?: string;
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
                <div className="flex items-start justify-between gap-2">
                  <h3 className="font-display text-lg text-forest">{s.name}</h3>
                  {can("procurement.manage") && (
                    <button type="button" onClick={() => setEditingSupplier(s)} className="rounded border border-hairline px-2 py-0.5 text-xs text-forest hover:bg-forest/5">Edit</button>
                  )}
                </div>
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

      <Modal open={poModalOpen} onClose={() => setPoModalOpen(false)} title="New purchase order" size="lg">
        <PoForm
          error={poError}
          pending={createPo.isPending}
          suppliers={suppliersQuery.data ?? []}
          suppliersLoading={suppliersQuery.isLoading}
          items={itemsQuery.data ?? []}
          itemsLoading={itemsQuery.isLoading}
          onSubmit={(b) => createPo.mutate(b)}
          onAddSupplier={() => { setPoModalOpen(false); setSupplierError(null); setSupplierModalOpen(true); }}
        />
      </Modal>

      {editingSupplier && (
        <EditEntityModal entity="suppliers" id={editingSupplier.id} record={editingSupplier} open onClose={() => setEditingSupplier(null)} invalidate={[["suppliers"]]} />
      )}
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
  key: number; // stable React key, so removing a line never scrambles the others' typed values
  inventory_item_id: string;
  description: string;
  quantity: string;
  unit_cost: string;
}

const money = (n: number) => `KES ${n.toLocaleString("en-US", { maximumFractionDigits: 2 })}`;
const num = (v: string) => (v.trim() === "" ? NaN : Number(v));
const lineTotal = (l: PoLine) => {
  const q = num(l.quantity);
  const c = num(l.unit_cost);
  return Number.isFinite(q) && Number.isFinite(c) && q > 0 && c >= 0 ? q * c : 0;
};

/**
 * Creates a purchase order in three plain steps: who from, what, and any notes.
 * Each item is its own labelled card (not a row of unlabelled boxes) with a live line total,
 * and the order total is always visible. The data sent to the API is unchanged, plus the
 * optional expected delivery date the API already supported.
 */
function PoForm({
  onSubmit,
  onAddSupplier,
  error,
  pending,
  suppliers,
  suppliersLoading,
  items,
  itemsLoading,
}: {
  onSubmit: (body: {
    supplier_id: string;
    expected_delivery_date?: string;
    notes?: string;
    items: { inventory_item_id?: string; description: string; quantity: string; unit_cost: string }[];
  }) => void;
  onAddSupplier: () => void;
  error: string | null;
  pending: boolean;
  suppliers: Supplier[];
  suppliersLoading: boolean;
  items: InventoryItem[];
  itemsLoading: boolean;
}) {
  const seq = useRef(0);
  const blankLine = (): PoLine => ({ key: ++seq.current, inventory_item_id: "", description: "", quantity: "1", unit_cost: "" });

  const [supplierId, setSupplierId] = useState("");
  const [expectedDate, setExpectedDate] = useState("");
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState<PoLine[]>(() => [blankLine()]);

  const sortedItems = [...items].sort((a, b) => a.name.localeCompare(b.name));
  const itemById = (id: string) => items.find((it) => it.id === id);

  const updateLine = (key: number, patch: Partial<PoLine>) =>
    setLines((prev) => prev.map((l) => (l.key === key ? { ...l, ...patch } : l)));

  // Picking an inventory item fills the description for you (unless you've typed your own).
  const pickItem = (line: PoLine, itemId: string) => {
    const previousName = itemById(line.inventory_item_id)?.name ?? "";
    const nextName = itemById(itemId)?.name ?? "";
    const keepTyped = line.description.trim() !== "" && line.description !== previousName;
    updateLine(line.key, { inventory_item_id: itemId, description: keepTyped ? line.description : nextName });
  };

  // Spell out what is still missing instead of leaving a silently greyed-out button.
  const problems: string[] = [];
  if (!supplierId) problems.push("choose a supplier");
  lines.forEach((l, i) => {
    const n = i + 1;
    if (!l.description.trim()) problems.push(`describe item ${n}`);
    if (!(num(l.quantity) > 0)) problems.push(`enter a quantity for item ${n}`);
    if (!(num(l.unit_cost) >= 0)) problems.push(`enter a price for item ${n}`);
  });
  const orderTotal = lines.reduce((sum, l) => sum + lineTotal(l), 0);

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (problems.length > 0) return;
        onSubmit({
          supplier_id: supplierId,
          expected_delivery_date: expectedDate || undefined,
          notes: notes.trim() || undefined,
          items: lines.map((l) => ({
            inventory_item_id: l.inventory_item_id || undefined,
            description: l.description.trim(),
            quantity: l.quantity,
            unit_cost: l.unit_cost,
          })),
        });
      }}
      className="space-y-6"
    >
      <p className="text-sm text-muted">
        Use this to request goods from a supplier. It only creates the order - no stock is added until you mark the
        goods as received.
      </p>

      {/* 1 - who from */}
      <section aria-labelledby="po-step-1" className="space-y-3">
        <h3 id="po-step-1" className="text-sm font-semibold text-forest">1. Who are you ordering from?</h3>
        {!suppliersLoading && suppliers.length === 0 ? (
          <div className="rounded-md border border-brass/40 bg-brass/10 px-3 py-3 text-sm text-ink">
            You haven&apos;t added a supplier yet.{" "}
            <button type="button" onClick={onAddSupplier} className="font-medium text-forest underline">
              Add a supplier first
            </button>
            , then come back to create the order.
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Select id="po-supplier" label="Supplier" required value={supplierId} onChange={(e) => setSupplierId(e.target.value)}>
              <option value="">Select a supplier…</option>
              {suppliers.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </Select>
            <Input id="po-expected" type="date" label="Expected delivery (optional)" value={expectedDate} onChange={(e) => setExpectedDate(e.target.value)} />
          </div>
        )}
      </section>

      {/* 2 - what */}
      <section aria-labelledby="po-step-2" className="space-y-3">
        <div>
          <h3 id="po-step-2" className="text-sm font-semibold text-forest">2. What are you ordering?</h3>
          <p className="text-xs text-muted">Add one item for each different thing you are buying.</p>
        </div>

        {lines.map((line, i) => {
          const n = i + 1;
          const picked = itemById(line.inventory_item_id);
          const qty = num(line.quantity);
          const priceIsZero = line.unit_cost.trim() !== "" && num(line.unit_cost) === 0; // only warn when 0 was typed on purpose, not on a fresh blank line
          return (
            <div key={line.key} role="group" aria-label={`Item ${n}`} className="rounded-lg border border-hairline bg-white/60 p-4">
              <div className="mb-3 flex items-center justify-between">
                <p className="text-xs font-semibold uppercase tracking-wider text-muted">Item {n}</p>
                {lines.length > 1 && (
                  <button
                    type="button"
                    onClick={() => setLines((prev) => prev.filter((l) => l.key !== line.key))}
                    className="text-xs text-clay hover:underline"
                    aria-label={`Remove item ${n}`}
                  >
                    Remove
                  </button>
                )}
              </div>

              <div className="space-y-3">
                <div>
                  <Select
                    id={`po-item-${line.key}`}
                    label="Inventory item (optional)"
                    value={line.inventory_item_id}
                    onChange={(e) => pickItem(line, e.target.value)}
                  >
                    <option value="">Not an inventory item (e.g. delivery fee, service)</option>
                    {sortedItems.map((it) => (
                      <option key={it.id} value={it.id}>{it.name}</option>
                    ))}
                  </Select>
                  <p className="mt-1 text-xs text-muted">
                    {itemsLoading
                      ? "Loading your inventory…"
                      : picked
                        ? `When received, ${Number.isFinite(qty) && qty > 0 ? `${qty} ${picked.unit}` : "the quantity"} will be added to ${picked.name} (stock now: ${Number(picked.current_stock).toLocaleString("en-US")} ${picked.unit}).`
                        : items.length === 0
                          ? "Tip: add the things you buy under Inventory, and receiving an order will update your stock automatically."
                          : "Pick the inventory item to have its stock updated when this order is received. Leave as is for anything that isn't stocked."}
                  </p>
                </div>

                <Input
                  id={`po-desc-${line.key}`}
                  label="Description"
                  required
                  maxLength={255}
                  placeholder="e.g. Dairy meal, 70 kg bag"
                  value={line.description}
                  onChange={(e) => updateLine(line.key, { description: e.target.value })}
                />

                <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                  <Input
                    id={`po-qty-${line.key}`}
                    label={`Quantity${picked ? ` (${picked.unit})` : ""}`}
                    type="number" inputMode="decimal" min="0.01" step="0.01"
                    value={line.quantity}
                    onChange={(e) => updateLine(line.key, { quantity: e.target.value })}
                  />
                  <Input
                    id={`po-cost-${line.key}`}
                    label="Price per unit (KES)"
                    type="number" inputMode="decimal" min="0" step="0.01" placeholder="0.00"
                    value={line.unit_cost}
                    onChange={(e) => updateLine(line.key, { unit_cost: e.target.value })}
                  />
                  <div>
                    <p className="mb-1 block text-sm font-medium text-ink">Line total</p>
                    <p aria-label={`Total for item ${n}`} className="rounded-md border border-transparent bg-hairline/30 px-3 py-2 text-sm font-medium tabular-nums text-ink">
                      {money(lineTotal(line))}
                    </p>
                  </div>
                </div>
                {priceIsZero && (
                  <p className="text-xs text-brass">The price is 0 - enter what you expect to pay per unit, unless this item is free.</p>
                )}
              </div>
            </div>
          );
        })}

        <Button type="button" variant="ghost" className="text-sm" onClick={() => setLines((prev) => [...prev, blankLine()])}>
          + Add another item
        </Button>

        <div className="flex items-center justify-between rounded-lg bg-forest/5 px-4 py-3" aria-live="polite">
          <span className="text-sm text-muted">{lines.length} item{lines.length === 1 ? "" : "s"}</span>
          <span className="text-sm text-ink">
            Order total <strong data-testid="po-total" className="ml-2 font-display text-lg text-forest tabular-nums">{money(orderTotal)}</strong>
          </span>
        </div>
      </section>

      {/* 3 - notes */}
      <section aria-labelledby="po-step-3" className="space-y-3">
        <h3 id="po-step-3" className="text-sm font-semibold text-forest">3. Anything else?</h3>
        <Textarea
          id="po-notes"
          label="Notes (optional)"
          placeholder="Anything the supplier or your team should know, e.g. delivery instructions"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
      </section>

      <div className="space-y-2">
        {error && <ErrorState message={error} />}
        {problems.length > 0 && (
          <p className="text-xs text-muted" data-testid="po-problems">Still needed: {problems.join(", ")}.</p>
        )}
        <Button type="submit" disabled={pending || problems.length > 0} className="w-full">
          {pending ? "Creating…" : "Create purchase order"}
        </Button>
      </div>
    </form>
  );
}
