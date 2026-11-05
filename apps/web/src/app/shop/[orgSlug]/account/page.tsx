"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight, Clock, LogOut, MapPin, Package, Phone, ShoppingBag, Wallet } from "lucide-react";
import clsx from "clsx";
import { ShopHeader } from "@/components/shop-header";
import { Card, Button, StatusBadge, ErrorState } from "@/components/ui";
import { IN_PROGRESS, OrderProgress, PAID_OR_BEYOND } from "@/components/order-progress";
import { apiFetch, getAccessToken, clearTokens, ApiError } from "@/lib/api";
import type { MyAccount, MyOrder } from "@/lib/types";
import welcomeBg from "../../../../../public/images/banner.jpg";

const kes = (n: number) => `KES ${n.toLocaleString()}`;
type Filter = "all" | "active" | "past";

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase() || "?";
}

function Skeleton() {
  return (
    <div className="animate-pulse space-y-4" aria-label="Loading your account">
      <div className="h-36 rounded-xl bg-hairline/60" />
      <div className="grid grid-cols-3 gap-3"><div className="h-24 rounded-lg bg-hairline/60" /><div className="h-24 rounded-lg bg-hairline/60" /><div className="h-24 rounded-lg bg-hairline/60" /></div>
      <div className="h-40 rounded-lg bg-hairline/60" />
    </div>
  );
}

function StatTile({ icon, label, value, hint }: { icon: React.ReactNode; label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-hairline bg-white/70 p-4">
      <div className="mb-2 flex h-8 w-8 items-center justify-center rounded-full bg-forest/10 text-forest">{icon}</div>
      <p className="font-display text-xl text-forest sm:text-2xl">{value}</p>
      <p className="text-xs font-medium text-ink">{label}</p>
      {hint && <p className="text-[11px] text-muted">{hint}</p>}
    </div>
  );
}

