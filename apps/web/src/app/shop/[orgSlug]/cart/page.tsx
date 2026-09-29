"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useMutation } from "@tanstack/react-query";
import { ShopHeader } from "@/components/shop-header";
import { Card, Button, Input, Select, ErrorState, EmptyState } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import { useCart, removeFromCart, updateCartQuantity, clearCart } from "@/lib/cart";
import type { PublicOrderConfirmation } from "@/lib/types";

export default function CartPage() {
  const { orgSlug } = useParams<{ orgSlug: string }>();
  const router = useRouter();
  const cart = useCart(orgSlug);
  const [checkoutOpen, setCheckoutOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const subtotal = cart.reduce((sum, item) => sum + Number(item.price) * Number(item.quantity), 0);

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
        body: JSON.stringify({
          ...body,
          items: cart.map((item) => ({ listing_slug: item.listingSlug, quantity: item.quantity })),
        }),
      }),
    onSuccess: (confirmation) => {
      clearCart(orgSlug);
      router.push(`/shop/${orgSlug}/orders/${confirmation.order_id}?email=${encodeURIComponent(confirmation.customer_email)}`);
    },
    onError: (err) =>
      setError(
        err instanceof ApiError
          ? err.message
          : "Checkout failed - one or more items may no longer be available in the quantity requested",
      ),
  });

  return (
    <div className="min-h-screen bg-paper">
      <ShopHeader orgSlug={orgSlug} />
      <main className="mx-auto max-w-2xl px-6 py-10">
        <h1 className="mb-6 font-display text-2xl text-forest">Your cart</h1>

        {cart.length === 0 ? (
          <EmptyState
            title="Your cart is empty"
            body="Browse the shop and add an animal or some crop produce to get started."
          />
        ) : (
          <>
            <Card className="mb-6">
              <ul className="divide-y divide-hairline/60">
                {cart.map((item) => (
                  <li key={item.listingSlug} className="flex items-center justify-between gap-4 py-3">
                    <div className="flex-1">
                      <p className="font-medium text-ink">{item.title}</p>
                      <p className="text-xs text-muted">
                        KES {Number(item.price).toLocaleString()}{item.listingKind === "crop_produce" ? ` / ${item.unit}` : ""}
                      </p>
                    </div>
                    {item.listingKind === "crop_produce" ? (
                      <input
                        type="number"
                        min="0.01"
                        step="0.01"
                        max={item.maxQuantity ?? undefined}
                        value={item.quantity}
                        onChange={(e) => updateCartQuantity(orgSlug, item.listingSlug, e.target.value)}
                        className="w-20 rounded-md border border-hairline px-2 py-1 text-sm"
                      />
                    ) : (
                      <span className="text-sm text-muted">1 unit</span>
                    )}
                    <p className="w-24 text-right text-sm font-medium text-ink">
                      KES {(Number(item.price) * Number(item.quantity)).toLocaleString()}
                    </p>
                    <button
                      onClick={() => removeFromCart(orgSlug, item.listingSlug)}
                      className="text-xs text-clay hover:underline"
                    >
                      Remove
                    </button>
                  </li>
                ))}
              </ul>
              <div className="mt-4 flex justify-between border-t border-hairline pt-3">
                <span className="font-medium text-ink">Subtotal</span>
                <span className="font-display text-xl text-forest">KES {subtotal.toLocaleString()}</span>
              </div>
            </Card>

            {!checkoutOpen ? (
              <div className="flex gap-2">
                <Link href={`/shop/${orgSlug}`} className="flex-1">
                  <Button variant="ghost" className="w-full">Continue browsing</Button>
                </Link>
                <Button className="flex-1" onClick={() => setCheckoutOpen(true)}>
                  Proceed to checkout
                </Button>
              </div>
            ) : (
              <Card>
                <CheckoutForm
                  error={error}
                  pending={checkout.isPending}
                  onSubmit={(body) => {
                    setError(null);
                    checkout.mutate(body);
                  }}
                />
              </Card>
            )}
          </>
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
      className="space-y-3"
    >
      {error && <ErrorState message={error} />}
      <p className="text-sm text-muted">No account needed - just your contact details to complete the order.</p>
      <Input id="cart-checkout-name" label="Full name" required value={name} onChange={(e) => setName(e.target.value)} />
      <Input id="cart-checkout-email" label="Email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
      <Input id="cart-checkout-phone" label="Phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
      <Select id="cart-checkout-delivery" label="Delivery" value={deliveryOption} onChange={(e) => setDeliveryOption(e.target.value)}>
        <option value="pickup">Farm pickup</option>
        <option value="delivery">Delivery</option>
      </Select>
      {deliveryOption === "delivery" && (
        <Input id="cart-checkout-address" label="Delivery address" required value={address} onChange={(e) => setAddress(e.target.value)} />
      )}
      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Placing order…" : "Place order"}
      </Button>
    </form>
  );
}
