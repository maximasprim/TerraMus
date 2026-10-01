"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, MessageCircle, ShieldCheck, Smartphone, Truck } from "lucide-react";
import { ShopHeader } from "@/components/shop-header";
import { CategoryIcon, ProductCard, ProductGridSkeleton, SectionHeading, Stars } from "@/components/shop-ui";
import { ErrorState, EmptyState } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import { categoryKey, humanize, shopPath, usePageTitle, useShopListings, useShopProfile, whatsappLink } from "@/lib/shop-utils";
import type {
  PublicBanner,
  PublicBlogPostSummary,
  PublicFAQ,
  PublicFarmProfile,
  PublicListing,
  PublicTestimonial,
} from "@/lib/types";

const WRAP = "mx-auto max-w-7xl px-4 sm:px-6";

export default function ShopHomePage() {
  const { orgSlug } = useParams<{ orgSlug: string }>();
  const profile = useShopProfile(orgSlug);
  const listingsQuery = useShopListings(orgSlug);
  const listings = useMemo(() => listingsQuery.data ?? [], [listingsQuery.data]);

  const banners = useQuery<PublicBanner[]>({
    queryKey: ["public-banners", orgSlug],
    queryFn: () => apiFetch<PublicBanner[]>(`/api/v1/public/${orgSlug}/banners`, { auth: false }),
  });
  const testimonials = useQuery<PublicTestimonial[]>({
    queryKey: ["public-testimonials", orgSlug],
    queryFn: () => apiFetch<PublicTestimonial[]>(`/api/v1/public/${orgSlug}/testimonials`, { auth: false }),
  });
  const blog = useQuery<PublicBlogPostSummary[]>({
    queryKey: ["public-blog", orgSlug],
    queryFn: () => apiFetch<PublicBlogPostSummary[]>(`/api/v1/public/${orgSlug}/blog`, { auth: false }),
  });
  const faqs = useQuery<PublicFAQ[]>({
    queryKey: ["public-faqs", orgSlug],
    queryFn: () => apiFetch<PublicFAQ[]>(`/api/v1/public/${orgSlug}/faqs`, { auth: false }),
  });

  usePageTitle(profile.data ? "Home" : undefined, profile.data?.farm_name);

  const animals = listings.filter((l) => l.listing_kind === "animal");
  const crops = listings.filter((l) => l.listing_kind === "crop_produce");
  const featured = listings.filter((l) => l.featured);

  const categories = useMemo(() => {
    const map = new Map<string, { key: string; kind: PublicListing["listing_kind"]; count: number }>();
    for (const l of listings) {
      const key = categoryKey(l);
      const id = `${l.listing_kind}:${key}`;
      const entry = map.get(id) ?? { key, kind: l.listing_kind, count: 0 };
      entry.count += 1;
      map.set(id, entry);
    }
    return [...map.values()].sort((a, b) => b.count - a.count).slice(0, 8);
  }, [listings]);

  const loading = listingsQuery.isLoading;

  return (
    <div className="min-h-screen bg-paper">
      <ShopHeader orgSlug={orgSlug} />

      <Hero
        orgSlug={orgSlug}
        profile={profile.data}
        banners={banners.data ?? []}
        animalCount={animals.length}
        cropCount={crops.length}
      />

      <TrustBar phoneKnown={!!profile.data?.phone} />

      {listingsQuery.error && (
        <div className={`${WRAP} py-6`}>
          <ErrorState message={listingsQuery.error instanceof ApiError ? listingsQuery.error.message : "Failed to load the store"} />
        </div>
      )}

      {categories.length > 0 && (
        <section className={`${WRAP} py-10`}>
          <SectionHeading title="Shop by category" subtitle="Find exactly what you need" href={shopPath(orgSlug, "/store")} linkText="Browse everything" />
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-8">
            {categories.map((c) => (
              <Link
                key={`${c.kind}:${c.key}`}
                href={shopPath(orgSlug, `/store?kind=${c.kind}&category=${encodeURIComponent(c.key)}`)}
                className="group flex flex-col items-center gap-2 rounded-lg border border-hairline bg-white p-4 text-center transition-shadow hover:shadow-md"
              >
                <span
                  className={`flex h-16 w-16 items-center justify-center rounded-full ${
                    c.kind === "animal" ? "bg-amber-50 text-brass" : "bg-emerald-50 text-forest"
                  }`}
                >
                  <CategoryIcon kind={c.kind} categoryKey={c.key} className="h-8 w-8" />
                </span>
                <span className="text-sm font-medium capitalize text-ink group-hover:text-forest">{humanize(c.key)}</span>
                <span className="text-xs text-muted">
                  {c.count} {c.count === 1 ? "item" : "items"}
                </span>
              </Link>
            ))}
          </div>
        </section>
      )}

      {loading && (
        <section className={`${WRAP} py-10`}>
          <ProductGridSkeleton count={4} />
        </section>
      )}

      {!loading && listings.length === 0 && !listingsQuery.error && (
        <section className={`${WRAP} py-10`}>
          <EmptyState title="Nothing listed right now" body="Check back soon, or contact the farm directly." />
        </section>
      )}

      {featured.length > 0 && (
        <ProductRow title="Featured deals" subtitle="Hand-picked by the farm" items={featured.slice(0, 4)} orgSlug={orgSlug} href={shopPath(orgSlug, "/store?featured=1")} tinted />
      )}
      {crops.length > 0 && (
        <ProductRow title="Fresh from the field" subtitle="Harvested and sold direct" items={crops.slice(0, 4)} orgSlug={orgSlug} href={shopPath(orgSlug, "/store?kind=crop_produce")} />
      )}
      {animals.length > 0 && (
        <ProductRow title="Quality livestock" subtitle="Healthy, well-kept animals ready for a new home" items={animals.slice(0, 4)} orgSlug={orgSlug} href={shopPath(orgSlug, "/store?kind=animal")} tinted />
      )}

      <StoryBand orgSlug={orgSlug} profile={profile.data} />

      {testimonials.data && testimonials.data.length > 0 && (
        <section className={`${WRAP} py-12`}>
          <SectionHeading title="What customers say" subtitle="Real feedback from people who bought from us" />
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {testimonials.data.slice(0, 6).map((t, i) => (
              <figure key={i} className="rounded-lg border border-hairline bg-white p-5">
                {t.rating ? <Stars rating={t.rating} /> : null}
                <blockquote className="mt-2 text-sm italic text-ink">&ldquo;{t.quote}&rdquo;</blockquote>
                <figcaption className="mt-3 text-xs font-medium text-muted">&mdash; {t.customer_name}</figcaption>
              </figure>
            ))}
          </div>
        </section>
      )}

      {blog.data && blog.data.length > 0 && (
        <section className="border-y border-hairline bg-white/50 py-12">
          <div className={WRAP}>
            <SectionHeading title="From the farm" subtitle="News, tips and stories" href={shopPath(orgSlug, "/blog")} linkText="All posts" />
            <div className="grid gap-4 md:grid-cols-3">
              {blog.data.slice(0, 3).map((post) => (
                <Link
                  key={post.slug}
                  href={shopPath(orgSlug, `/blog/${post.slug}`)}
                  className="overflow-hidden rounded-lg border border-hairline bg-white transition-shadow hover:shadow-md"
                >
                  {post.cover_image_url && (
                    // eslint-disable-next-line @next/next/no-img-element -- org-supplied CMS image URL
                    <img src={post.cover_image_url} alt="" className="h-40 w-full object-cover" />
                  )}
                  <div className="p-4">
                    <h3 className="font-display text-lg text-forest">{post.title}</h3>
                    {post.excerpt && <p className="mt-1 line-clamp-3 text-sm text-muted">{post.excerpt}</p>}
                    {post.published_at && (
                      <p className="mt-2 text-xs text-muted">{new Date(post.published_at).toLocaleDateString()}</p>
                    )}
                  </div>
                </Link>
              ))}
            </div>
          </div>
        </section>
      )}

      {faqs.data && faqs.data.length > 0 && (
        <section className={`${WRAP} py-12`}>
          <SectionHeading title="Common questions" href={shopPath(orgSlug, "/faqs")} linkText="All FAQs" />
          <div className="mx-auto max-w-3xl divide-y divide-hairline rounded-lg border border-hairline bg-white">
            {faqs.data.slice(0, 5).map((f, i) => (
              <details key={i} className="group p-4">
                <summary className="cursor-pointer list-none font-medium text-ink marker:hidden">
                  <span className="flex items-center justify-between gap-4">
                    {f.question}
                    <ChevronRight className="h-4 w-4 shrink-0 text-muted transition-transform group-open:rotate-90" aria-hidden />
                  </span>
                </summary>
                <p className="mt-2 whitespace-pre-line text-sm text-muted">{f.answer}</p>
              </details>
            ))}
          </div>
        </section>
      )}

      <CallToAction orgSlug={orgSlug} profile={profile.data} />
    </div>
  );
}

