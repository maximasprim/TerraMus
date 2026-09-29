"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ShopHeader } from "@/components/shop-header";
import { Card, ErrorState, EmptyState } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import type { PublicListing, PublicTestimonial, PublicBanner } from "@/lib/types";

export default function ShopBrowsePage() {
  const { orgSlug } = useParams<{ orgSlug: string }>();

  const { data, isLoading, error } = useQuery<PublicListing[]>({
    queryKey: ["public-listings", orgSlug],
    queryFn: () => apiFetch<PublicListing[]>(`/api/v1/public/${orgSlug}/listings`, { auth: false }),
  });
  const testimonialsQuery = useQuery<PublicTestimonial[]>({
    queryKey: ["public-testimonials", orgSlug],
    queryFn: () => apiFetch<PublicTestimonial[]>(`/api/v1/public/${orgSlug}/testimonials`, { auth: false }),
  });
  const bannersQuery = useQuery<PublicBanner[]>({
    queryKey: ["public-banners", orgSlug],
    queryFn: () => apiFetch<PublicBanner[]>(`/api/v1/public/${orgSlug}/banners`, { auth: false }),
  });

  return (
    <div className="min-h-screen bg-paper">
      <ShopHeader orgSlug={orgSlug} />

      {bannersQuery.data && bannersQuery.data.length > 0 && (
        <section className="mx-auto max-w-5xl px-6 pt-8">
          <div className="flex snap-x gap-4 overflow-x-auto pb-2">
            {bannersQuery.data.map((banner, i) => {
              const image = (
                // eslint-disable-next-line @next/next/no-img-element -- external, org-supplied CMS image URL, not a static/local asset
                <img
                  src={banner.image_url}
                  alt={banner.title}
                  className="h-48 w-full min-w-[280px] max-w-md snap-start rounded-lg border border-hairline object-cover"
                />
              );
              return (
                <div key={i} className="relative min-w-[280px] max-w-md flex-shrink-0">
                  {banner.link_url ? (
                    <a href={banner.link_url} target="_blank" rel="noreferrer">{image}</a>
                  ) : (
                    image
                  )}
                  <p className="mt-2 text-sm font-medium text-ink">{banner.title}</p>
                </div>
              );
            })}
          </div>
        </section>
      )}

      <main className="mx-auto max-w-5xl px-6 py-10">
        <h1 className="mb-6 font-display text-2xl text-forest">Available now</h1>

        {error && (
          <ErrorState message={error instanceof ApiError ? error.message : "Failed to load listings"} />
        )}
        {isLoading && <p className="text-sm text-muted">Loading…</p>}
        {data && data.length === 0 && (
          <EmptyState title="Nothing listed right now" body="Check back soon, or contact the farm directly." />
        )}

        {data && data.length > 0 && (
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {data.map((listing) => (
              <Link key={listing.slug} href={`/shop/${orgSlug}/listings/${listing.slug}`}>
                <Card className="flex h-full flex-col gap-2 transition-shadow hover:shadow-md">
                  <div className="flex items-start justify-between">
                    <h2 className="font-display text-lg text-forest">{listing.title}</h2>
                    {listing.featured && (
                      <span className="rounded-full border border-brass/30 bg-brass/10 px-2 py-0.5 text-xs text-brass-dark">
                        Featured
                      </span>
                    )}
                  </div>
                  <p className="text-sm capitalize text-muted">
                    {listing.listing_kind === "animal" ? (
                      <>
                        {listing.species}
                        {listing.breed ? ` · ${listing.breed}` : ""} · {listing.sex}
                      </>
                    ) : (
                      <>
                        {listing.crop_type?.replace(/_/g, " ")}
                        {listing.variety ? ` · ${listing.variety}` : ""}
                      </>
                    )}
                  </p>
                  {listing.listing_kind === "animal" && listing.current_weight && (
                    <p className="text-sm text-muted">{listing.current_weight} kg</p>
                  )}
                  {listing.listing_kind === "crop_produce" && listing.quantity_available && (
                    <p className="text-sm text-muted">{listing.quantity_available} {listing.unit} available</p>
                  )}
                  {listing.county && <p className="text-xs text-muted">{listing.county}</p>}
                  <p className="mt-auto pt-2 font-display text-xl text-forest">
                    {listing.pricing_type === "fixed" && listing.price
                      ? `KES ${Number(listing.price).toLocaleString()}${listing.listing_kind === "crop_produce" ? ` / ${listing.unit}` : ""}`
                      : listing.pricing_type.replace(/_/g, " ")}
                  </p>
                </Card>
              </Link>
            ))}
          </div>
        )}
      </main>

      {testimonialsQuery.data && testimonialsQuery.data.length > 0 && (
        <section className="border-t border-hairline bg-white/40 py-10">
          <div className="mx-auto max-w-5xl px-6">
            <h2 className="mb-6 font-display text-xl text-forest">What customers say</h2>
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
              {testimonialsQuery.data.map((t, i) => (
                <Card key={i}>
                  {t.rating && (
                    <p className="mb-1 text-brass">{"★".repeat(t.rating)}{"☆".repeat(5 - t.rating)}</p>
                  )}
                  <p className="text-sm italic text-ink">&ldquo;{t.quote}&rdquo;</p>
                  <p className="mt-2 text-xs text-muted">- {t.customer_name}</p>
                </Card>
              ))}
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
