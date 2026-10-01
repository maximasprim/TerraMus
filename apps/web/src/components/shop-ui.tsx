"use client";

import { useState } from "react";
import Link from "next/link";
import { Beef, Check, ChevronLeft, ChevronRight, Egg, Leaf, MapPin, ShoppingCart, Sprout, Star, Wheat } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { addToCart, useCart } from "@/lib/cart";
import type { PublicListing } from "@/lib/types";
import { cartItemFor, categoryKey, humanize, imageSrc, isFixedPrice, kes, shopPath } from "@/lib/shop-utils";

/* ---------- category art (listings carry no photos, so we draw them) ---------- */

export function iconForCategory(kind: PublicListing["listing_kind"], key: string): LucideIcon {
  const k = key.toLowerCase();
  if (/chicken|poultry|hen|duck|turkey|layer|broiler|quail/.test(k)) return Egg;
  if (kind === "animal") return Beef;
  if (/maize|corn|wheat|rice|sorghum|millet|barley|oat/.test(k)) return Wheat;
  if (/tea|coffee|avocado|mango|banana|fruit|macadamia|vegetable/.test(k)) return Leaf;
  return Sprout;
}

const TONE: Record<PublicListing["listing_kind"], string> = {
  animal: "bg-gradient-to-br from-amber-50 to-orange-100 text-brass",
  crop_produce: "bg-gradient-to-br from-emerald-50 to-lime-100 text-forest",
};

export function CategoryIcon({
  kind,
  categoryKey: key,
  className = "h-10 w-10",
}: {
  kind: PublicListing["listing_kind"];
  categoryKey: string;
  className?: string;
}) {
  const Icon = iconForCategory(kind, key);
  return <Icon className={className} aria-hidden strokeWidth={1.5} />;
}

/** Product card visual: the listing's COVER photo (thumbnail) when the farm has
 * uploaded one, otherwise the illustrated category art. Cards only ever show
 * one photo - the full set lives on the product page (ProductGallery). */
export function ProductVisual({ listing, className = "" }: { listing: PublicListing; className?: string }) {
  const cover = listing.images?.[0];
  const [failed, setFailed] = useState(false);

  if (cover && !failed) {
    return (
      <div className={`relative overflow-hidden bg-hairline/30 ${className}`}>
        {/* eslint-disable-next-line @next/next/no-img-element -- served by the API, not a static asset */}
        <img
          src={imageSrc(cover, true)}
          alt={listing.title}
          loading="lazy"
          onError={() => setFailed(true)}
          className="absolute inset-0 h-full w-full object-cover"
        />
      </div>
    );
  }

  return (
    <div className={`flex items-center justify-center ${TONE[listing.listing_kind]} ${className}`}>
      <CategoryIcon kind={listing.listing_kind} categoryKey={categoryKey(listing)} className="h-1/3 w-1/3 max-h-24 max-w-24 opacity-80" />
    </div>
  );
}

/** Product-page gallery: every photo, with a large main image, prev/next
 * arrows and a clickable thumbnail strip. Falls back to the category art when
 * there are no (working) photos. */
