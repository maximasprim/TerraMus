"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Check, MapPin, MessageCircle, Minus, Plus, ShieldCheck, Truck } from "lucide-react";
import { ShopHeader } from "@/components/shop-header";
import { ReviewsSection } from "@/components/shop-reviews";
import { ProductCard, ProductGallery, SectionHeading } from "@/components/shop-ui";
import { Button, ErrorState, Input, Select } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import { addToCart, useCart } from "@/lib/cart";
import {
  cartItemFor,
  categoryKey,
  humanize,
  isFixedPrice,
  kes,
  shopPath,
  usePageTitle,
  useShopListings,
  useShopProfile,
  whatsappLink,
} from "@/lib/shop-utils";
import type { PublicListing, PublicOrderConfirmation } from "@/lib/types";

function ageText(dob: string | null): string | null {
  if (!dob) return null;
  const d = new Date(dob);
  if (isNaN(d.getTime())) return null;
  const now = new Date();
  const months = Math.max(0, (now.getFullYear() - d.getFullYear()) * 12 + now.getMonth() - d.getMonth());
  if (months < 12) return `${months} mo`;
  const y = Math.floor(months / 12);
  const m = months % 12;
  return m ? `${y} yr ${m} mo` : `${y} yr`;
}

export default function ListingDetailPage() {
  const { orgSlug, slug } = useParams<{ orgSlug: string; slug: string }>();
  const router = useRouter();
  const [checkoutOpen, setCheckoutOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [qty, setQty] = useState("1");

  const cart = useCart(orgSlug);
  const profile = useShopProfile(orgSlug);
  const all = useShopListings(orgSlug);

  const { data: listing, isLoading, error: loadError } = useQuery<PublicListing>({
    queryKey: ["public-listing", orgSlug, slug],
    queryFn: () => apiFetch<PublicListing>(`/api/v1/public/${orgSlug}/listings/${slug}`, { auth: false }),
  });

  usePageTitle(listing?.title, profile.data?.farm_name);

  const isCrop = listing?.listing_kind === "crop_produce";
  const maxQty = listing?.quantity_available ? Number(listing.quantity_available) : null;
  const qtyNum = Number(qty);
  const qtyValid = !isCrop || (qtyNum > 0 && (maxQty === null || qtyNum <= maxQty));
  const soldOut = isCrop && maxQty !== null && maxQty <= 0;
  const inCart = cart.some((i) => i.listingSlug === slug);

  const related = useMemo(
    () => (all.data ?? []).filter((l) => l.slug !== slug && listing && l.listing_kind === listing.listing_kind).slice(0, 4),
    [all.data, slug, listing],
  );

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
          items: [{ listing_slug: slug, quantity: isCrop ? String(qtyNum) : "1" }],
        }),
      }),
    onSuccess: (confirmation) => {
      router.push(`/shop/${orgSlug}/orders/${confirmation.order_id}?email=${encodeURIComponent(confirmation.customer_email)}`);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Checkout failed - the listing may no longer be available"),
  });

  const specs: [string, string][] = [];
  if (listing) {
    specs.push(["Type", isCrop ? "Fresh produce" : "Livestock"]);
    if (isCrop) {
      if (listing.crop_type) specs.push(["Crop", humanize(listing.crop_type)]);
      if (listing.variety) specs.push(["Variety", listing.variety]);
      if (listing.unit) specs.push(["Sold per", listing.unit]);
      if (listing.quantity_available) specs.push(["In stock", `${listing.quantity_available} ${listing.unit ?? ""}`.trim()]);
    } else {
      if (listing.species) specs.push(["Species", listing.species]);
      if (listing.breed) specs.push(["Breed", listing.breed]);
      if (listing.sex) specs.push(["Sex", listing.sex]);
      const age = ageText(listing.date_of_birth);
      if (age) specs.push(["Age", age]);
      if (listing.current_weight) specs.push(["Weight", `${listing.current_weight} kg`]);
      // health_status is only populated for animals (null for crop produce)
      if (listing.health_status) specs.push(["Health", humanize(listing.health_status)]);
    }
    if (listing.county) specs.push(["Location", listing.county]);
  }

  const wa = whatsappLink(profile.data?.phone, listing ? `Hello, I'm interested in "${listing.title}".` : undefined);
  const total = listing && isFixedPrice(listing) ? Number(listing.price) * (isCrop ? qtyNum || 0 : 1) : null;

  return (
    <div className="min-h-screen bg-paper">
      <ShopHeader orgSlug={orgSlug} />
      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
        {loadError && (
          <ErrorState message={loadError instanceof ApiError ? loadError.message : "This listing is no longer available"} />
        )}
        {isLoading && <p className="text-sm text-muted">Loading…</p>}

        {listing && (
          <>
            <nav className="mb-4 text-xs text-muted" aria-label="Breadcrumb">
              <Link href={shopPath(orgSlug)} className="hover:underline">Home</Link> &rsaquo;{" "}
              <Link href={shopPath(orgSlug, "/store")} className="hover:underline">Store</Link> &rsaquo;{" "}
              <Link href={shopPath(orgSlug, `/store?kind=${listing.listing_kind}&category=${encodeURIComponent(categoryKey(listing))}`)} className="capitalize hover:underline">
                {humanize(categoryKey(listing))}
              </Link>{" "}
              &rsaquo; <span className="text-ink">{listing.title}</span>
            </nav>

            <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)_20rem]">
              <ProductGallery listing={listing} className="lg:sticky lg:top-40 lg:h-fit" />

              <div>
                {listing.featured && (
                  <span className="mb-2 inline-block rounded bg-brass px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-ink">Featured</span>
                )}
                <h1 className="font-display text-3xl text-forest">{listing.title}</h1>
                <p className="mt-1 flex items-center gap-2 text-sm capitalize text-muted">
                  {humanize(categoryKey(listing))}
                  {listing.county && (
                    <span className="flex items-center gap-1 normal-case"><MapPin className="h-3.5 w-3.5" aria-hidden /> {listing.county}</span>
                  )}
                </p>

                <p className="mt-4 border-t border-hairline pt-4 font-display text-3xl text-forest">
                  {isFixedPrice(listing) ? kes(listing.price as string) : <span className="capitalize">{humanize(listing.pricing_type)}</span>}
                  {isFixedPrice(listing) && isCrop && listing.unit && <span className="text-base font-normal text-muted"> / {listing.unit}</span>}
                </p>

                {listing.description && (
                  <div className="mt-5">
                    <h2 className="mb-1 font-semibold text-ink">About this {isCrop ? "product" : "animal"}</h2>
                    <p className="whitespace-pre-line text-sm text-ink/90">{listing.description}</p>
                  </div>
                )}

                <div className="mt-6">
                  <h2 className="mb-2 font-semibold text-ink">Details</h2>
                  <dl className="divide-y divide-hairline/60 rounded-lg border border-hairline bg-white text-sm">
                    {specs.map(([k, v]) => (
                      <div key={k} className="flex justify-between gap-4 px-4 py-2">
                        <dt className="text-muted">{k}</dt>
                        <dd className="text-right capitalize text-ink">{v}</dd>
                      </div>
                    ))}
                  </dl>
                </div>
              </div>

              <aside className="h-fit rounded-xl border border-hairline bg-white p-5 lg:sticky lg:top-40">
                {isFixedPrice(listing) ? (
                  <>
                    <p className="font-display text-2xl text-forest">{total !== null ? kes(total) : ""}</p>
                    <p className={`mt-1 text-sm font-medium ${soldOut ? "text-red-600" : "text-forest"}`}>
                      {soldOut ? "Out of stock" : isCrop && maxQty !== null ? `In stock · ${maxQty} ${listing.unit ?? ""} available` : "Available"}
                    </p>

                    {isCrop && !soldOut && (
                      <div className="mt-4">
                        <label htmlFor="qty" className="mb-1 block text-sm text-muted">Quantity{listing.unit ? ` (${listing.unit})` : ""}</label>
                        <div className="flex items-center overflow-hidden rounded-md border border-hairline">
                          <button type="button" aria-label="Decrease quantity" onClick={() => setQty(String(Math.max(1, Math.floor(qtyNum || 1) - 1)))} className="p-2.5 hover:bg-forest/5"><Minus className="h-4 w-4" /></button>
                          <input id="qty" inputMode="decimal" value={qty} onChange={(e) => setQty(e.target.value)} className="w-full border-x border-hairline py-2 text-center outline-none" />
                          <button type="button" aria-label="Increase quantity" onClick={() => setQty(String(Math.floor(qtyNum || 0) + 1))} className="p-2.5 hover:bg-forest/5"><Plus className="h-4 w-4" /></button>
                        </div>
                        {!qtyValid && (
                          <p className="mt-1 text-xs text-red-600">{maxQty !== null && qtyNum > maxQty ? `Only ${maxQty} available` : "Enter a quantity above zero"}</p>
                        )}
                      </div>
                    )}

                    {!soldOut && (
                      <div className="mt-4 space-y-2">
                        {inCart ? (
                          <Link href={shopPath(orgSlug, "/cart")} className="flex w-full items-center justify-center gap-2 rounded-md border border-forest px-4 py-2.5 text-sm font-semibold text-forest hover:bg-forest/5">
                            <Check className="h-4 w-4" aria-hidden /> In your cart · View cart
                          </Link>
                        ) : (
                          <button
                            type="button"
                            disabled={!qtyValid}
                            onClick={() => addToCart(orgSlug, cartItemFor(listing, String(qtyNum)))}
                            className="w-full rounded-md bg-brass px-4 py-2.5 text-sm font-semibold text-ink hover:bg-brass/90 disabled:opacity-50"
                          >
                            Add to cart
                          </button>
                        )}
                        {!checkoutOpen && (
                          <Button onClick={() => setCheckoutOpen(true)} disabled={!qtyValid} className="w-full">
                            Buy now
                          </Button>
                        )}
                      </div>
                    )}

                    {checkoutOpen && !soldOut && (
                      <CheckoutForm
                        error={error}
                        pending={checkout.isPending}
                        onSubmit={(body) => {
                          setError(null);
                          checkout.mutate(body);
                        }}
                      />
                    )}
                  </>
                ) : (
                  <>
                    <p className="font-semibold text-ink">Request a quote</p>
                    <p className="mt-1 text-sm text-muted">This listing is priced on request - contact the farm and we&apos;ll get back to you.</p>
                    <div className="mt-4 space-y-2">
                      {wa && (
                        <a href={wa} target="_blank" rel="noreferrer" className="flex w-full items-center justify-center gap-2 rounded-md bg-brass px-4 py-2.5 text-sm font-semibold text-ink hover:bg-brass/90">
                          <MessageCircle className="h-4 w-4" aria-hidden /> Ask on WhatsApp
                        </a>
                      )}
                      <Link href={shopPath(orgSlug, `/contact?product=${encodeURIComponent(listing.slug)}`)} className="flex w-full items-center justify-center rounded-md border border-forest px-4 py-2.5 text-sm font-semibold text-forest hover:bg-forest/5">
                        Send an enquiry
                      </Link>
                    </div>
                  </>
                )}

                {isFixedPrice(listing) && (
                  <Link href={shopPath(orgSlug, `/contact?product=${encodeURIComponent(listing.slug)}`)} className="mt-3 block text-center text-sm text-forest underline underline-offset-4">
                    Ask a question about this {isCrop ? "product" : "animal"}
                  </Link>
                )}

                <ul className="mt-5 space-y-2 border-t border-hairline pt-4 text-xs text-muted">
                  <li className="flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-forest" aria-hidden /> Sold directly by {profile.data?.farm_name ?? "the farm"}</li>
                  <li className="flex items-center gap-2"><Truck className="h-4 w-4 text-forest" aria-hidden /> Farm pickup or delivery at checkout</li>
                  <li className="flex items-center gap-2"><Check className="h-4 w-4 text-forest" aria-hidden /> Pay securely after you place your order</li>
                </ul>
              </aside>
            </div>

            <ReviewsSection orgSlug={orgSlug} slug={slug} />

            {related.length > 0 && (
              <section className="mt-14">
                <SectionHeading title="You may also like" href={shopPath(orgSlug, `/store?kind=${listing.listing_kind}`)} />
                <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
                  {related.map((l) => (
                    <ProductCard key={l.slug} listing={l} orgSlug={orgSlug} />
                  ))}
                </div>
              </section>
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
      className="mt-4 space-y-3 border-t border-hairline pt-4"
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
