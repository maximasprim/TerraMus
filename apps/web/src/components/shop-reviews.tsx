"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, ErrorState, Input } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";

interface Reviews {
  count: number; average_rating: number | null;
  reviews: { customer_name: string; rating: number; comment: string | null; created_at: string }[];
}
const stars = (n: number) => "★".repeat(n) + "☆".repeat(5 - n);

/** Public reviews for one listing, plus a form to leave one. New reviews wait for the farm's approval. */
export function ReviewsSection({ orgSlug, slug }: { orgSlug: string; slug: string }) {
  const qc = useQueryClient();
  const path = `/api/v1/public/${orgSlug}/listings/${slug}/feedback`;
  const [name, setName] = useState("");
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [thanks, setThanks] = useState(false);
  const { data } = useQuery<Reviews>({ queryKey: ["public-reviews", orgSlug, slug], queryFn: () => apiFetch<Reviews>(path, { auth: false }) });
  const submit = useMutation({
    mutationFn: () => apiFetch(path, { method: "POST", auth: false, body: JSON.stringify({ customer_name: name.trim(), rating, comment: comment.trim() || undefined }) }),
    onSuccess: () => { setThanks(true); setError(null); setName(""); setRating(0); setComment(""); qc.invalidateQueries({ queryKey: ["public-reviews", orgSlug, slug] }); },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Could not send your review. Please try again."),
  });
  return (
    <section className="mt-14" aria-labelledby="reviews-heading">
      <h2 id="reviews-heading" className="font-display text-2xl text-forest">Customer reviews</h2>
      {data && data.count > 0 && data.average_rating != null && (
        <p className="mt-1 text-sm text-muted"><span className="text-amber-600">{stars(Math.round(data.average_rating))}</span> {data.average_rating.toFixed(1)} from {data.count} review{data.count === 1 ? "" : "s"}</p>
      )}
      <div className="mt-4 grid gap-8 lg:grid-cols-2">
        <div className="space-y-4">
          {data && data.count === 0 && <p className="text-sm text-muted">No reviews yet. Be the first to share your experience.</p>}
          {data?.reviews.map((r, i) => (
            <div key={i} className="border-b border-hairline pb-3">
              <p className="text-amber-600" aria-label={`${r.rating} out of 5 stars`}>{stars(r.rating)}</p>
              {r.comment && <p className="mt-1 whitespace-pre-line text-sm">{r.comment}</p>}
              <p className="mt-1 text-xs text-muted">{r.customer_name} · {new Date(r.created_at).toLocaleDateString()}</p>
            </div>))}
        </div>
        <div className="space-y-3 rounded-lg border border-hairline p-4">
          <h3 className="font-display text-lg text-forest">Leave a review</h3>
          {thanks ? <p className="text-sm text-forest">Thank you! Your review will appear once the farm approves it.</p> : (
            <>
              {error && <ErrorState message={error} />}
              <Input label="Your name" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} />
              <div>
                <p className="mb-1 text-sm font-medium text-ink">Rating</p>
                <div className="flex gap-1" role="radiogroup" aria-label="Rating">
                  {[1, 2, 3, 4, 5].map((n) => (
                    <button key={n} type="button" role="radio" aria-checked={rating === n} aria-label={`${n} star${n === 1 ? "" : "s"}`} onClick={() => setRating(n)}
                      className={`text-2xl leading-none ${n <= rating ? "text-amber-500" : "text-hairline"}`}>★</button>))}
                </div>
              </div>
              <div>
                <label htmlFor="rv-comment" className="mb-1 block text-sm font-medium text-ink">Your review (optional)</label>
                <textarea id="rv-comment" rows={4} maxLength={1000} value={comment} onChange={(e) => setComment(e.target.value)}
                  className="w-full rounded-md border border-hairline bg-white px-3 py-2 text-sm focus:border-brass focus:outline-none" />
              </div>
              <Button disabled={name.trim().length < 2 || rating < 1 || submit.isPending} onClick={() => submit.mutate()}>{submit.isPending ? "Sending…" : "Submit review"}</Button>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
