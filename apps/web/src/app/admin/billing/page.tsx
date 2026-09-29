"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { Card, Button, Input, ErrorState, StatusBadge } from "@/components/ui";
import { apiFetch, ApiError, API_BASE, getAccessToken } from "@/lib/api";
import type { SubscriptionOut, SubscriptionTierOut, SubscriptionPaymentOut } from "@/lib/billing-types";

/** A PDF download needs the Bearer token attached, so a plain <a href>
 * pointing at the API won't work (browser navigation doesn't carry the
 * app's Authorization header) - fetch as a blob with the header, then
 * trigger a download via a throwaway object URL. */
async function downloadReceipt(paymentId: string) {
  const token = getAccessToken();
  const resp = await fetch(`${API_BASE}/api/v1/billing/payments/${paymentId}/receipt.pdf`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!resp.ok) return;
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `receipt_${paymentId}.pdf`;
  a.click();
  URL.revokeObjectURL(url);
}

export default function BillingPage() {
  const queryClient = useQueryClient();
  const [phone, setPhone] = useState("");
  const [selectedTier, setSelectedTier] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [awaitingPayment, setAwaitingPayment] = useState(false);

  const subscriptionQuery = useQuery<SubscriptionOut>({
    queryKey: ["subscription"],
    queryFn: () => apiFetch<SubscriptionOut>("/api/v1/billing/subscription"),
    // Poll while we're waiting on an M-Pesa STK push to be confirmed by the
    // webhook - the UI has no way to know the moment Safaricom calls back,
    // so short-polling is the simplest correct approach without adding
    // websockets for one screen. Stops automatically once awaitingPayment
    // is cleared (payment resolved, or the user navigates away).
    refetchInterval: awaitingPayment ? 3000 : false,
  });

  const tiersQuery = useQuery<SubscriptionTierOut[]>({
    queryKey: ["subscription-tiers"],
    queryFn: () => apiFetch<SubscriptionTierOut[]>("/api/v1/billing/tiers"),
  });

  const paymentsQuery = useQuery<SubscriptionPaymentOut[]>({
    queryKey: ["subscription-payments"],
    queryFn: () => apiFetch<SubscriptionPaymentOut[]>("/api/v1/billing/payments"),
  });

  const subscribe = useMutation({
    mutationFn: (body: { tier_slug: string; phone_number: string }) =>
      apiFetch<SubscriptionPaymentOut>("/api/v1/billing/subscribe", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      setError(null);
      setAwaitingPayment(true);
      queryClient.invalidateQueries({ queryKey: ["subscription-payments"] });
      // Stop polling automatically after 2 minutes even if nothing came
      // through, rather than polling forever if the STK push was never
      // completed on the phone.
      setTimeout(() => setAwaitingPayment(false), 120_000);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Failed to start payment"),
  });

  // Once the subscription's tier matches what we just paid for and it's
  // active, stop polling - no need to wait out the full 2 minutes.
  if (awaitingPayment && subscriptionQuery.data?.status === "active" && subscriptionQuery.data.tier.slug === selectedTier) {
    setAwaitingPayment(false);
  }

  const subscription = subscriptionQuery.data;

  return (
    <AdminShell>
      <h1 className="mb-1 font-display text-2xl text-forest">Billing</h1>
      <p className="mb-6 text-sm text-muted">Your plan, usage limits, and payment history.</p>

      {subscriptionQuery.error && (
        <ErrorState message={subscriptionQuery.error instanceof ApiError ? subscriptionQuery.error.message : "Failed to load subscription"} />
      )}

      {subscription && (
        <Card className="mb-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-medium uppercase tracking-wider text-muted">Current plan</p>
              <p className="font-display text-2xl text-forest">{subscription.tier.name}</p>
            </div>
            <StatusBadge status={subscription.status === "active" ? "active" : subscription.status === "past_due" ? "failed" : "pending"} />
          </div>
          <div className="mt-3 flex gap-6 text-sm text-muted">
            <span>KES {subscription.tier.monthly_price_kes.toLocaleString()}/mo</span>
            <span>{subscription.tier.max_users ? `${subscription.tier.max_users} users` : "Unlimited users"}</span>
            <span>{subscription.tier.max_animals ? `${subscription.tier.max_animals} animals` : "Unlimited animals"}</span>
            {subscription.current_period_end && (
              <span>Renews {new Date(subscription.current_period_end).toLocaleDateString()}</span>
            )}
          </div>
        </Card>
      )}

      {awaitingPayment && (
        <div className="mb-6 rounded-lg border border-brass/30 bg-brass/5 px-4 py-3 text-sm text-brass-dark">
          Check your phone for the M-Pesa prompt and enter your PIN. This page will update automatically
          once payment is confirmed.
        </div>
      )}

      <p className="mb-3 text-sm font-medium text-ink">Available plans</p>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
        {(tiersQuery.data ?? []).map((tier) => {
          const isCurrent = subscription?.tier.slug === tier.slug;
          return (
            <Card key={tier.id} className={isCurrent ? "border-brass" : undefined}>
              <p className="font-display text-lg text-forest">{tier.name}</p>
              <p className="mt-1 text-2xl font-medium text-ink">
                KES {tier.monthly_price_kes.toLocaleString()}
                <span className="text-sm font-normal text-muted">/mo</span>
              </p>
              <p className="mt-2 text-xs text-muted">
                {tier.max_users ? `${tier.max_users} users` : "Unlimited users"} ·{" "}
                {tier.max_animals ? `${tier.max_animals} animals` : "Unlimited animals"}
              </p>
              {isCurrent ? (
                <p className="mt-4 text-center text-xs font-medium text-brass-dark">Current plan</p>
              ) : (
                <Button
                  variant="ghost"
                  className="mt-4 w-full text-xs"
                  disabled={tier.monthly_price_kes <= 0}
                  onClick={() => setSelectedTier(tier.slug)}
                >
                  {tier.monthly_price_kes <= 0 ? "Contact us to downgrade" : "Switch to this plan"}
                </Button>
              )}
            </Card>
          );
        })}
      </div>

      {selectedTier && (
        <Card className="mt-6 max-w-sm">
          <p className="mb-3 text-sm font-medium text-ink">
            Pay for {tiersQuery.data?.find((t) => t.slug === selectedTier)?.name} via M-Pesa
          </p>
          {error && <div className="mb-3"><ErrorState message={error} /></div>}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              subscribe.mutate({ tier_slug: selectedTier, phone_number: phone });
            }}
            className="space-y-3"
          >
            <Input
              id="mpesa-phone" label="M-Pesa phone number" placeholder="254712345678" required
              value={phone} onChange={(e) => setPhone(e.target.value)}
            />
            <Button type="submit" disabled={subscribe.isPending} className="w-full">
              {subscribe.isPending ? "Sending prompt…" : "Pay now"}
            </Button>
          </form>
        </Card>
      )}

      <p className="mb-3 mt-8 text-sm font-medium text-ink">Payment history</p>
      {paymentsQuery.data && paymentsQuery.data.length === 0 && (
        <p className="text-sm text-muted">No payments yet.</p>
      )}
      {paymentsQuery.data && paymentsQuery.data.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-hairline">
          <table className="w-full text-left text-sm">
            <thead className="bg-forest text-paper">
              <tr>
                <th className="px-4 py-3 font-medium">Date</th>
                <th className="px-4 py-3 font-medium">Amount</th>
                <th className="px-4 py-3 font-medium">Reference</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium" />
              </tr>
            </thead>
            <tbody>
              {paymentsQuery.data.map((p, i) => (
                <tr key={p.id} className={i % 2 === 0 ? "bg-white/40" : "bg-white/70"}>
                  <td className="px-4 py-3 text-muted">{new Date(p.initiated_at).toLocaleString()}</td>
                  <td className="px-4 py-3 text-ink">{p.currency} {p.amount.toLocaleString()}</td>
                  <td className="px-4 py-3 font-mono text-xs text-muted">{p.provider_reference || "-"}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={p.status === "successful" ? "completed" : p.status === "failed" ? "failed" : "pending"} />
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Button variant="ghost" className="text-xs" onClick={() => downloadReceipt(p.id)}>
                      Receipt
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </AdminShell>
  );
}