export default function CustomerAccountPage() {
  const { orgSlug } = useParams<{ orgSlug: string }>();
  const router = useRouter();
  // Sign-in state lives in the browser, so it is read after the page mounts; the server and the first browser render
  // both show the same loading placeholder, which avoids a server/browser mismatch.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const loggedIn = mounted && !!getAccessToken();
  const [filter, setFilter] = useState<Filter>("all");

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

  if (!mounted) {
    return (
      <div className="min-h-screen bg-paper">
        <ShopHeader orgSlug={orgSlug} />
        <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6 sm:py-10"><Skeleton /></main>
      </div>
    );
  }

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
  const account = accountQuery.data;
  const orders = ordersQuery.data;

  const inProgress = (orders ?? []).filter((o) => IN_PROGRESS.has(o.status));
  const spent = (orders ?? []).filter((o) => PAID_OR_BEYOND.has(o.status)).reduce((sum, o) => sum + Number(o.total_amount), 0);
  const shown = (orders ?? []).filter((o) => (filter === "all" ? true : filter === "active" ? IN_PROGRESS.has(o.status) : !IN_PROGRESS.has(o.status)));
  const logout = () => { clearTokens(); router.push(`/shop/${orgSlug}`); };

  return (
    <div className="min-h-screen bg-paper">
      <ShopHeader orgSlug={orgSlug} />
      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 sm:py-10">
        {isWrongAccountType && (
          <ErrorState message="This login isn't a customer account. Log in with a customer email instead." />
        )}
        {accountQuery.error && !isWrongAccountType && (
          <ErrorState message={accountQuery.error instanceof ApiError ? accountQuery.error.message : "Failed to load your account"} />
        )}
        {accountQuery.isLoading && <Skeleton />}

        {account && (
          <div className="space-y-6">
            {/* Welcome banner */}
            <section className="relative overflow-hidden rounded-xl p-5 text-paper shadow-sm sm:p-7"
            style={{ backgroundImage: `url("${welcomeBg.src}")`, backgroundSize: "cover", backgroundPosition: "center" }}
            >
              <div className="absolute inset-0 bg-gradient-to-br from-forest/10 to-forest-light/40" aria-hidden />
              <div className="relative flex flex-wrap items-center justify-between gap-4">
                <div className="flex items-center gap-4">
                  <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-brass font-display text-xl text-white" aria-hidden>
                    {initials(account.full_name)}
                  </span>
                  <div className="min-w-0">
                    <p className="text-xs uppercase tracking-wider text-paper/80">Welcome back</p>
                    <h1 className="truncate font-display text-2xl sm:text-3xl">{account.full_name}</h1>
                    <p className="break-words text-sm text-paper/80">
                      {account.email} · Member since {new Date(account.created_at).toLocaleDateString(undefined, { month: "short", year: "numeric" })}
                    </p>
                  </div>
                </div>
                <div className="flex gap-2">
                  <Link href={`/shop/${orgSlug}/store`} className="inline-flex items-center gap-1.5 rounded-md bg-brass px-4 py-2 text-sm font-medium text-white hover:bg-brass-dark">
                    <ShoppingBag className="h-4 w-4" aria-hidden /> Continue shopping
                  </Link>
                  <button onClick={logout} className="inline-flex items-center gap-1.5 rounded-md border border-white/30 px-4 py-2 text-sm font-medium text-paper hover:bg-white/10">
                    <LogOut className="h-4 w-4" aria-hidden /> Log out
                  </button>
                </div>
              </div>
            </section>

            {/* At a glance */}
            <section className="grid grid-cols-3 gap-3">
              <StatTile icon={<Package className="h-4 w-4" />} label="Orders" value={orders ? String(orders.length) : "-"} hint="all time" />
              <StatTile icon={<Clock className="h-4 w-4" />} label="In progress" value={orders ? String(inProgress.length) : "-"} hint="on their way to you" />
              <StatTile icon={<Wallet className="h-4 w-4" />} label="Spent so far" value={orders ? kes(spent) : "-"} hint="paid orders" />
            </section>

            <div className="grid gap-6 lg:grid-cols-3">
              {/* Orders */}
              <section className="lg:col-span-2">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <h2 className="font-display text-xl text-forest">Your orders</h2>
                  {orders && orders.length > 0 && (
                    <div className="flex gap-1 rounded-full border border-hairline bg-white p-0.5 text-xs" role="tablist" aria-label="Filter orders">
                      {([["all", "All"], ["active", "In progress"], ["past", "Past"]] as [Filter, string][]).map(([key, label]) => (
                        <button
                          key={key} role="tab" aria-selected={filter === key} onClick={() => setFilter(key)}
                          className={clsx("rounded-full px-3 py-1 font-medium transition-colors", filter === key ? "bg-forest text-paper" : "text-muted hover:text-ink")}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                  )}
                </div>

                {ordersQuery.isLoading && <div className="h-32 animate-pulse rounded-lg bg-hairline/60" />}
                {orders && orders.length === 0 && (
                  <div className="rounded-xl border border-dashed border-hairline bg-white/50 px-6 py-12 text-center">
                    <span className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-forest/10 text-forest"><ShoppingBag className="h-5 w-5" aria-hidden /></span>
                    <p className="font-display text-lg text-forest">No orders yet</p>
                    <p className="mx-auto mb-4 mt-1 max-w-xs text-sm text-muted">Browse the farm&apos;s listings to place your first order.</p>
                    <Link href={`/shop/${orgSlug}/store`} className="inline-block rounded-md bg-forest px-5 py-2 text-sm font-medium text-paper hover:bg-forest-dark">Browse the shop</Link>
                  </div>
                )}
                {orders && orders.length > 0 && shown.length === 0 && (
                  <p className="rounded-lg border border-hairline bg-white/50 px-4 py-8 text-center text-sm text-muted">No {filter === "active" ? "orders in progress" : "past orders"}.</p>
                )}
                <div className="space-y-3">
                  {shown.map((order) => (
                    <Link key={order.id} href={`/shop/${orgSlug}/account/orders/${order.id}`} className="group block">
                      <div className="rounded-lg border border-hairline bg-white/70 p-4 transition group-hover:border-brass group-hover:shadow-sm">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className="text-sm font-medium text-ink">
                              {new Date(order.created_at).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}
                              <span className="font-normal text-muted"> · {order.items.length} animal{order.items.length === 1 ? "" : "s"}</span>
                            </p>
                            <p className="font-display text-lg text-forest">{kes(Number(order.total_amount))}</p>
                          </div>
                          <div className="flex items-center gap-2">
                            <StatusBadge status={order.status} />
                            <ChevronRight className="h-4 w-4 text-muted transition group-hover:translate-x-0.5 group-hover:text-brass" aria-hidden />
                          </div>
                        </div>
                        <div className="mt-3"><OrderProgress status={order.status} compact /></div>
                      </div>
                    </Link>
                  ))}
                </div>
              </section>

              {/* Profile */}
              <aside>
                <h2 className="mb-3 font-display text-xl text-forest">Your details</h2>
                <div className="space-y-3 rounded-lg border border-hairline bg-white/70 p-4 text-sm">
                  <div className="flex items-start gap-3"><Phone className="mt-0.5 h-4 w-4 shrink-0 text-brass" aria-hidden /><div><p className="text-xs text-muted">Phone</p><p className="text-ink">{account.phone || "Not provided"}</p></div></div>
                  <div className="flex items-start gap-3"><MapPin className="mt-0.5 h-4 w-4 shrink-0 text-brass" aria-hidden /><div><p className="text-xs text-muted">Location</p><p className="text-ink">{account.location || "Not provided"}</p></div></div>
                  <div className="flex items-start gap-3"><Package className="mt-0.5 h-4 w-4 shrink-0 text-brass" aria-hidden /><div><p className="text-xs text-muted">Account type</p><p className="capitalize text-ink">{account.customer_type.replace(/_/g, " ")}</p></div></div>
                </div>
              </aside>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
