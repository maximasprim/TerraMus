"use client";

import { useEffect, useState, useCallback } from "react";

/** A guest's cart for one farm's storefront. Kept in localStorage, scoped
 * per org (a shopper browsing two different farms' shops in the same
 * browser gets two independent carts) and per browser only - there's no
 * account required to buy (see PublicOrderCreate), so there's nowhere
 * server-side to keep this. Cleared once an order is successfully placed. */
export interface CartItem {
  listingSlug: string;
  title: string;
  price: string; // per-unit for crop produce, flat for an animal
  unit: string | null;
  listingKind: "animal" | "crop_produce";
  quantity: string; // always "1" for an animal item - editable for crop produce
  maxQuantity: string | null; // quantity_available snapshot at add-time, just a soft UI cap
}

function cartKey(orgSlug: string): string {
  return `terramus-cart:${orgSlug}`;
}

function readCart(orgSlug: string): CartItem[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(cartKey(orgSlug));
    return raw ? (JSON.parse(raw) as CartItem[]) : [];
  } catch {
    return [];
  }
}

function writeCart(orgSlug: string, items: CartItem[]): void {
  try {
    window.localStorage.setItem(cartKey(orgSlug), JSON.stringify(items));
    // Same-tab listeners (React state elsewhere on the page, e.g. the
    // header's cart count) don't get the browser's own "storage" event -
    // that only fires in *other* tabs - so a custom event covers same-tab
    // updates and "storage" covers cross-tab ones.
    window.dispatchEvent(new CustomEvent("terramus-cart-updated"));
  } catch {
    // localStorage unavailable (private browsing quota, etc.) - cart just
    // won't persist this session; nothing else to do about it here.
  }
}

export function addToCart(orgSlug: string, item: CartItem): void {
  const items = readCart(orgSlug);
  const existing = items.find((i) => i.listingSlug === item.listingSlug);
  if (existing) {
    // An animal is always exactly one unit - re-adding just leaves it as is.
    // Crop produce accumulates quantity.
    if (item.listingKind === "crop_produce") {
      existing.quantity = String(Number(existing.quantity) + Number(item.quantity));
    }
  } else {
    items.push(item);
  }
  writeCart(orgSlug, items);
}

export function removeFromCart(orgSlug: string, listingSlug: string): void {
  writeCart(orgSlug, readCart(orgSlug).filter((i) => i.listingSlug !== listingSlug));
}

export function updateCartQuantity(orgSlug: string, listingSlug: string, quantity: string): void {
  const items = readCart(orgSlug);
  const item = items.find((i) => i.listingSlug === listingSlug);
  if (item) item.quantity = quantity;
  writeCart(orgSlug, items);
}

export function clearCart(orgSlug: string): void {
  writeCart(orgSlug, []);
}

/** Live-updating view of one org's cart. Re-reads on mount and whenever any
 * page (this tab or another) changes it. */
export function useCart(orgSlug: string): CartItem[] {
  const [items, setItems] = useState<CartItem[]>([]);

  const refresh = useCallback(() => setItems(readCart(orgSlug)), [orgSlug]);

  useEffect(() => {
    refresh();
    window.addEventListener("terramus-cart-updated", refresh);
    window.addEventListener("storage", refresh);
    return () => {
      window.removeEventListener("terramus-cart-updated", refresh);
      window.removeEventListener("storage", refresh);
    };
  }, [refresh]);

  return items;
}
