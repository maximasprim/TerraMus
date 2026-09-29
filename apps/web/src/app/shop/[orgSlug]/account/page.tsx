"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ShopHeader } from "@/components/shop-header";
import { Card, Button, StatusBadge, ErrorState, EmptyState } from "@/components/ui";
import { apiFetch, getAccessToken, clearTokens, ApiError } from "@/lib/api";
import type { MyAccount, MyOrder } from "@/lib/types";

export default function CustomerAccountPage() {
  const { orgSlug } = useParams<{ orgSlug: string }>();
  const router = useRouter();
  const loggedIn = typeof window !== "undefined" && !!getAccessToken();

  const accountQuery = useQuery<MyAccount>({
    queryKey: ["my-account"],
    queryFn: () => apiFetch<MyAccount>("/api/v1/account/me"),
    enabled: loggedIn,
    retry: false,
  });
  const ordersQuery = useQuery<MyOrder[]>({
    queryKey: ["my-orders"],
    queryFn: () => apiFetch<MyOrder[]>("/api/v1/account/orders"),
    enabled: loggedIn && !!accountQuery.data,
  });

  if (!loggedIn) {
    return (
      <div className="min-h-screen bg-paper">
        <ShopHeader orgSlug={orgSlug} />
        <main className="mx-auto max-w-sm px-6 py-10">
          <Card>
            <h1 className="mb-2 font-display text-2xl text-forest">My account</h1>
            <p className="mb-4 text-sm text-muted">Log in to see your profile and order history.</p>
            <div className="flex gap-2">
              <Link href={`/shop/${orgSlug}/account/login`} className="flex-1">
                <Button className="w-full">Log in</Button>
              </Link>
              <Link href={`/shop/${orgSlug}/account/register`} className="flex-1">
                <Button variant="ghost" className="w-full">Register</Button>
              </Link>
            </div>
          </Card>
        </main>
      </div>
    );
  }

  const isWrongAccountType = accountQuery.error instanceof ApiError && accountQuery.error.status === 403;

  return (
    <div className="min-h-screen bg-paper">
      <ShopHeader orgSlug={orgSlug} />
      <main className="mx-auto max-w-2xl px-6 py-10">
        {isWrongAccountType && (
          <ErrorState message="This login isn't a customer account. Log in with a customer email instead." />
        )}
        {accountQuery.error && !isWrongAccountType && (
          <ErrorState message={accountQuery.error instanceof ApiError ? accountQuery.error.message : "Failed to load your account"} />
        )}
        {accountQuery.isLoading && <p className="text-sm text-muted">Loading…</p>}

        {accountQuery.data && (
          <>
            <div className="mb-6 flex items-center justify-between">
              <div>
                <h1 className="font-display text-2xl text-forest">{accountQuery.data.full_name}</h1>
                <p className="text-sm text-muted">{accountQuery.data.email}</p>
              </div>
              <Button
                variant="ghost"
                onClick={() => { clearTokens(); router.push(`/shop/${orgSlug}`); }}
              >
                Log out
              </Button>
            </div>

            <h2 className="mb-3 font-display text-lg text-forest">Your orders</h2>
            {ordersQuery.data && ordersQuery.data.length === 0 && (
              <EmptyState title="No orders yet" body="Browse the farm's listings to place your first order." />
            )}
            {ordersQuery.data && ordersQuery.data.length > 0 && (
              <div className="space-y-3">
                {ordersQuery.data.map((order) => (
                  <Link key={order.id} href={`/shop/${orgSlug}/account/orders/${order.id}`}>
                    <Card className="transition hover:border-brass">
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-sm font-medium text-ink">
                            {new Date(order.created_at).toLocaleDateString()} · {order.items.length} animal{order.items.length === 1 ? "" : "s"}
                          </p>
                          <p className="text-xs text-muted">KES {Number(order.total_amount).toLocaleString()}</p>
                        </div>
                        <StatusBadge status={order.status} />
                      </div>
                    </Card>
                  </Link>
                ))}
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
