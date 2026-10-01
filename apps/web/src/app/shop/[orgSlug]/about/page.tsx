"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Clock, HandCoins, Handshake, MapPin, Package, Sprout } from "lucide-react";
import { ShopHeader } from "@/components/shop-header";
import { shopPath, usePageTitle, useShopListings, useShopProfile } from "@/lib/shop-utils";

export default function AboutPage() {
  const { orgSlug } = useParams<{ orgSlug: string }>();
  const { data: profile } = useShopProfile(orgSlug);
  const { data: listings } = useShopListings(orgSlug);
  usePageTitle(profile ? "About us" : undefined, profile?.farm_name);

  const farm = profile?.farm_name ?? "our farm";
  const yearsFarming = profile?.established_year ? Math.max(1, new Date().getFullYear() - profile.established_year) : null;

  const stats = [
    yearsFarming ? { Icon: Clock, value: `${yearsFarming}+`, label: "Years farming" } : null,
    listings ? { Icon: Package, value: String(listings.length), label: "Products available" } : null,
    profile?.county ? { Icon: MapPin, value: profile.county, label: "Based in" } : null,
    profile?.established_year ? { Icon: Sprout, value: String(profile.established_year), label: "Established" } : null,
  ].filter((s): s is { Icon: typeof Clock; value: string; label: string } => s !== null);

  const values = [
    { Icon: Sprout, title: "Quality first", text: "Every animal and every harvest is looked after from start to finish, with proper records behind it." },
    { Icon: HandCoins, title: "Fair, upfront prices", text: "Prices are listed openly. No middlemen, no hidden charges." },
    { Icon: Handshake, title: "Honest dealing", text: "What you see is what you get. Questions are always welcome before you buy." },
  ];

  return (
    <div className="min-h-screen bg-paper">
      <ShopHeader orgSlug={orgSlug} />

      <section className="bg-gradient-to-br from-forest to-ink text-paper">
        <div className="mx-auto max-w-4xl px-4 py-16 text-center sm:px-6">
          <p className="text-xs font-semibold uppercase tracking-widest text-brass">About us</p>
          <h1 className="mt-2 font-display text-4xl sm:text-5xl">{farm}</h1>
          {profile?.tagline && <p className="mt-3 text-paper/80">{profile.tagline}</p>}
        </div>
      </section>

      <main className="mx-auto max-w-5xl space-y-14 px-4 py-12 sm:px-6">
        {stats.length > 0 && (
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            {stats.map(({ Icon, value, label }) => (
              <div key={label} className="rounded-lg border border-hairline bg-white p-5 text-center">
                <Icon className="mx-auto h-6 w-6 text-brass" aria-hidden />
                <p className="mt-2 font-display text-2xl text-forest">{value}</p>
                <p className="text-xs text-muted">{label}</p>
              </div>
            ))}
          </div>
        )}

        <section className="grid gap-8 md:grid-cols-[2fr_1fr]">
          <div>
            <h2 className="font-display text-2xl text-forest">Our story</h2>
            <p className="mt-3 whitespace-pre-line text-ink/90">
              {profile?.farm_story ??
                `${farm} is a working farm selling livestock and fresh produce directly to customers. We believe in quality, honesty and fair prices - and we'd love to show you around.`}
            </p>
          </div>
          <aside className="h-fit rounded-lg border border-hairline bg-white p-5 text-sm">
            <h3 className="mb-3 font-semibold text-ink">Visit or reach us</h3>
            <ul className="space-y-2 text-muted">
              {(profile?.address || profile?.county) && <li>{[profile?.address, profile?.county].filter(Boolean).join(", ")}</li>}
              {profile?.phone && <li><a className="text-forest hover:underline" href={`tel:${profile.phone}`}>{profile.phone}</a></li>}
              {profile?.email && <li><a className="break-all text-forest hover:underline" href={`mailto:${profile.email}`}>{profile.email}</a></li>}
              {profile?.website && <li><a className="break-all text-forest hover:underline" href={profile.website} target="_blank" rel="noreferrer">{profile.website}</a></li>}
            </ul>
            <Link href={shopPath(orgSlug, "/contact")} className="mt-4 block rounded-md border border-forest px-4 py-2 text-center font-medium text-forest hover:bg-forest/5">
              Contact us
            </Link>
          </aside>
        </section>

        <section>
          <h2 className="mb-5 text-center font-display text-2xl text-forest">What we stand for</h2>
          <div className="grid gap-4 md:grid-cols-3">
            {values.map(({ Icon, title, text }) => (
              <div key={title} className="rounded-lg border border-hairline bg-white p-6">
                <Icon className="h-7 w-7 text-forest" aria-hidden />
                <h3 className="mt-3 font-semibold text-ink">{title}</h3>
                <p className="mt-1 text-sm text-muted">{text}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-xl bg-forest p-8 text-center text-paper">
          <h2 className="font-display text-2xl">Ready to buy direct from {farm}?</h2>
          <Link href={shopPath(orgSlug, "/store")} className="mt-4 inline-block rounded-md bg-brass px-6 py-3 text-sm font-semibold text-ink hover:bg-brass/90">
            Browse the store
          </Link>
        </section>
      </main>
    </div>
  );
}
