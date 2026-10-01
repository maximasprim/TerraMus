"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { LayoutGrid, List, Search, SlidersHorizontal, X } from "lucide-react";
import { ShopHeader } from "@/components/shop-header";
import { ProductCard, ProductGridSkeleton } from "@/components/shop-ui";
import { EmptyState, ErrorState } from "@/components/ui";
import { ApiError } from "@/lib/api";
import { categoryKey, humanize, isFixedPrice, shopPath, usePageTitle, useShopListings, useShopProfile } from "@/lib/shop-utils";
import type { PublicListing } from "@/lib/types";

const PAGE_SIZE = 12;
const KIND_LABEL: Record<string, string> = { animal: "Livestock", crop_produce: "Fresh produce" };

export default function StorePage() {
  // useSearchParams needs a Suspense boundary.
  return (
    <Suspense fallback={<div className="min-h-screen bg-paper" />}>
      <StoreInner />
    </Suspense>
  );
}

function StoreInner() {
  const { orgSlug } = useParams<{ orgSlug: string }>();
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  const { data, isLoading, error } = useShopListings(orgSlug);
  const profile = useShopProfile(orgSlug);
  usePageTitle("Store", profile.data?.farm_name);

  const [view, setView] = useState<"grid" | "list">("grid");
  const [filtersOpen, setFiltersOpen] = useState(false);

  // All filter state lives in the URL, so links from the home page / header
  // search / footer work, and results are shareable.
  const q = sp.get("q") ?? "";
  const kind = sp.get("kind") ?? "";
  const category = sp.get("category") ?? "";
  const county = sp.get("county") ?? "";
  const min = sp.get("min") ?? "";
  const max = sp.get("max") ?? "";
  const featuredOnly = sp.get("featured") === "1";
  const sort = sp.get("sort") ?? "featured";
  const page = Math.max(1, Number(sp.get("page")) || 1);

  const setParams = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(sp.toString());
    for (const [k, v] of Object.entries(patch)) {
      if (v === null || v === "") next.delete(k);
      else next.set(k, v);
    }
    if (!("page" in patch)) next.delete("page");
    const qs = next.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  };

  const [qInput, setQInput] = useState(q);
  const [minInput, setMinInput] = useState(min);
  const [maxInput, setMaxInput] = useState(max);
  useEffect(() => setQInput(q), [q]);
  useEffect(() => setMinInput(min), [min]);
  useEffect(() => setMaxInput(max), [max]);

  const all = useMemo(() => data ?? [], [data]);

  const counties = useMemo(
    () => [...new Set(all.map((l) => l.county).filter((c): c is string => !!c))].sort(),
    [all],
  );

  const categories = useMemo(() => {
    const map = new Map<string, number>();
    for (const l of all) {
      if (kind && l.listing_kind !== kind) continue;
      const k = categoryKey(l);
      map.set(k, (map.get(k) ?? 0) + 1);
    }
    return [...map.entries()].sort((a, b) => b[1] - a[1]);
  }, [all, kind]);

  const results = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const filtered = all.filter((l: PublicListing) => {
      if (kind && l.listing_kind !== kind) return false;
      if (category && categoryKey(l) !== category) return false;
      if (county && l.county !== county) return false;
      if (featuredOnly && !l.featured) return false;
      if (needle) {
        const hay = [l.title, l.description, l.species, l.breed, l.crop_type, l.variety, l.county]
          .filter(Boolean)
          .join(" ")
          .toLowerCase()
          .replace(/_/g, " ");
        if (!hay.includes(needle)) return false;
      }
      const price = isFixedPrice(l) ? Number(l.price) : null;
      if (min && (price === null || price < Number(min))) return false;
      if (max && (price === null || price > Number(max))) return false;
      return true;
    });
    const priceOf = (l: PublicListing) => (isFixedPrice(l) ? Number(l.price) : Number.POSITIVE_INFINITY);
    return [...filtered].sort((a, b) => {
      if (sort === "price_asc") return priceOf(a) - priceOf(b);
      if (sort === "price_desc") return (priceOf(b) === Infinity ? -1 : priceOf(b)) - (priceOf(a) === Infinity ? -1 : priceOf(a));
      if (sort === "name") return a.title.localeCompare(b.title);
      return Number(b.featured) - Number(a.featured) || a.title.localeCompare(b.title);
    });
  }, [all, q, kind, category, county, featuredOnly, min, max, sort]);

  const pages = Math.max(1, Math.ceil(results.length / PAGE_SIZE));
  const current = Math.min(page, pages);
  const visible = results.slice((current - 1) * PAGE_SIZE, current * PAGE_SIZE);

  const chips: { label: string; clear: Record<string, string | null> }[] = [];
  if (q) chips.push({ label: `“${q}”`, clear: { q: null } });
  if (kind) chips.push({ label: KIND_LABEL[kind] ?? kind, clear: { kind: null, category: null } });
  if (category) chips.push({ label: humanize(category), clear: { category: null } });
  if (county) chips.push({ label: county, clear: { county: null } });
  if (featuredOnly) chips.push({ label: "Featured", clear: { featured: null } });
  if (min || max) chips.push({ label: `KES ${min || "0"} – ${max || "any"}`, clear: { min: null, max: null } });

  const filterPanel = (
    <div className="space-y-6 text-sm">
      <div>
        <h3 className="mb-2 font-semibold text-ink">Type</h3>
        <ul className="space-y-1">
          {[["", "All products"], ["animal", "Livestock"], ["crop_produce", "Fresh produce"]].map(([val, label]) => (
            <li key={val}>
              <button
                type="button"
                onClick={() => setParams({ kind: val || null, category: null })}
                className={`w-full rounded px-2 py-1 text-left ${kind === val ? "bg-forest/10 font-medium text-forest" : "text-ink/80 hover:bg-forest/5"}`}
              >
                {label}
              </button>
            </li>
          ))}
        </ul>
      </div>

      {categories.length > 0 && (
        <div>
          <h3 className="mb-2 font-semibold text-ink">Category</h3>
          <ul className="space-y-1">
            {categories.map(([key, count]) => (
              <li key={key}>
                <button
                  type="button"
                  onClick={() => setParams({ category: category === key ? null : key })}
                  className={`flex w-full justify-between rounded px-2 py-1 text-left capitalize ${category === key ? "bg-forest/10 font-medium text-forest" : "text-ink/80 hover:bg-forest/5"}`}
                >
                  <span>{humanize(key)}</span>
                  <span className="text-muted">{count}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div>
        <h3 className="mb-2 font-semibold text-ink">Price (KES)</h3>
        <form
          className="flex items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            setParams({ min: minInput.trim() || null, max: maxInput.trim() || null });
          }}
        >
          <input value={minInput} onChange={(e) => setMinInput(e.target.value)} inputMode="numeric" placeholder="Min" aria-label="Minimum price" className="w-full rounded border border-hairline bg-white px-2 py-1.5" />
          <span className="text-muted">–</span>
          <input value={maxInput} onChange={(e) => setMaxInput(e.target.value)} inputMode="numeric" placeholder="Max" aria-label="Maximum price" className="w-full rounded border border-hairline bg-white px-2 py-1.5" />
          <button type="submit" className="rounded bg-forest px-3 py-1.5 text-paper">Go</button>
        </form>
      </div>

      {counties.length > 1 && (
        <div>
          <h3 className="mb-2 font-semibold text-ink">Location</h3>
          <select value={county} onChange={(e) => setParams({ county: e.target.value || null })} aria-label="Filter by county" className="w-full rounded border border-hairline bg-white px-2 py-1.5">
            <option value="">All locations</option>
            {counties.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>
      )}

      <label className="flex cursor-pointer items-center gap-2">
        <input type="checkbox" checked={featuredOnly} onChange={(e) => setParams({ featured: e.target.checked ? "1" : null })} className="h-4 w-4 accent-forest" />
        Featured deals only
      </label>

      {chips.length > 0 && (
        <button type="button" onClick={() => router.replace(pathname, { scroll: false })} className="text-forest underline underline-offset-4">
          Clear all filters
        </button>
      )}
    </div>
  );

  return (
    <div className="min-h-screen bg-paper">
      <ShopHeader orgSlug={orgSlug} />

      <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
        <nav className="mb-4 text-xs text-muted" aria-label="Breadcrumb">
          <Link href={shopPath(orgSlug)} className="hover:underline">Home</Link> &rsaquo; <span className="text-ink">Store</span>
        </nav>

        <div className="grid gap-6 lg:grid-cols-[15rem_1fr]">
          <aside className="hidden lg:block">
            <div className="sticky top-36 rounded-lg border border-hairline bg-white p-4">{filterPanel}</div>
          </aside>

          <section>
            <div className="mb-4 flex flex-wrap items-center gap-3">
              <form
                role="search"
                className="flex min-w-[12rem] flex-1 overflow-hidden rounded-md border border-hairline bg-white"
                onSubmit={(e) => {
                  e.preventDefault();
                  setParams({ q: qInput.trim() || null });
                }}
              >
                <input value={qInput} onChange={(e) => setQInput(e.target.value)} placeholder="Search this store…" aria-label="Search this store" className="min-w-0 flex-1 px-3 py-2 text-sm outline-none" />
                <button type="submit" className="px-3 text-forest" aria-label="Search"><Search className="h-4 w-4" aria-hidden /></button>
              </form>

              <button type="button" onClick={() => setFiltersOpen((o) => !o)} className="flex items-center gap-1.5 rounded-md border border-hairline bg-white px-3 py-2 text-sm lg:hidden">
                <SlidersHorizontal className="h-4 w-4" aria-hidden /> Filters
              </button>

              <select value={sort} onChange={(e) => setParams({ sort: e.target.value === "featured" ? null : e.target.value })} aria-label="Sort products" className="rounded-md border border-hairline bg-white px-3 py-2 text-sm">
                <option value="featured">Featured first</option>
                <option value="price_asc">Price: low to high</option>
                <option value="price_desc">Price: high to low</option>
                <option value="name">Name: A to Z</option>
              </select>

              <div className="hidden overflow-hidden rounded-md border border-hairline bg-white sm:flex">
                <button type="button" aria-label="Grid view" aria-pressed={view === "grid"} onClick={() => setView("grid")} className={`p-2 ${view === "grid" ? "bg-forest text-paper" : "text-muted"}`}>
                  <LayoutGrid className="h-4 w-4" />
                </button>
                <button type="button" aria-label="List view" aria-pressed={view === "list"} onClick={() => setView("list")} className={`p-2 ${view === "list" ? "bg-forest text-paper" : "text-muted"}`}>
                  <List className="h-4 w-4" />
                </button>
              </div>
            </div>

            {filtersOpen && <div className="mb-4 rounded-lg border border-hairline bg-white p-4 lg:hidden">{filterPanel}</div>}

            {chips.length > 0 && (
              <div className="mb-4 flex flex-wrap gap-2">
                {chips.map((c) => (
                  <button key={c.label} type="button" onClick={() => setParams(c.clear)} className="flex items-center gap-1 rounded-full border border-forest/30 bg-forest/5 px-3 py-1 text-xs capitalize text-forest">
                    {c.label} <X className="h-3 w-3" aria-hidden />
                  </button>
                ))}
              </div>
            )}

            {!isLoading && !error && (
              <p className="mb-3 text-sm text-muted">
                {results.length} {results.length === 1 ? "result" : "results"}
              </p>
            )}

            {error && <ErrorState message={error instanceof ApiError ? error.message : "Failed to load the store"} />}
            {isLoading && <ProductGridSkeleton count={6} />}
            {!isLoading && !error && results.length === 0 && (
              <EmptyState
                title={all.length === 0 ? "Nothing listed right now" : "No products match your filters"}
                body={all.length === 0 ? "Check back soon, or contact the farm directly." : "Try removing a filter or searching for something else."}
              />
            )}

            {visible.length > 0 && (
              <div className={view === "list" ? "space-y-3" : "grid grid-cols-2 gap-4 xl:grid-cols-3"}>
                {visible.map((l) => (
                  <ProductCard key={l.slug} listing={l} orgSlug={orgSlug} view={view} />
                ))}
              </div>
            )}

            {pages > 1 && (
              <div className="mt-8 flex flex-wrap items-center justify-center gap-1">
                <button type="button" disabled={current === 1} onClick={() => setParams({ page: String(current - 1) })} className="rounded border border-hairline bg-white px-3 py-1.5 text-sm disabled:opacity-40">
                  Previous
                </button>
                {Array.from({ length: pages }).map((_, i) => (
                  <button key={i} type="button" onClick={() => setParams({ page: String(i + 1) })} aria-current={current === i + 1 ? "page" : undefined} className={`rounded border px-3 py-1.5 text-sm ${current === i + 1 ? "border-forest bg-forest text-paper" : "border-hairline bg-white"}`}>
                    {i + 1}
                  </button>
                ))}
                <button type="button" disabled={current === pages} onClick={() => setParams({ page: String(current + 1) })} className="rounded border border-hairline bg-white px-3 py-1.5 text-sm disabled:opacity-40">
                  Next
                </button>
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
