"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Phone, Search, ShoppingCart, Truck, User } from "lucide-react";
import { useCart } from "@/lib/cart";
import { shopPath, useShopProfile } from "@/lib/shop-utils";

/** Storefront header: announcement bar, brand + search + account/cart row,
 * and a category/navigation strip. Same `orgSlug` prop as before, so every
 * page that already renders <ShopHeader orgSlug=... /> gets the new look. */
export function ShopHeader({ orgSlug }: { orgSlug: string }) {
  const { data } = useShopProfile(orgSlug);
  const router = useRouter();
  const cart = useCart(orgSlug);
  const cartCount = cart.length;
  const [q, setQ] = useState("");

  const nav: { label: string; href: string }[] = [
    { label: "All products", href: shopPath(orgSlug, "/store") },
    { label: "Livestock", href: shopPath(orgSlug, "/store?kind=animal") },
    { label: "Fresh produce", href: shopPath(orgSlug, "/store?kind=crop_produce") },
    { label: "Featured deals", href: shopPath(orgSlug, "/store?featured=1") },
    { label: "About us", href: shopPath(orgSlug, "/about") },
    { label: "Blog", href: shopPath(orgSlug, "/blog") },
    { label: "FAQs", href: shopPath(orgSlug, "/faqs") },
    { label: "Contact", href: shopPath(orgSlug, "/contact") },
  ];

  return (
    <header className="sticky top-0 z-40 shadow-sm">
      <div className="bg-ink text-xs text-paper/80">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-0.5 sm:px-6">
          <p className="flex items-center gap-1.5">
            <Truck className="h-3.5 w-3.5" aria-hidden /> Farm pickup or delivery &middot; buy direct from the grower
          </p>
          {data?.phone && (
            <a href={`tel:${data.phone}`} className="hidden items-center gap-1.5 hover:text-paper sm:flex">
              <Phone className="h-3.5 w-3.5" aria-hidden /> {data.phone}
            </a>
          )}
        </div>
      </div>

      <div className="bg-forest text-paper">
        <div className="mx-auto flex max-w-8xl flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3 ">
          <Link href={shopPath(orgSlug)} className="flex min-w-0 items-center gap-3">
            {data?.logo_url ? (
              // eslint-disable-next-line @next/next/no-img-element -- org-supplied CMS image URL
              <img src={data.logo_url} alt="" className="h-10 w-10 rounded-full border border-paper/20 bg-white object-cover" />
            ) : (
              <span className="flex h-10 w-10 items-center justify-center rounded-full bg-brass font-display text-lg text-ink">
                {(data?.farm_name ?? "F").charAt(0).toUpperCase()}
              </span>
            )}
            <span className="min-w-0">
              <span className="block truncate font-display text-xl italic leading-tight">{data?.farm_name ?? "Farm"}</span>
              {data?.tagline && <span className="hidden truncate text-xs text-paper/70 md:block">{data.tagline}</span>}
            </span>
          </Link>

          <form
            role="search"
            className="order-last flex w-full flex-1 overflow-hidden rounded-full bg-white md:order-none md:w-auto"
            onSubmit={(e) => {
              e.preventDefault();
              const term = q.trim();
              router.push(shopPath(orgSlug, term ? `/store?q=${encodeURIComponent(term)}` : "/store"));
            }}
          >
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search animals, produce, breeds…"
              aria-label="Search the store"
              className="min-w-0 flex-1 px-4 py-2.5 text-sm text-ink outline-none placeholder:text-muted"
            />
            <button type="submit" className="flex items-center bg-brass px-4 text-ink hover:bg-brass/90" aria-label="Search">
              <Search className="h-5 w-5" aria-hidden />
            </button>
          </form>

          <div className="ml-auto flex items-center gap-5 text-sm md:ml-0">
            <Link href={shopPath(orgSlug, "/account")} className="flex items-center gap-1.5 text-paper/90 hover:text-paper">
              <User className="h-5 w-5" aria-hidden />
              <span className="hidden sm:inline">My account</span>
            </Link>
            <Link href={shopPath(orgSlug, "/cart")} className="relative flex items-center gap-1.5 text-paper/90 hover:text-paper">
              <ShoppingCart className="h-6 w-6" aria-hidden />
              <span className="hidden sm:inline">Cart</span>
              {cartCount > 0 && (
                <span className="absolute -right-2 -top-2 flex h-5 min-w-5 items-center justify-center rounded-full bg-brass px-1 text-[11px] font-bold text-ink">
                  {cartCount}
                </span>
              )}
            </Link>
          </div>
        </div>
      </div>

      <nav className="border-b border-hairline bg-white" aria-label="Store sections">
        <ul className="mx-auto flex max-w-7xl gap-1 overflow-x-auto px-4 text-sm sm:px-6">
          {nav.map((item) => (
            <li key={item.label} className="shrink-0">
              <Link href={item.href} className="block px-3 py-2.5 text-ink/80 hover:text-forest hover:underline hover:underline-offset-8">
                {item.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
    </header>
  );
}
