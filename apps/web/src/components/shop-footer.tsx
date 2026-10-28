"use client";

import Link from "next/link";
import { Mail, MapPin, MessageCircle, Phone } from "lucide-react";
import { shopPath, useShopProfile, whatsappLink } from "@/lib/shop-utils";

export function ShopFooter({ orgSlug }: { orgSlug: string }) {
  const { data } = useShopProfile(orgSlug);
  const wa = whatsappLink(data?.phone, `Hello ${data?.farm_name ?? ""}, I have a question about your products.`);

  const col = "space-y-2 text-sm text-paper/75";
  const link = "hover:text-paper hover:underline";

  return (
    <footer className="mt-12 bg-forest text-paper">
      <div className="mx-auto grid max-w-8xl gap-10 px-4 py-8 mb-4 sm:px-6 md:grid-cols-2 lg:grid-cols-4">
        <div>
          <p className="font-display text-2xl italic">{data?.farm_name ?? "Farm"}</p>
          {data?.tagline && <p className="mt-2 text-sm text-paper/75">{data.tagline}</p>}
          {data?.established_year && <p className="mt-3 text-xs text-paper/60">Farming since {data.established_year}</p>}
        </div>

        <div>
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-brass">Shop</h3>
          <ul className={col}>
            <li><Link className={link} href={shopPath(orgSlug, "/store")}>All products</Link></li>
            <li><Link className={link} href={shopPath(orgSlug, "/store?kind=animal")}>Livestock</Link></li>
            <li><Link className={link} href={shopPath(orgSlug, "/store?kind=crop_produce")}>Fresh produce</Link></li>
            <li><Link className={link} href={shopPath(orgSlug, "/store?featured=1")}>Featured deals</Link></li>
            <li><Link className={link} href={shopPath(orgSlug, "/cart")}>Your cart</Link></li>
          </ul>
        </div>

        <div>
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-brass">Help &amp; info</h3>
          <ul className={col}>
            <li><Link className={link} href={shopPath(orgSlug, "/about")}>About us</Link></li>
            <li><Link className={link} href={shopPath(orgSlug, "/contact")}>Contact us</Link></li>
            <li><Link className={link} href={shopPath(orgSlug, "/faqs")}>FAQs</Link></li>
            <li><Link className={link} href={shopPath(orgSlug, "/blog")}>From the farm (blog)</Link></li>
            <li><Link className={link} href={shopPath(orgSlug, "/account")}>My account &amp; orders</Link></li>
          </ul>
        </div>

        <div>
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-brass">Get in touch</h3>
          <ul className={col}>
            {data?.address || data?.county ? (
              <li className="flex gap-2">
                <MapPin className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
                <span>{[data?.address, data?.county].filter(Boolean).join(", ")}</span>
              </li>
            ) : null}
            {data?.phone && (
              <li className="flex gap-2">
                <Phone className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
                <a className={link} href={`tel:${data.phone}`}>{data.phone}</a>
              </li>
            )}
            {data?.email && (
              <li className="flex gap-2">
                <Mail className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
                <a className={`${link} break-all`} href={`mailto:${data.email}`}>{data.email}</a>
              </li>
            )}
            {wa && (
              <li>
                <a
                  href={wa}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-2 inline-flex items-center gap-2 rounded-md bg-brass px-3 py-1.5 font-semibold text-ink hover:bg-brass/90"
                >
                  <MessageCircle className="h-4 w-4" aria-hidden /> Chat on WhatsApp
                </a>
              </li>
            )}
          </ul>
        </div>
      </div>

      <div className="border-t border-paper/15">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-2 px-4 py-4 text-xs text-paper/60 sm:px-6">
          <p>&copy; {new Date().getFullYear()} {data?.farm_name ?? "Farm"}. All rights reserved.</p>
          <p>Store powered by TerraMus</p>
        </div>
      </div>
    </footer>
  );
}
