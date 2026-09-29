"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import { useCart } from "@/lib/cart";
import type { PublicFarmProfile } from "@/lib/types";

export function ShopHeader({ orgSlug }: { orgSlug: string }) {
  const { data } = useQuery<PublicFarmProfile>({
    queryKey: ["public-profile", orgSlug],
    queryFn: () => apiFetch<PublicFarmProfile>(`/api/v1/public/${orgSlug}/profile`, { auth: false }),
  });
  const cart = useCart(orgSlug);
  const cartCount = cart.length;

  return (
    <header className="border-b border-hairline bg-forest text-paper">
      <div className="mx-auto max-w-5xl px-6 py-8">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <Link href={`/shop/${orgSlug}`}>
              <p className="font-display text-3xl italic">{data?.farm_name ?? "Farm"}</p>
            </Link>
            {data?.tagline && <p className="mt-1 text-paper/70">{data.tagline}</p>}
            {(data?.county || data?.phone) && (
              <p className="mt-2 text-xs text-paper/50">
                {data?.county}
                {data?.county && data?.phone ? " · " : ""}
                {data?.phone}
              </p>
            )}
          </div>
          <nav className="flex gap-4 text-sm text-paper/80">
            <Link href={`/shop/${orgSlug}`} className="hover:text-paper">
              Livestock
            </Link>
            <Link href={`/shop/${orgSlug}/blog`} className="hover:text-paper">
              Blog
            </Link>
            <Link href={`/shop/${orgSlug}/faqs`} className="hover:text-paper">
              FAQs
            </Link>
            <Link href={`/shop/${orgSlug}/account`} className="hover:text-paper">
              My account
            </Link>
             <Link href={`/shop/${orgSlug}/cart`} className="hover:text-paper">
              Cart{cartCount > 0 ? ` (${cartCount})` : ""}
            </Link>
          </nav>
        </div>
      </div>
    </header>
  );
}
