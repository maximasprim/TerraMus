"use client";

import { useParams, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ShopHeader } from "@/components/shop-header";
import { Card, StatusBadge, ErrorState } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import type { Order } from "@/lib/types";

export default function GuestOrderStatusPage() {
  const { orgSlug, orderId } = useParams<{ orgSlug: string; orderId: string }>();
  const searchParams = useSearchParams();
  const email = searchParams.get("email") ?? "";

  const { data, isLoading, error } = useQuery<Order>({
    queryKey: ["public-order", orgSlug, orderId, email],
    queryFn: () =>
      apiFetch<Order>(`/api/v1/public/${orgSlug}/orders/${orderId}?email=${encodeURIComponent(email)}`, { auth: false }),
    enabled: !!email,
  });

  return (
    <div className="min-h-screen bg-paper">
      <ShopHeader orgSlug={orgSlug} />
      <main className="mx-auto max-w-xl px-6 py-10">
        {!email && (
          <ErrorState message="This link is missing your order email - use the link from your order confirmation." />
        )}
        {error && (
          <ErrorState message={error instanceof ApiError ? error.message : "Order not found for that email"} />
        )}
        {isLoading && <p className="text-sm text-muted">Loading…</p>}

        {data && (
          <Card>
            <div className="mb-3 flex items-center justify-between">
              <h1 className="font-display text-2xl text-forest">Order status</h1>
              <StatusBadge status={data.status} />
            </div>
            <p className="mb-4 text-sm text-muted">Placed {new Date(data.created_at).toLocaleDateString()}</p>

            <dl className="space-y-2 text-sm">
              <div className="flex justify-between border-b border-hairline/60 pb-2">
                <dt className="text-muted">Total</dt>
                <dd className="font-medium text-ink">KES {Number(data.total_amount).toLocaleString()}</dd>
              </div>
              <div className="flex justify-between border-b border-hairline/60 pb-2 capitalize">
                <dt className="text-muted">Delivery</dt>
                <dd className="text-ink">{data.delivery_option}</dd>
              </div>
            </dl>

            <p className="mt-4 text-xs text-muted">
              Bookmark this page to check your order status later - you&apos;ll need this same link (with your email).
            </p>
          </Card>
        )}
      </main>
    </div>
  );
}
