"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { Card, Button, StatusBadge, ErrorState, EmptyState, Input, Modal, Select, Textarea } from "@/components/ui";
import { ApiError, apiFetch, apiFetchAll } from "@/lib/api";
import type { Reservation, Animal, Customer } from "@/lib/types";

const isoDay = (offsetDays = 0) => new Date(Date.now() + offsetDays * 86_400_000).toISOString().slice(0, 10);

export default function ReservationsPage() {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [form, setForm] = useState({ animal_id: "", customer_id: "", reservation_date: isoDay(), expiry_date: isoDay(7), deposit_amount: "", notes: "" });

  const reservationsQuery = useQuery<Reservation[]>({
    queryKey: ["reservations"],
    queryFn: () => apiFetch<Reservation[]>("/api/v1/reservations"),
  });
  const animalsQuery = useQuery<Animal[]>({
    queryKey: ["livestock"],
    queryFn: () => apiFetchAll<Animal>("/api/v1/livestock"),
  });
  const customersQuery = useQuery<Customer[]>({
    queryKey: ["customers"],
    queryFn: () => apiFetch<Customer[]>("/api/v1/customers"),
  });

  const cancel = useMutation({
    mutationFn: (id: string) => apiFetch(`/api/v1/reservations/${id}/cancel`, { method: "POST" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["reservations"] });
      queryClient.invalidateQueries({ queryKey: ["livestock"] });
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Failed to cancel reservation"),
  });

  const create = useMutation({
    mutationFn: () =>
      apiFetch("/api/v1/reservations", {
        method: "POST",
        body: JSON.stringify({
          animal_id: form.animal_id,
          customer_id: form.customer_id,
          reservation_date: form.reservation_date,
          expiry_date: form.expiry_date,
          deposit_amount: form.deposit_amount.trim() || undefined,
          notes: form.notes.trim() || undefined,
        }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["reservations"] });
      queryClient.invalidateQueries({ queryKey: ["livestock"] });
      setModalOpen(false);
      setForm({ animal_id: "", customer_id: "", reservation_date: isoDay(), expiry_date: isoDay(7), deposit_amount: "", notes: "" });
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Failed to create the reservation"),
  });

  // Releases every reservation whose expiry date has passed (animals go back to "for sale").
  const clearExpired = useMutation({
    mutationFn: () => apiFetch<{ expired_count: number }>("/api/v1/reservations/expire-stale", { method: "POST" }),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["reservations"] });
      queryClient.invalidateQueries({ queryKey: ["livestock"] });
      setError(null);
      setNotice(result.expired_count === 0 ? "No expired reservations to clear." : `Released ${result.expired_count} expired reservation${result.expired_count === 1 ? "" : "s"}.`);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Failed to clear expired reservations"),
  });

  const forSale = (animalsQuery.data ?? []).filter((a) => a.status === "for_sale");
  const canSubmit = !!form.animal_id && !!form.customer_id && form.expiry_date >= form.reservation_date;

  return (
    <AdminShell>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl text-forest">Reservations</h1>
          <p className="text-sm text-muted">
            Animals held for a customer - cancelling releases the animal back to "for sale".
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" disabled={clearExpired.isPending} onClick={() => { setNotice(null); clearExpired.mutate(); }}>
            {clearExpired.isPending ? "Clearing…" : "Clear expired"}
          </Button>
          <Button onClick={() => { setError(null); setModalOpen(true); }}>+ New reservation</Button>
        </div>
      </div>

      {notice && <p className="mb-4 rounded-md border border-forest/30 bg-forest/5 px-3 py-2 text-sm text-forest">{notice}</p>}
      {error && <div className="mb-4"><ErrorState message={error} /></div>}

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title="New reservation">
        <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); if (canSubmit) create.mutate(); }}>
          {forSale.length === 0 && <p className="text-sm text-muted">No animals are currently marked for sale - put an animal up for sale first.</p>}
          <Select id="res-animal" label="Animal (for sale)" value={form.animal_id} onChange={(e) => setForm({ ...form, animal_id: e.target.value })} required>
            <option value="">Select an animal…</option>
            {forSale.map((a) => <option key={a.id} value={a.id}>{a.animal_number}{a.name ? ` - ${a.name}` : ""} ({a.species})</option>)}
          </Select>
          <Select id="res-customer" label="Customer" value={form.customer_id} onChange={(e) => setForm({ ...form, customer_id: e.target.value })} required>
            <option value="">Select a customer…</option>
            {(customersQuery.data ?? []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
          <div className="grid grid-cols-2 gap-3">
            <Input id="res-from" label="Reserved on" type="date" value={form.reservation_date} onChange={(e) => setForm({ ...form, reservation_date: e.target.value })} required />
            <Input id="res-until" label="Hold until" type="date" value={form.expiry_date} min={form.reservation_date} onChange={(e) => setForm({ ...form, expiry_date: e.target.value })} required />
          </div>
          <Input id="res-deposit" label="Deposit (KES, optional)" type="number" step="any" min="0" value={form.deposit_amount} onChange={(e) => setForm({ ...form, deposit_amount: e.target.value })} />
          <Textarea id="res-notes" label="Notes (optional)" rows={2} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="ghost" onClick={() => setModalOpen(false)}>Cancel</Button>
            <Button type="submit" disabled={!canSubmit || create.isPending}>{create.isPending ? "Reserving…" : "Reserve animal"}</Button>
          </div>
        </form>
      </Modal>
      {reservationsQuery.error && (
        <ErrorState message={reservationsQuery.error instanceof ApiError ? reservationsQuery.error.message : "Failed to load reservations"} />
      )}
      {reservationsQuery.data && reservationsQuery.data.length === 0 && (
        <EmptyState title="No reservations" body={'Use "+ New reservation" to hold a for-sale animal for a customer.'} />
      )}

      {reservationsQuery.data && reservationsQuery.data.length > 0 && (
        <div className="space-y-3">
          {reservationsQuery.data.map((r) => {
            const animal = animalsQuery.data?.find((a) => a.id === r.animal_id);
            const customer = customersQuery.data?.find((c) => c.id === r.customer_id);
            return (
              <Card key={r.id}>
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-medium text-ink">
                      {animal?.animal_number ?? r.animal_id.slice(0, 8)} → {customer?.name ?? "Unknown customer"}
                    </p>
                    <p className="text-xs text-muted">
                      Reserved {r.reservation_date} · expires {r.expiry_date}
                      {r.deposit_amount && ` · deposit KES ${Number(r.deposit_amount).toLocaleString()}`}
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    <StatusBadge status={r.status} />
                    {r.status === "active" && (
                      <Button
                        variant="ghost"
                        className="text-xs"
                        disabled={cancel.isPending}
                        onClick={() => cancel.mutate(r.id)}
                      >
                        Cancel
                      </Button>
                    )}
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </AdminShell>
  );
}
