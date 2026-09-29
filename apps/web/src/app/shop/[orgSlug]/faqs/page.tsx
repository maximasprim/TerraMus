"use client";

import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ShopHeader } from "@/components/shop-header";
import { Card, ErrorState, EmptyState } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import type { PublicFAQ } from "@/lib/types";

export default function FAQsPage() {
  const { orgSlug } = useParams<{ orgSlug: string }>();

  const { data, isLoading, error } = useQuery<PublicFAQ[]>({
    queryKey: ["public-faqs", orgSlug],
    queryFn: () => apiFetch<PublicFAQ[]>(`/api/v1/public/${orgSlug}/faqs`, { auth: false }),
  });

  const grouped = data?.reduce<Record<string, PublicFAQ[]>>((acc, faq) => {
    const key = faq.category ?? "General";
    (acc[key] ??= []).push(faq);
    return acc;
  }, {});

  return (
    <div className="min-h-screen bg-paper">
      <ShopHeader orgSlug={orgSlug} />
      <main className="mx-auto max-w-2xl px-6 py-10">
        <h1 className="mb-6 font-display text-2xl text-forest">Frequently asked questions</h1>

        {error && <ErrorState message={error instanceof ApiError ? error.message : "Failed to load FAQs"} />}
        {isLoading && <p className="text-sm text-muted">Loading…</p>}
        {data && data.length === 0 && (
          <EmptyState title="No FAQs yet" body="Have a question? Contact the farm directly." />
        )}

        {grouped &&
          Object.entries(grouped).map(([category, faqs]) => (
            <div key={category} className="mb-6">
              <h2 className="mb-3 text-xs font-medium uppercase tracking-wider text-muted">{category}</h2>
              <div className="space-y-3">
                {faqs.map((faq, i) => (
                  <Card key={i}>
                    <p className="font-medium text-ink">{faq.question}</p>
                    <p className="mt-1 text-sm text-muted">{faq.answer}</p>
                  </Card>
                ))}
              </div>
            </div>
          ))}
      </main>
    </div>
  );
}
