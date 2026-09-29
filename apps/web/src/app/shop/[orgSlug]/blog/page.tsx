"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ShopHeader } from "@/components/shop-header";
import { Card, ErrorState, EmptyState } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import type { PublicBlogPostSummary } from "@/lib/types";

export default function BlogListPage() {
  const { orgSlug } = useParams<{ orgSlug: string }>();

  const { data, isLoading, error } = useQuery<PublicBlogPostSummary[]>({
    queryKey: ["public-blog", orgSlug],
    queryFn: () => apiFetch<PublicBlogPostSummary[]>(`/api/v1/public/${orgSlug}/blog`, { auth: false }),
  });

  return (
    <div className="min-h-screen bg-paper">
      <ShopHeader orgSlug={orgSlug} />
      <main className="mx-auto max-w-3xl px-6 py-10">
        <h1 className="mb-6 font-display text-2xl text-forest">From the farm</h1>

        {error && <ErrorState message={error instanceof ApiError ? error.message : "Failed to load posts"} />}
        {isLoading && <p className="text-sm text-muted">Loading…</p>}
        {data && data.length === 0 && (
          <EmptyState title="No posts yet" body="Check back soon for updates from the farm." />
        )}

        {data && data.length > 0 && (
          <div className="space-y-4">
            {data.map((post) => (
              <Link key={post.slug} href={`/shop/${orgSlug}/blog/${post.slug}`}>
                <Card className="transition-shadow hover:shadow-md">
                  <h2 className="font-display text-lg text-forest">{post.title}</h2>
                  {post.author_name && <p className="text-xs text-muted">By {post.author_name}</p>}
                  {post.excerpt && <p className="mt-2 text-sm text-ink">{post.excerpt}</p>}
                  {post.published_at && (
                    <p className="mt-2 text-xs text-muted">{new Date(post.published_at).toLocaleDateString()}</p>
                  )}
                </Card>
              </Link>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
