"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Loader2, Smartphone } from "lucide-react";
import { Button, ErrorState, Input } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import { normaliseKePhone, PHONE_ERROR } from "@/lib/phone";
import type { PaymentMethod } from "@/lib/types";

/** How long after the M-Pesa prompt is sent before we offer "try again". */
const RETRY_AFTER_MS = 45_000;

/**
 * Pay-online panel for an unpaid guest order. Only shows methods the backend
 * says are really configured (GET /public/payment-methods). Paying is
 * asynchronous: we trigger the M-Pesa prompt, then the PARENT page polls the
 * order until the provider's callback marks it paid - the browser never decides
 * a payment succeeded. Offline settlement stays available throughout.
 */
export function PaymentPanel({
  orgSlug,
  orderId,
  email,
  total,
  waiting,
  timedOut,
  onInitiated,
}: {
  orgSlug: string;
  orderId: string;
  email: string;
  total: string;
  waiting: boolean;
  timedOut: boolean;
  onInitiated: () => void;
}) {
  const methods = useQuery<{ methods: PaymentMethod[] }>({
    queryKey: ["public-payment-methods"],
    queryFn: () => apiFetch<{ methods: PaymentMethod[] }>("/api/v1/public/payment-methods", { auth: false }),
    staleTime: 5 * 60_000,
  });
  const mpesa = methods.data?.methods.find((m) => m.provider === "mpesa");

  const [phone, setPhone] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [canRetry, setCanRetry] = useState(false);

  // Offer "try again" a little after the prompt was sent (customer may have dismissed it).
  useEffect(() => {
    if (!waiting) return;
    setCanRetry(false);
    const t = setTimeout(() => setCanRetry(true), RETRY_AFTER_MS);
    return () => clearTimeout(t);
  }, [waiting]);

  const pay = useMutation({
    mutationFn: (normalised: string) =>
      apiFetch(`/api/v1/public/${orgSlug}/orders/${orderId}/pay/mpesa`, {
        method: "POST",
        auth: false,
        body: JSON.stringify({ phone_or_token: normalised, email }),
      }),
    onSuccess: () => {
      setError(null);
      onInitiated();
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Couldn't start the payment - please try again."),
  });

  const submit = () => {
    const normalised = normaliseKePhone(phone);
    if (!normalised) {
      setError(PHONE_ERROR);
      return;
    }
    setError(null);
    pay.mutate(normalised);
  };

  const offline = (
    <p className="mt-4 text-xs text-muted">
      Prefer to pay when you collect or receive your order? Just keep this page&apos;s link - the farm will confirm the
      details with you.
    </p>
  );

  if (methods.isLoading) return null;
  if (!mpesa) {
    return (
      <div className="mt-6 rounded-lg border border-hairline bg-white p-5">
        <h2 className="font-semibold text-ink">Payment</h2>
        <p className="mt-1 text-sm text-muted">
          Online payment isn&apos;t available for this farm yet. Pay on pickup or delivery - the farm will contact you to
          confirm.
        </p>
      </div>
    );
  }

  if (waiting && !timedOut) {
    return (
      <div className="mt-6 rounded-lg border border-brass/40 bg-brass/10 p-5">
        <div className="flex items-start gap-3">
          <Loader2 className="mt-0.5 h-5 w-5 shrink-0 animate-spin text-forest" aria-hidden />
          <div>
            <h2 className="font-semibold text-ink">Check your phone</h2>
            <p className="mt-1 text-sm text-ink/80">
              We sent an M-Pesa prompt for KES {Number(total).toLocaleString()}. Enter your M-Pesa PIN to complete the
              payment - this page updates by itself once it&apos;s confirmed.
            </p>
            {canRetry && (
              <button type="button" onClick={submit} disabled={pay.isPending} className="mt-3 text-sm font-medium text-forest underline underline-offset-4">
                Didn&apos;t get the prompt? Send it again
              </button>
            )}
            {error && <p className="mt-2 text-sm text-clay">{error}</p>}
          </div>
        </div>
        {offline}
      </div>
    );
  }

  return (
    <div className="mt-6 rounded-lg border border-hairline bg-white p-5">
      <h2 className="flex items-center gap-2 font-semibold text-ink">
        <Smartphone className="h-5 w-5 text-forest" aria-hidden /> Pay with {mpesa.label}
      </h2>
      {timedOut && (
        <p className="mt-2 rounded-md bg-brass/10 p-3 text-sm text-ink">
          We haven&apos;t received a confirmation yet. If you completed the payment it may still arrive - refresh this
          page in a minute. Otherwise you can send the prompt again.
        </p>
      )}
      <form
        className="mt-3 space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        {error && <ErrorState message={error} />}
        <Input
          id="mpesa-phone"
          label="M-Pesa phone number"
          type="tel"
          inputMode="tel"
          autoComplete="tel"
          placeholder="0712 345 678"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          required
        />
        <Button type="submit" disabled={pay.isPending} className="w-full">
          {pay.isPending ? "Sending prompt…" : `Pay KES ${Number(total).toLocaleString()}`}
        </Button>
      </form>
      {offline}
    </div>
  );
}