export function ProductGallery({ listing, className = "" }: { listing: PublicListing; className?: string }) {
  const [index, setIndex] = useState(0);
  const [broken, setBroken] = useState<Record<string, boolean>>({});
  const photos = (listing.images ?? []).filter((p) => !broken[p.id]);

  if (photos.length === 0) {
    return (
      <ProductVisual
        listing={{ ...listing, images: [] }}
        className={`aspect-square rounded-xl border border-hairline ${className}`}
      />
    );
  }

  const current = Math.min(index, photos.length - 1);
  const go = (delta: number) => setIndex((current + delta + photos.length) % photos.length);

  return (
    <div className={className}>
      <div className="relative aspect-square overflow-hidden rounded-xl border border-hairline bg-white">
        {/* eslint-disable-next-line @next/next/no-img-element -- served by the API, not a static asset */}
        <img
          key={photos[current].id}
          src={imageSrc(photos[current])}
          alt={`${listing.title} - photo ${current + 1} of ${photos.length}`}
          onError={() => setBroken((b) => ({ ...b, [photos[current].id]: true }))}
          className="absolute inset-0 h-full w-full object-contain"
        />
        {photos.length > 1 && (
          <>
            <button type="button" aria-label="Previous photo" onClick={() => go(-1)} className="absolute left-2 top-1/2 -translate-y-1/2 rounded-full bg-white/85 p-2 shadow hover:bg-white">
              <ChevronLeft className="h-5 w-5" aria-hidden />
            </button>
            <button type="button" aria-label="Next photo" onClick={() => go(1)} className="absolute right-2 top-1/2 -translate-y-1/2 rounded-full bg-white/85 p-2 shadow hover:bg-white">
              <ChevronRight className="h-5 w-5" aria-hidden />
            </button>
            <span className="absolute bottom-2 right-2 rounded bg-ink/60 px-2 py-0.5 text-xs text-paper">
              {current + 1} / {photos.length}
            </span>
          </>
        )}
      </div>

      {photos.length > 1 && (
        <ul className="mt-3 flex flex-wrap gap-2">
          {photos.map((p, i) => (
            <li key={p.id}>
              <button
                type="button"
                aria-label={`Show photo ${i + 1}`}
                aria-current={i === current}
                onClick={() => setIndex(i)}
                className={`block h-16 w-16 overflow-hidden rounded-md border-2 ${i === current ? "border-brass" : "border-hairline hover:border-forest/40"}`}
              >
                {/* eslint-disable-next-line @next/next/no-img-element -- served by the API, not a static asset */}
                <img src={imageSrc(p, true)} alt="" loading="lazy" className="h-full w-full object-cover" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/* ---------- small building blocks ---------- */

export function Stars({ rating }: { rating: number }) {
  return (
    <span className="inline-flex text-brass" aria-label={`${rating} out of 5`}>
      {[1, 2, 3, 4, 5].map((n) => (
        <Star key={n} className="h-4 w-4" fill={n <= rating ? "currentColor" : "none"} />
      ))}
    </span>
  );
}

export function SectionHeading({
  title,
  subtitle,
  href,
  linkText = "See all",
}: {
  title: string;
  subtitle?: string;
  href?: string;
  linkText?: string;
}) {
  return (
    <div className="mb-5 flex items-end justify-between gap-4">
      <div>
        <h2 className="font-display text-2xl text-forest">{title}</h2>
        {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
      </div>
      {href && (
        <Link href={href} className="shrink-0 text-sm font-medium text-forest underline-offset-4 hover:underline">
          {linkText} &rarr;
        </Link>
      )}
    </div>
  );
}

export function ProductGridSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="animate-pulse overflow-hidden rounded-lg border border-hairline bg-white">
          <div className="aspect-[4/3] bg-hairline/50" />
          <div className="space-y-2 p-3">
            <div className="h-4 w-3/4 rounded bg-hairline/60" />
            <div className="h-3 w-1/2 rounded bg-hairline/50" />
            <div className="h-5 w-1/3 rounded bg-hairline/60" />
          </div>
        </div>
      ))}
    </div>
  );
}

/* ---------- the product card used everywhere ---------- */

export function ProductCard({
  listing,
  orgSlug,
  view = "grid",
}: {
  listing: PublicListing;
  orgSlug: string;
  view?: "grid" | "list";
}) {
  const cart = useCart(orgSlug);
  const inCart = cart.some((i) => i.listingSlug === listing.slug);
  const href = shopPath(orgSlug, `/listings/${listing.slug}`);
  const isCrop = listing.listing_kind === "crop_produce";
  const fixed = isFixedPrice(listing);
  const stock = isCrop && listing.quantity_available ? Number(listing.quantity_available) : null;
  const lowStock = stock !== null && stock > 0 && stock <= 10;
  const list = view === "list";

  const subtitle = isCrop
    ? [humanize(listing.crop_type), listing.variety].filter(Boolean).join(" · ")
    : [listing.species, listing.breed, listing.sex].filter(Boolean).join(" · ");

  return (
    <article
      className={`group flex overflow-hidden rounded-lg border border-hairline bg-white transition-shadow hover:shadow-md ${
        list ? "flex-row" : "flex-col"
      }`}
    >
      <Link href={href} className={`relative block ${list ? "w-40 shrink-0 sm:w-56" : ""}`} aria-label={listing.title}>
        <ProductVisual listing={listing} className={list ? "h-full min-h-[9rem]" : "aspect-[4/3]"} />
        <div className="absolute left-2 top-2 flex flex-col gap-1">
          {listing.featured && (
            <span className="rounded bg-brass px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-ink">
              Featured
            </span>
          )}
          {lowStock && (
            <span className="rounded bg-red-600 px-2 py-0.5 text-[11px] font-semibold text-white">Only {stock} left</span>
          )}
        </div>
      </Link>

      <div className="flex flex-1 flex-col gap-1 p-3">
        <Link href={href} className="font-medium leading-snug text-ink hover:text-forest hover:underline">
          {listing.title}
        </Link>
        {subtitle && <p className="text-xs capitalize text-muted">{subtitle}</p>}
        {listing.county && (
          <p className="flex items-center gap-1 text-xs text-muted">
            <MapPin className="h-3 w-3" aria-hidden /> {listing.county}
          </p>
        )}
        {list && listing.description && <p className="mt-1 line-clamp-2 text-sm text-muted">{listing.description}</p>}

        <div className="mt-auto pt-2">
          <p className="font-display text-xl text-forest">
            {fixed ? kes(listing.price as string) : <span className="text-base capitalize">{humanize(listing.pricing_type)}</span>}
            {fixed && isCrop && listing.unit && <span className="text-xs font-normal text-muted"> / {listing.unit}</span>}
          </p>
          {isCrop && stock !== null && !lowStock && (
            <p className="text-xs text-muted">
              {stock} {listing.unit} in stock
            </p>
          )}

          {fixed ? (
            inCart ? (
              <Link
                href={shopPath(orgSlug, "/cart")}
                className="mt-2 flex w-full items-center justify-center gap-1.5 rounded-md border border-forest px-3 py-1.5 text-sm font-medium text-forest hover:bg-forest/5"
              >
                <Check className="h-4 w-4" aria-hidden /> In cart · View
              </Link>
            ) : (
              <button
                type="button"
                onClick={() => addToCart(orgSlug, cartItemFor(listing))}
                className="mt-2 flex w-full items-center justify-center gap-1.5 rounded-md bg-brass px-3 py-1.5 text-sm font-semibold text-ink hover:bg-brass/90"
              >
                <ShoppingCart className="h-4 w-4" aria-hidden /> Add to cart
              </button>
            )
          ) : (
            <Link
              href={href}
              className="mt-2 flex w-full items-center justify-center rounded-md border border-hairline px-3 py-1.5 text-sm font-medium text-forest hover:bg-forest/5"
            >
              Request a quote
            </Link>
          )}
        </div>
      </div>
    </article>
  );
}