/* ------------------------------ sections ------------------------------ */

function Hero({
  orgSlug,
  profile,
  banners,
  animalCount,
  cropCount,
}: {
  orgSlug: string;
  profile: PublicFarmProfile | undefined;
  banners: PublicBanner[];
  animalCount: number;
  cropCount: number;
}) {
  const [index, setIndex] = useState(0);
  const count = banners.length;

  useEffect(() => {
    if (count < 2) return;
    const t = setInterval(() => setIndex((i) => (i + 1) % count), 6000);
    return () => clearInterval(t);
  }, [count]);

  const active = count > 0 ? banners[index % count] : null;
  const farm = profile?.farm_name ?? "our farm";

  return (
    <section className={`${WRAP} grid gap-4 py-5 lg:grid-cols-[1fr_20rem]`}>
      <div className="relative min-h-[18rem] overflow-hidden rounded-xl bg-forest text-paper sm:min-h-[24rem]">
        {active && (
          // eslint-disable-next-line @next/next/no-img-element -- org-supplied CMS image URL
          <img src={active.image_url} alt="" className="absolute inset-0 h-full w-full object-cover" />
        )}
        <div className={`absolute inset-0 ${active ? "bg-gradient-to-r from-ink/80 via-ink/40 to-transparent" : "bg-gradient-to-br from-forest via-forest to-ink"}`} />

        <div className="relative flex h-full min-h-[18rem] flex-col justify-center gap-4 p-6 sm:min-h-[24rem] sm:p-12">
          <p className="text-xs font-semibold uppercase tracking-widest text-brass">
            {profile?.county ? `Farm-fresh from ${profile.county}` : "Farm-fresh, direct to you"}
          </p>
          <h1 className="max-w-xl font-display text-3xl leading-tight sm:text-5xl">
            {active ? active.title : profile?.tagline ?? `Fresh from ${farm}`}
          </h1>
          <p className="max-w-lg text-sm text-paper/85 sm:text-base">
            Buy livestock and fresh produce straight from {farm}. No middlemen, honest prices, and pickup or delivery
            that suits you.
          </p>
          <div className="mt-2 flex flex-wrap gap-3">
            <Link href={shopPath(orgSlug, "/store")} className="rounded-md bg-brass px-6 py-3 text-sm font-semibold text-ink hover:bg-brass/90">
              Shop now
            </Link>
            {active?.link_url ? (
              <a href={active.link_url} target="_blank" rel="noreferrer" className="rounded-md border border-paper/60 px-6 py-3 text-sm font-medium hover:bg-paper/10">
                Learn more
              </a>
            ) : (
              <Link href={shopPath(orgSlug, "/about")} className="rounded-md border border-paper/60 px-6 py-3 text-sm font-medium hover:bg-paper/10">
                Our story
              </Link>
            )}
          </div>
        </div>

        {count > 1 && (
          <>
            <button
              type="button"
              aria-label="Previous slide"
              onClick={() => setIndex((i) => (i - 1 + count) % count)}
              className="absolute left-3 top-1/2 -translate-y-1/2 rounded-full bg-ink/40 p-2 hover:bg-ink/60"
            >
              <ChevronLeft className="h-5 w-5" aria-hidden />
            </button>
            <button
              type="button"
              aria-label="Next slide"
              onClick={() => setIndex((i) => (i + 1) % count)}
              className="absolute right-3 top-1/2 -translate-y-1/2 rounded-full bg-ink/40 p-2 hover:bg-ink/60"
            >
              <ChevronRight className="h-5 w-5" aria-hidden />
            </button>
            <div className="absolute bottom-3 left-1/2 flex -translate-x-1/2 gap-1.5">
              {banners.map((_, i) => (
                <button
                  key={i}
                  type="button"
                  aria-label={`Go to slide ${i + 1}`}
                  onClick={() => setIndex(i)}
                  className={`h-2 rounded-full transition-all ${i === index % count ? "w-6 bg-brass" : "w-2 bg-paper/60"}`}
                />
              ))}
            </div>
          </>
        )}
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-1">
        <PromoTile
          href={shopPath(orgSlug, "/store?kind=crop_produce")}
          title="Fresh produce"
          text={cropCount > 0 ? `${cropCount} ${cropCount === 1 ? "product" : "products"} in stock` : "Seasonal harvests"}
          tone="bg-emerald-50 text-forest"
          kind="crop_produce"
          icon="crop"
        />
        <PromoTile
          href={shopPath(orgSlug, "/store?kind=animal")}
          title="Livestock"
          text={animalCount > 0 ? `${animalCount} ${animalCount === 1 ? "animal" : "animals"} for sale` : "Healthy, well-kept stock"}
          tone="bg-amber-50 text-brass"
          kind="animal"
          icon="animal"
        />
      </div>
    </section>
  );
}

