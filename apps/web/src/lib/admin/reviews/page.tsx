"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { Button, Card, EmptyState, ErrorState, StatCard } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import type { Listing } from "@/lib/types";

interface Review { id: string; listing_id: string | null; customer_name: string; rating: number; comment: string | null; status: string; created_at: string }
interface Summary { pending_moderation: number; listings: { listing_id: string | null; reviews: number; average_rating: number }[] }
type Status = "pending" | "approved" | "rejected";
const stars = (n: number) => "★".repeat(n) + "☆".repeat(5 - n);

export default function ReviewsPage() {
  const qc = useQueryClient();
  const [status, setStatus] = useState<Status>("pending");
  const [error, setError] = useState<string | null>(null);
  const reviews = useQuery<Review[]>({ queryKey: ["reviews", status], queryFn: () => apiFetch<Review[]>(`/api/v1/feedback?status=${status}`) });
  const summary = useQuery<Summary>({ queryKey: ["reviews", "summary"], queryFn: () => apiFetch<Summary>("/api/v1/feedback/summary") });
  const listings = useQuery<Listing[]>({ queryKey: ["listings"], queryFn: () => apiFetch<Listing[]>("/api/v1/listings") });
  const title = (id: string | null) => (listings.data ?? []).find((l) => l.id === id)?.title ?? "A listing";
  const decide = useMutation({
    mutationFn: (v: { id: string; status: "approved" | "rejected" }) => apiFetch(`/api/v1/feedback/${v.id}`, { method: "PATCH", body: JSON.stringify({ status: v.status }) }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["reviews"] }); setError(null); },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Could not update the review"),
  });
  const avg = summary.data && summary.data.listings.length
    ? summary.data.listings.reduce((s, l) => s + l.average_rating * l.reviews, 0) / summary.data.listings.reduce((s, l) => s + l.reviews, 0) : null;
  return (
    <AdminShell>
      <div className="mb-6">
        <h1 className="font-display text-2xl text-forest">Customer reviews</h1>
        <p className="text-sm text-muted">Reviews left on your shop appear publicly only after you approve them.</p>
      </div>
      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-3">
        <StatCard label="Waiting for approval" value={String(summary.data?.pending_moderation ?? 0)} />
        <StatCard label="Average rating" value={avg == null ? "-" : avg.toFixed(1)} hint="approved reviews" />
        <StatCard label="Approved reviews" value={String(summary.data?.listings.reduce((s, l) => s + l.reviews, 0) ?? 0)} />
      </div>
      <div className="mb-4 flex gap-2 border-b border-hairline">
        {(["pending", "approved", "rejected"] as Status[]).map((s) => (
          <button key={s} onClick={() => setStatus(s)} className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium capitalize ${status === s ? "border-forest text-forest" : "border-transparent text-muted hover:text-ink"}`}>{s}</button>))}
      </div>
      {error && <ErrorState message={error} />}
      {reviews.error && <ErrorState message="Failed to load reviews" />}
      {reviews.data && reviews.data.length === 0 && <EmptyState title={`No ${status} reviews`} body={status === "pending" ? "New reviews from your shop will wait here for your decision." : "Nothing here yet."} />}
      <div className="space-y-3">
        {reviews.data?.map((r) => (
          <Card key={r.id} className="space-y-2">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-amber-600" aria-label={`${r.rating} out of 5`}>{stars(r.rating)}</p>
                <p className="text-sm font-medium">{r.customer_name} <span className="font-normal text-muted">on {title(r.listing_id)} · {new Date(r.created_at).toLocaleDateString()}</span></p>
              </div>
              <div className="flex gap-2">
                {r.status !== "approved" && <Button disabled={decide.isPending} onClick={() => decide.mutate({ id: r.id, status: "approved" })}>Approve</Button>}
                {r.status !== "rejected" && <Button variant="ghost" disabled={decide.isPending} onClick={() => decide.mutate({ id: r.id, status: "rejected" })}>Reject</Button>}
              </div>
            </div>
            {r.comment && <p className="whitespace-pre-line text-sm">{r.comment}</p>}
          </Card>))}
      </div>
    </AdminShell>
  );
}
