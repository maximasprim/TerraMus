"use client";

import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ShopHeader } from "@/components/shop-header";
import { Card, ErrorState } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import type { PublicBlogPostDetail } from "@/lib/types";

export default function BlogPostPage() {
  const { orgSlug, slug } = useParams<{ orgSlug: string; slug: string }>();

  const { data, isLoading, error } = useQuery<PublicBlogPostDetail>({
    queryKey: ["public-blog-post", orgSlug, slug],
    queryFn: () => apiFetch<PublicBlogPostDetail>(`/api/v1/public/${orgSlug}/blog/${slug}`, { auth: false }),
  });

  return (
    <div className="min-h-screen bg-paper">
      <ShopHeader orgSlug={orgSlug} />
      <main className="mx-auto max-w-2xl px-6 py-10">
        {error && (
          <ErrorState message={error instanceof ApiError ? error.message : "This post is no longer available"} />
        )}
        {isLoading && <p className="text-sm text-muted">Loading…</p>}

        {data && (
          <Card>
            <h1 className="font-display text-2xl text-forest">{data.title}</h1>
            <p className="mb-4 text-xs text-muted">
              {data.author_name}
              {data.author_name && data.published_at ? " · " : ""}
              {data.published_at && new Date(data.published_at).toLocaleDateString()}
            </p>
            <div className="whitespace-pre-wrap text-sm leading-relaxed text-ink">{data.body}</div>
          </Card>
        )}
      </main>
    </div>
  );
}
