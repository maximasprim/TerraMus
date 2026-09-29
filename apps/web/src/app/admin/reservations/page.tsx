"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { Card, Button, StatusBadge, ErrorState, EmptyState } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import type { Reservation, Animal, Customer } from "@/lib/types";

export default function ReservationsPage() {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const reservationsQuery = useQuery<Reservation[]>({
    queryKey: ["reservations"],
    queryFn: () => apiFetch<Reservation[]>("/api/v1/reservations"),
  });
  const animalsQuery = useQuery<Animal[]>({
    queryKey: ["livestock"],
    queryFn: () => apiFetch<Animal[]>("/api/v1/livestock?page_size=200"),
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

  return (
    <AdminShell>
      <div className="mb-6">
        <h1 className="font-display text-2xl text-forest">Reservations</h1>
        <p className="text-sm text-muted">
          Animals held for a customer - cancelling releases the animal back to "for sale".
        </p>
      </div>

      {error && <div className="mb-4"><ErrorState message={error} /></div>}
      {reservationsQuery.error && (
        <ErrorState message={reservationsQuery.error instanceof ApiError ? reservationsQuery.error.message : "Failed to load reservations"} />
      )}
      {reservationsQuery.data && reservationsQuery.data.length === 0 && (
        <EmptyState title="No reservations" body="Reservations are created from an animal's profile once it's for sale." />
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
