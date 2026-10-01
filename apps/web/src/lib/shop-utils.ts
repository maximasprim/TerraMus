"use client";

import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, API_BASE } from "@/lib/api";
import type { CartItem } from "@/lib/cart";
import type { PublicFarmProfile, PublicListing } from "@/lib/types";

/** Shared helpers + data hooks for the public storefront. The react-query
 * keys are deliberately identical to the ones the original pages used, so
 * every page shares one cache entry per farm. */

export const shopPath = (orgSlug: string, sub = "") => `/shop/${orgSlug}${sub}`;

/** Best URL for a photo: the direct bucket/CDN link when the photo is stored
 * in object storage, otherwise the API media endpoint (database-stored photos).
 * Both kinds can coexist, so callers should always go through this. */
export const imageSrc = (img: { id: string; url?: string | null; thumb_url?: string | null }, thumb = false) =>
  (thumb ? img.thumb_url : img.url) ?? listingImageUrl(img.id, thumb);

/** URL of a listing photo served by the API (public, cacheable). `thumb` is
 * the small version used on product cards; the full size is for the product page. */
export const listingImageUrl = (imageId: string, thumb = false) =>
  `${API_BASE}/api/v1/media/listing-images/${imageId}${thumb ? "/thumb" : ""}`;

export function useShopProfile(orgSlug: string) {
  return useQuery<PublicFarmProfile>({
    queryKey: ["public-profile", orgSlug],
    queryFn: () => apiFetch<PublicFarmProfile>(`/api/v1/public/${orgSlug}/profile`, { auth: false }),
  });
}

export function useShopListings(orgSlug: string) {
  return useQuery<PublicListing[]>({
    queryKey: ["public-listings", orgSlug],
    queryFn: () => apiFetch<PublicListing[]>(`/api/v1/public/${orgSlug}/listings`, { auth: false }),
  });
}

export function usePageTitle(title: string | undefined, farmName?: string) {
  useEffect(() => {
    if (!title) return;
    document.title = farmName ? `${title} | ${farmName}` : title;
  }, [title, farmName]);
}

export const humanize = (s: string | null | undefined) => (s ?? "").replace(/_/g, " ");

export const kes = (n: string | number) => `KES ${Number(n).toLocaleString()}`;

export const isFixedPrice = (l: PublicListing) => l.pricing_type === "fixed" && !!l.price;

export const priceText = (l: PublicListing) =>
  isFixedPrice(l) ? kes(l.price as string) : humanize(l.pricing_type);

/** The raw species / crop-type code a listing belongs to (used for filters). */
export const categoryKey = (l: PublicListing) =>
  (l.listing_kind === "animal" ? l.species : l.crop_type) ?? "other";

/** Build a wa.me link from a (Kenyan-friendly) phone number. */
export function whatsappLink(phone: string | null | undefined, text?: string): string | null {
  if (!phone) return null;
  let digits = phone.replace(/\D/g, "");
  if (digits.startsWith("0")) digits = `254${digits.slice(1)}`;
  else if (digits.length === 9 && /^[71]/.test(digits)) digits = `254${digits}`;
  if (digits.length < 10) return null;
  return `https://wa.me/${digits}${text ? `?text=${encodeURIComponent(text)}` : ""}`;
}

export function cartItemFor(l: PublicListing, quantity = "1"): CartItem {
  return {
    listingSlug: l.slug,
    title: l.title,
    price: l.price ?? "0",
    unit: l.unit,
    listingKind: l.listing_kind,
    quantity: l.listing_kind === "animal" ? "1" : quantity,
    maxQuantity: l.quantity_available,
  };
}
