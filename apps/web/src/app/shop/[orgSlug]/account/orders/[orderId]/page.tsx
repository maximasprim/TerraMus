"use client";

import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ShopHeader } from "@/components/shop-header";
import { Card, StatusBadge, ErrorState } from "@/components/ui";
import { apiFetch, getAccessToken, ApiError } from "@/lib/api";
import type { MyOrderDetail } from "@/lib/types";

export default function CustomerOrderDetailPage() {
  const { orgSlug, orderId } = useParams<{ orgSlug: string; orderId: string }>();
  const loggedIn = typeof window !== "undefined" && !!getAccessToken();

  const orderQuery = useQuery<MyOrderDetail>({
    queryKey: ["my-order", orderId],
    queryFn: () => apiFetch<MyOrderDetail>(`/api/v1/account/orders/${orderId}`),
    enabled: loggedIn,
    retry: false,
  });

  return (
    <div className="min-h-screen bg-paper">
      <ShopHeader orgSlug={orgSlug} />
      <main className="mx-auto max-w-2xl px-6 py-10">
        {!loggedIn && <ErrorState message="Log in to view this order." />}
        {orderQuery.error && (
          <ErrorState message={orderQuery.error instanceof ApiError ? orderQuery.error.message : "Failed to load order"} />
        )}
        {orderQuery.isLoading && <p className="text-sm text-muted">Loading…</p>}

        {orderQuery.data && (
          <>
            <div className="mb-6 flex items-center justify-between">
              <div>
                <h1 className="font-display text-2xl text-forest">
                  Order from {new Date(orderQuery.data.created_at).toLocaleDateString()}
                </h1>
                <p className="text-sm text-muted">{orderQuery.data.items.length} animal(s)</p>
              </div>
              <StatusBadge status={orderQuery.data.status} />
            </div>

            <Card className="mb-4">
              <h2 className="mb-3 font-display text-lg text-forest">Items</h2>
              <div className="space-y-2 text-sm">
                {orderQuery.data.items.map((item, i) => (
                  <div key={i} className="flex justify-between border-b border-hairline/60 pb-2">
                    <span className="text-ink">Animal {item.animal_id.slice(0, 8)}…</span>
                    <span className="font-medium text-ink">KES {Number(item.price).toLocaleString()}</span>
                  </div>
                ))}
              </div>
              <div className="mt-3 flex justify-between border-t border-hairline pt-3">
                <span className="font-medium text-ink">Total</span>
                <span className="font-display text-lg text-forest">
                  KES {Number(orderQuery.data.total_amount).toLocaleString()}
                </span>
              </div>
            </Card>

            {orderQuery.data.invoice && (
              <Card className="mb-4">
                <h2 className="mb-3 font-display text-lg text-forest">Invoice</h2>
                <dl className="space-y-2 text-sm">
                  <div className="flex justify-between"><dt className="text-muted">Invoice number</dt><dd className="text-ink">{orderQuery.data.invoice.invoice_number}</dd></div>
                  <div className="flex justify-between"><dt className="text-muted">Subtotal</dt><dd className="text-ink">KES {Number(orderQuery.data.invoice.subtotal).toLocaleString()}</dd></div>
                  {Number(orderQuery.data.invoice.tax_amount) > 0 && (
                    <div className="flex justify-between"><dt className="text-muted">Tax</dt><dd className="text-ink">KES {Number(orderQuery.data.invoice.tax_amount).toLocaleString()}</dd></div>
                  )}
                  <div className="flex justify-between"><dt className="text-muted">Total</dt><dd className="font-medium text-ink">KES {Number(orderQuery.data.invoice.total).toLocaleString()}</dd></div>
                  <div className="flex justify-between"><dt className="text-muted">Issued</dt><dd className="text-ink">{new Date(orderQuery.data.invoice.issued_at).toLocaleDateString()}</dd></div>
                </dl>
              </Card>
            )}

            {orderQuery.data.payments.length > 0 && (
              <Card>
                <h2 className="mb-3 font-display text-lg text-forest">Payment history</h2>
                <div className="space-y-2 text-sm">
                  {orderQuery.data.payments.map((p, i) => (
                    <div key={i} className="flex items-center justify-between border-b border-hairline/60 pb-2">
                      <div>
                        <p className="capitalize text-ink">{p.provider}</p>
                        <p className="text-xs text-muted">{new Date(p.initiated_at).toLocaleString()}</p>
                      </div>
                      <div className="text-right">
                        <p className="text-ink">KES {Number(p.amount).toLocaleString()}</p>
                        <StatusBadge status={p.status} />
                      </div>
                    </div>
                  ))}
                </div>
              </Card>
            )}
          </>
        )}
      </main>
    </div>
  );
}
