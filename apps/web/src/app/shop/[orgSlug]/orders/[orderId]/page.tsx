"use client";

import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ShopHeader } from "@/components/shop-header";
import { PaymentPanel } from "@/components/shop-payment-panel";
import { Card, StatusBadge, ErrorState } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import type { Order } from "@/lib/types";

/** How long we keep checking for the payment confirmation before asking the customer to retry/refresh. */
const WAIT_LIMIT_MS = 3 * 60_000;

export default function GuestOrderStatusPage() {
  const { orgSlug, orderId } = useParams<{ orgSlug: string; orderId: string }>();
  const searchParams = useSearchParams();
  const email = searchParams.get("email") ?? "";

  // After the M-Pesa prompt is sent the order is polled until the provider's callback marks it paid.
  // Polling stops on its own (paid, or WAIT_LIMIT_MS) so an abandoned tab doesn't hammer the API.
  const [waiting, setWaiting] = useState(false);
  const [timedOut, setTimedOut] = useState(false);

  const { data, isLoading, error } = useQuery<Order>({
    queryKey: ["public-order", orgSlug, orderId, email],
    queryFn: () =>
      apiFetch<Order>(`/api/v1/public/${orgSlug}/orders/${orderId}?email=${encodeURIComponent(email)}`, { auth: false }),
    enabled: !!email,
    refetchInterval: waiting ? 4000 : false,
  });

  useEffect(() => {
    if (data?.status === "paid") setWaiting(false);
  }, [data?.status]);

  useEffect(() => {
    if (!waiting) return;
    const t = setTimeout(() => {
      setWaiting(false);
      setTimedOut(true);
    }, WAIT_LIMIT_MS);
    return () => clearTimeout(t);
  }, [waiting]);

  const unpaid = data?.status === "pending" || data?.status === "payment_pending";

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

        {data?.status === "paid" && (
          <div className="mt-6 rounded-lg border border-forest/30 bg-forest/5 p-5">
            <h2 className="font-semibold text-forest">Payment received - thank you!</h2>
            <p className="mt-1 text-sm text-ink/80">The farm has your payment and will be in touch about {data.delivery_option === "delivery" ? "delivery" : "collection"}.</p>
          </div>
        )}

        {data?.status === "cancelled" && (
          <p className="mt-6 rounded-lg border border-hairline bg-white p-5 text-sm text-muted">
            This order was cancelled (unpaid orders are released after a while so the items can go back on sale). You&apos;re
            welcome to place a new order from the store.
          </p>
        )}

        {data && unpaid && (
          <PaymentPanel
            orgSlug={orgSlug}
            orderId={orderId}
            email={email}
            total={data.total_amount}
            waiting={waiting}
            timedOut={timedOut}
            onInitiated={() => {
              setTimedOut(false);
              setWaiting(true);
            }}
          />
        )}
      </main>
    </div>
  );
}
