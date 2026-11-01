"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { Card, Button, Input, Select, Modal, ErrorState, EmptyState } from "@/components/ui";
import { BulkImportModal } from "@/components/bulk-import-modal";
import { apiFetch, ApiError } from "@/lib/api";
import type { Customer } from "@/lib/types";

const CUSTOMER_TYPES = [
  "individual", "butcher", "hotel", "restaurant", "institution",
  "livestock_trader", "wholesaler", "farm", "corporate",
] as const;

export default function CustomersPage() {
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [editingCustomer, setEditingCustomer] = useState<Customer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editError, setEditError] = useState<string | null>(null);

  const { data, isLoading, error: loadError } = useQuery<Customer[]>({
    queryKey: ["customers"],
    queryFn: () => apiFetch<Customer[]>("/api/v1/customers"),
  });

  const create = useMutation({
    mutationFn: (body: { name: string; email?: string; phone?: string; customer_type: string }) =>
      apiFetch("/api/v1/customers", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["customers"] });
      setModalOpen(false);
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Failed to create customer"),
  });

  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: { name: string; email?: string; phone?: string; customer_type: string } }) =>
      apiFetch(`/api/v1/customers/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["customers"] });
      setEditingCustomer(null);
      setEditError(null);
    },
    onError: (err) => setEditError(err instanceof ApiError ? err.message : "Failed to update customer"),
  });

  return (
    <AdminShell>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl text-forest">Customers</h1>
          <p className="text-sm text-muted">Everyone who's bought from, or been quoted by, the farm.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" onClick={() => setImportOpen(true)}>Import CSV</Button>
          <Button onClick={() => { setError(null); setModalOpen(true); }}>+ New customer</Button>
        </div>
      </div>

      {loadError && <ErrorState message={loadError instanceof ApiError ? loadError.message : "Failed to load customers"} />}
      {isLoading && <p className="text-sm text-muted">Loading…</p>}
      {data && data.length === 0 && (
        <EmptyState title="No customers yet" body="Customers appear here once added manually or via guest checkout." />
      )}

      {data && data.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-hairline">
          <table className="w-full text-left text-sm">
            <thead className="bg-forest text-paper">
              <tr>
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Type</th>
                <th className="px-4 py-3 font-medium">Email</th>
                <th className="px-4 py-3 font-medium">Phone</th>
                <th className="px-4 py-3 font-medium">Location</th>
              </tr>
            </thead>
            <tbody>
              {data.map((c, i) => (
                <tr
                  key={c.id}
                  className={`cursor-pointer hover:bg-brass/5 ${i % 2 === 0 ? "bg-white/40" : "bg-white/70"}`}
                  onClick={() => { setEditError(null); setEditingCustomer(c); }}
                >
                  <td className="px-4 py-3 font-medium text-ink">{c.name}</td>
                  <td className="px-4 py-3 capitalize text-muted">{c.customer_type.replace(/_/g, " ")}</td>
                  <td className="px-4 py-3 text-muted">{c.email ?? "-"}</td>
                  <td className="px-4 py-3 text-muted">{c.phone ?? "-"}</td>
                  <td className="px-4 py-3 text-muted">{c.location ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title="New customer">
        <CustomerForm error={error} pending={create.isPending} onSubmit={(body) => create.mutate(body)} />
      </Modal>

      <Modal open={!!editingCustomer} onClose={() => setEditingCustomer(null)} title="Edit customer">
        {editingCustomer && (
          <CustomerForm
            initial={editingCustomer}
            error={editError}
            pending={update.isPending}
            onSubmit={(body) => update.mutate({ id: editingCustomer.id, body })}
          />
        )}
      </Modal>

      <BulkImportModal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        endpoint="/api/v1/bulk-import/customers"
        invalidateKeys={[["customers"]]}
      />
    </AdminShell>
  );
}

function CustomerForm({
  onSubmit,
  error,
  pending,
  initial,
}: {
  onSubmit: (body: { name: string; email?: string; phone?: string; customer_type: string }) => void;
  error: string | null;
  pending: boolean;
  initial?: Customer;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [email, setEmail] = useState(initial?.email ?? "");
  const [phone, setPhone] = useState(initial?.phone ?? "");
  const [type, setType] = useState<string>(initial?.customer_type ?? CUSTOMER_TYPES[0]);

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ name, email: email || undefined, phone: phone || undefined, customer_type: type });
      }}
      className="space-y-3"
    >
      {error && <ErrorState message={error} />}
      <Input id="cust-name" label="Name" required value={name} onChange={(e) => setName(e.target.value)} />
      <Input id="cust-email" label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
      <Input id="cust-phone" label="Phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
      <Select id="cust-type" label="Customer type" value={type} onChange={(e) => setType(e.target.value)}>
        {CUSTOMER_TYPES.map((t) => (
          <option key={t} value={t}>
            {t.replace(/_/g, " ")}
          </option>
        ))}
      </Select>
      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Saving…" : initial ? "Save changes" : "Create customer"}
      </Button>
    </form>
  );
}
