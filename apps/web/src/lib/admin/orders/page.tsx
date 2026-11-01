"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { StatusBadge, ErrorState, EmptyState } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import type { Order, Customer } from "@/lib/types";

export default function OrdersPage() {
  const ordersQuery = useQuery<Order[]>({
    queryKey: ["orders"],
    queryFn: () => apiFetch<Order[]>("/api/v1/orders"),
  });
  const customersQuery = useQuery<Customer[]>({
    queryKey: ["customers"],
    queryFn: () => apiFetch<Customer[]>("/api/v1/customers"),
  });

  const customerName = (id: string) => customersQuery.data?.find((c) => c.id === id)?.name ?? id.slice(0, 8);

  return (
    <AdminShell>
      <h1 className="font-display text-2xl text-forest">Orders</h1>
      <p className="mb-6 text-sm text-muted">Every order placed, whether by staff or guest checkout.</p>

      {ordersQuery.error && (
        <ErrorState message={ordersQuery.error instanceof ApiError ? ordersQuery.error.message : "Failed to load orders"} />
      )}
      {ordersQuery.isLoading && <p className="text-sm text-muted">Loading…</p>}
      {ordersQuery.data && ordersQuery.data.length === 0 && (
        <EmptyState title="No orders yet" body="Orders placed by staff or through guest checkout will show up here." />
      )}

      {ordersQuery.data && ordersQuery.data.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-hairline">
          <table className="w-full text-left text-sm">
            <thead className="bg-forest text-paper">
              <tr>
                <th className="px-4 py-3 font-medium">Customer</th>
                <th className="px-4 py-3 font-medium">Items</th>
                <th className="px-4 py-3 font-medium">Total</th>
                <th className="px-4 py-3 font-medium">Delivery</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Placed</th>
              </tr>
            </thead>
            <tbody>
              {ordersQuery.data.map((order, i) => (
                <tr key={order.id} className={i % 2 === 0 ? "bg-white/40" : "bg-white/70"}>
                  <td className="px-4 py-3">
                    <Link href={`/admin/orders/${order.id}`} className="font-medium text-ink hover:underline">
                      {customerName(order.customer_id)}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-muted">{order.items.length}</td>
                  <td className="px-4 py-3 font-medium text-ink">KES {Number(order.total_amount).toLocaleString()}</td>
                  <td className="px-4 py-3 capitalize text-muted">{order.delivery_option}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={order.status} />
                  </td>
                  <td className="px-4 py-3 text-muted">{new Date(order.created_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </AdminShell>
  );
}
