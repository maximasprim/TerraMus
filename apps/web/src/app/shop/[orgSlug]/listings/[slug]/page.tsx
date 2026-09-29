"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation } from "@tanstack/react-query";
import { ShopHeader } from "@/components/shop-header";
import { Card, Button, Input, Select, ErrorState } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import type { PublicListing, PublicOrderConfirmation } from "@/lib/types";

export default function ListingDetailPage() {
  const { orgSlug, slug } = useParams<{ orgSlug: string; slug: string }>();
  const router = useRouter();
  const [checkoutOpen, setCheckoutOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: listing, isLoading, error: loadError } = useQuery<PublicListing>({
    queryKey: ["public-listing", orgSlug, slug],
    queryFn: () => apiFetch<PublicListing>(`/api/v1/public/${orgSlug}/listings/${slug}`, { auth: false }),
  });

  const checkout = useMutation({
    mutationFn: (body: {
      customer_name: string;
      customer_email: string;
      customer_phone?: string;
      delivery_option: string;
      delivery_address?: string;
    }) =>
      apiFetch<PublicOrderConfirmation>(`/api/v1/public/${orgSlug}/orders`, {
        method: "POST",
        auth: false,
        body: JSON.stringify({ ...body, items: [{ listing_slug: slug }] }),
      }),
    onSuccess: (confirmation) => {
      router.push(`/shop/${orgSlug}/orders/${confirmation.order_id}?email=${encodeURIComponent(confirmation.customer_email)}`);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Checkout failed - the listing may no longer be available"),
  });

  return (
    <div className="min-h-screen bg-paper">
      <ShopHeader orgSlug={orgSlug} />
      <main className="mx-auto max-w-2xl px-6 py-10">
        {loadError && (
          <ErrorState message={loadError instanceof ApiError ? loadError.message : "This listing is no longer available"} />
        )}
        {isLoading && <p className="text-sm text-muted">Loading…</p>}

        {listing && (
          <Card>
            <h1 className="font-display text-2xl text-forest">{listing.title}</h1>
            <p className="mb-4 text-sm capitalize text-muted">
              {listing.species}
              {listing.breed ? ` · ${listing.breed}` : ""} · {listing.sex}
              {listing.county ? ` · ${listing.county}` : ""}
            </p>
            {listing.description && <p className="mb-4 text-sm text-ink">{listing.description}</p>}
            <dl className="mb-4 space-y-1 text-sm">
              {listing.current_weight && (
                <div className="flex justify-between border-b border-hairline/60 pb-1">
                  <dt className="text-muted">Weight</dt>
                  <dd className="text-ink">{listing.current_weight} kg</dd>
                </div>
              )}
              <div className="flex justify-between border-b border-hairline/60 pb-1">
                <dt className="text-muted">Health</dt>
                <dd className="capitalize text-ink">{listing.health_status.replace(/_/g, " ")}</dd>
              </div>
            </dl>

            <p className="mb-4 font-display text-3xl text-forest">
              {listing.pricing_type === "fixed" && listing.price
                ? `KES ${Number(listing.price).toLocaleString()}`
                : listing.pricing_type.replace(/_/g, " ")}
            </p>

            {listing.pricing_type !== "fixed" ? (
              <p className="rounded-md border border-hairline bg-white/60 px-4 py-3 text-sm text-muted">
                This listing requires a quote - please contact the farm directly.
              </p>
            ) : !checkoutOpen ? (
              <Button onClick={() => setCheckoutOpen(true)} className="w-full">
                Reserve this animal
              </Button>
            ) : (
              <CheckoutForm
                error={error}
                pending={checkout.isPending}
                onSubmit={(body) => {
                  setError(null);
                  checkout.mutate(body);
                }}
              />
            )}
          </Card>
        )}
      </main>
    </div>
  );
}

function CheckoutForm({
  onSubmit,
  error,
  pending,
}: {
  onSubmit: (body: {
    customer_name: string;
    customer_email: string;
    customer_phone?: string;
    delivery_option: string;
    delivery_address?: string;
  }) => void;
  error: string | null;
  pending: boolean;
}) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [deliveryOption, setDeliveryOption] = useState("pickup");
  const [address, setAddress] = useState("");

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({
          customer_name: name,
          customer_email: email,
          customer_phone: phone || undefined,
          delivery_option: deliveryOption,
          delivery_address: deliveryOption === "delivery" ? address : undefined,
        });
      }}
      className="space-y-3 border-t border-hairline pt-4"
    >
      {error && <ErrorState message={error} />}
      <p className="text-sm text-muted">No account needed - just your contact details to complete the order.</p>
      <Input id="checkout-name" label="Full name" required value={name} onChange={(e) => setName(e.target.value)} />
      <Input id="checkout-email" label="Email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
      <Input id="checkout-phone" label="Phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
      <Select id="checkout-delivery" label="Delivery" value={deliveryOption} onChange={(e) => setDeliveryOption(e.target.value)}>
        <option value="pickup">Farm pickup</option>
        <option value="delivery">Delivery</option>
      </Select>
      {deliveryOption === "delivery" && (
        <Input id="checkout-address" label="Delivery address" required value={address} onChange={(e) => setAddress(e.target.value)} />
      )}
      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Placing order…" : "Place order"}
      </Button>
    </form>
  );
}