function PromoTile({
  href,
  title,
  text,
  tone,
  kind,
  icon,
}: {
  href: string;
  title: string;
  text: string;
  tone: string;
  kind: PublicListing["listing_kind"];
  icon: "crop" | "animal";
}) {
  return (
    <Link
      href={href}
      className={`flex flex-col justify-between rounded-xl border border-hairline p-5 transition-shadow hover:shadow-md ${tone}`}
    >
      <CategoryIcon kind={kind} categoryKey={icon === "crop" ? "vegetable" : "cattle"} className="h-12 w-12" />
      <div className="mt-6">
        <p className="font-display text-xl text-ink">{title}</p>
        <p className="text-sm text-muted">{text}</p>
        <p className="mt-2 text-sm font-semibold text-forest">Shop now &rarr;</p>
      </div>
    </Link>
  );
}

function TrustBar({ phoneKnown }: { phoneKnown: boolean }) {
  const items = [
    { Icon: ShieldCheck, title: "Direct from the farm", text: "No middlemen - you buy from the grower" },
    { Icon: Truck, title: "Pickup or delivery", text: "Choose what suits you at checkout" },
    { Icon: Smartphone, title: "Simple online payment", text: "Order first, pay securely after" },
    { Icon: MessageCircle, title: "Talk to the farmer", text: phoneKnown ? "Call or WhatsApp any time" : "Message us with any question" },
  ];
  return (
    <section className="border-y border-hairline bg-white">
      <div className={`${WRAP} grid grid-cols-2 gap-4 py-5 lg:grid-cols-4`}>
        {items.map(({ Icon, title, text }) => (
          <div key={title} className="flex items-start gap-3">
            <Icon className="mt-0.5 h-6 w-6 shrink-0 text-forest" aria-hidden />
            <div>
              <p className="text-sm font-semibold text-ink">{title}</p>
              <p className="text-xs text-muted">{text}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function ProductRow({
  title,
  subtitle,
  items,
  orgSlug,
  href,
  tinted,
}: {
  title: string;
  subtitle: string;
  items: PublicListing[];
  orgSlug: string;
  href: string;
  tinted?: boolean;
}) {
  return (
    <section className={tinted ? "border-y border-hairline bg-white/50 py-10" : "py-10"}>
      <div className={WRAP}>
        <SectionHeading title={title} subtitle={subtitle} href={href} />
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {items.map((l) => (
            <ProductCard key={l.slug} listing={l} orgSlug={orgSlug} />
          ))}
        </div>
      </div>
    </section>
  );
}

function StoryBand({ orgSlug, profile }: { orgSlug: string; profile: PublicFarmProfile | undefined }) {
  const values = [
    "Animals raised with care and proper health records",
    "Produce harvested fresh and sold at fair prices",
    "Transparent listings - what you see is what you get",
  ];
  return (
    <section className={`${WRAP} py-12`}>
      <div className="grid overflow-hidden rounded-xl bg-forest text-paper md:grid-cols-2">
        <div className="flex flex-col justify-center gap-4 p-8 sm:p-12">
          <p className="text-xs font-semibold uppercase tracking-widest text-brass">
            {profile?.established_year ? `Farming since ${profile.established_year}` : "Our story"}
          </p>
          <h2 className="font-display text-3xl">Why buy from {profile?.farm_name ?? "us"}?</h2>
          <p className="line-clamp-4 whitespace-pre-line text-sm text-paper/85">
            {profile?.farm_story ?? "We are a family-run farm committed to quality, honesty and fair prices. Every animal and every harvest is looked after from start to finish."}
          </p>
          <div>
            <Link href={shopPath(orgSlug, "/about")} className="inline-block rounded-md border border-paper/60 px-5 py-2.5 text-sm font-medium hover:bg-paper/10">
              Read our story
            </Link>
          </div>
        </div>
        <ul className="flex flex-col justify-center gap-4 bg-ink/30 p-8 sm:p-12">
          {values.map((v) => (
            <li key={v} className="flex items-start gap-3 text-sm">
              <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-brass" aria-hidden />
              {v}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function CallToAction({ orgSlug, profile }: { orgSlug: string; profile: PublicFarmProfile | undefined }) {
  const wa = whatsappLink(profile?.phone, `Hello ${profile?.farm_name ?? ""}, I'd like to enquire about your products.`);
  return (
    <section className={`${WRAP} pb-4 pt-2`}>
      <div className="flex flex-col items-start justify-between gap-4 rounded-xl border border-brass/40 bg-brass/10 p-8 md:flex-row md:items-center">
        <div>
          <h2 className="font-display text-2xl text-forest">Can&apos;t find what you&apos;re looking for?</h2>
          <p className="mt-1 text-sm text-muted">Tell us what you need - bulk orders and special requests are welcome.</p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Link href={shopPath(orgSlug, "/contact")} className="rounded-md bg-forest px-5 py-2.5 text-sm font-semibold text-paper hover:bg-forest/90">
            Contact the farm
          </Link>
          {wa && (
            <a href={wa} target="_blank" rel="noreferrer" className="rounded-md border border-forest px-5 py-2.5 text-sm font-semibold text-forest hover:bg-forest/5">
              WhatsApp us
            </a>
          )}
        </div>
      </div>
    </section>
  );
}
