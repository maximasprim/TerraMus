"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { Button, Card, EmptyState, ErrorState, TagChip } from "@/components/ui";
import { ApiError, apiFetch, apiFetchAll } from "@/lib/api";
import { whatsappLink } from "@/lib/shop-utils";
import type { Inquiry, InquirySummary } from "@/lib/types";

type Filter = "all" | Inquiry["status"];
const TABS: { key: Filter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "new", label: "New" },
  { key: "read", label: "Read" },
  { key: "replied", label: "Replied" },
  { key: "archived", label: "Archived" },
];

export default function InquiriesPage() {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<Filter>("new");

  const summary = useQuery<InquirySummary>({
    queryKey: ["inquiries", "summary"],
    queryFn: () => apiFetch<InquirySummary>("/api/v1/inquiries/summary"),
  });
  const list = useQuery<Inquiry[]>({
    queryKey: ["inquiries", filter],
    queryFn: () => apiFetchAll<Inquiry>(`/api/v1/inquiries${filter === "all" ? "" : `?status=${filter}`}`, { style: "offset", pageSize: 100 }),
  });

  const setStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: Inquiry["status"] }) =>
      apiFetch(`/api/v1/inquiries/${id}`, { method: "PATCH", body: JSON.stringify({ status }) }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["inquiries"] }),
  });

  const count = (key: Filter) =>
    key === "all" ? (summary.data ? Object.values(summary.data).reduce((a, b) => a + b, 0) : null) : summary.data?.[key] ?? null;

  return (
    <AdminShell>
      <div className="mb-6">
        <h1 className="font-display text-2xl text-forest">Inquiries</h1>
        <p className="text-sm text-muted">Messages customers send from your public site&apos;s contact page.</p>
      </div>

      <div className="mb-5 flex flex-wrap gap-2">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setFilter(t.key)}
            className={`rounded-full border px-4 py-1.5 text-sm ${filter === t.key ? "border-forest bg-forest text-paper" : "border-hairline bg-white text-ink hover:bg-forest/5"}`}
          >
            {t.label}
            {count(t.key) !== null && <span className="ml-1.5 opacity-70">({count(t.key)})</span>}
          </button>
        ))}
      </div>

      {list.error && <ErrorState message={list.error instanceof ApiError ? list.error.message : "Failed to load inquiries"} />}
      {list.isLoading && <p className="text-sm text-muted">Loading…</p>}
      {list.data && list.data.length === 0 && (
        <EmptyState title="Nothing here" body={filter === "new" ? "No new inquiries - you're all caught up." : "No inquiries in this view."} />
      )}

      <div className="space-y-3">
        {list.data?.map((q) => {
          const wa = whatsappLink(q.phone, `Hello ${q.name}, thanks for contacting us.`);
          return (
            <Card key={q.id} className="space-y-3">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className="font-medium text-ink">{q.name}</p>
                  <p className="text-xs text-muted">{new Date(q.created_at).toLocaleString()}</p>
                </div>
                <div className="flex items-center gap-2">
                  {q.listing_slug && <TagChip>{q.listing_slug}</TagChip>}
                  <span className={`rounded-full border px-2 py-0.5 text-xs capitalize ${q.status === "new" ? "border-brass/40 bg-brass/10 text-ink" : "border-hairline text-muted"}`}>
                    {q.status}
                  </span>
                </div>
              </div>

              <p className="whitespace-pre-line text-sm text-ink">{q.message}</p>

              <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
                {q.phone && <a className="text-forest hover:underline" href={`tel:${q.phone}`}>{q.phone}</a>}
                {q.email && <a className="break-all text-forest hover:underline" href={`mailto:${q.email}`}>{q.email}</a>}
                {wa && <a className="text-forest hover:underline" href={wa} target="_blank" rel="noreferrer">Reply on WhatsApp</a>}
              </div>

              <div className="flex flex-wrap gap-2 border-t border-hairline pt-3">
                {q.status !== "read" && q.status !== "replied" && (
                  <Button variant="ghost" className="text-xs" disabled={setStatus.isPending} onClick={() => setStatus.mutate({ id: q.id, status: "read" })}>
                    Mark read
                  </Button>
                )}
                {q.status !== "replied" && (
                  <Button variant="ghost" className="text-xs" disabled={setStatus.isPending} onClick={() => setStatus.mutate({ id: q.id, status: "replied" })}>
                    Mark replied
                  </Button>
                )}
                {q.status !== "archived" ? (
                  <Button variant="ghost" className="text-xs" disabled={setStatus.isPending} onClick={() => setStatus.mutate({ id: q.id, status: "archived" })}>
                    Archive
                  </Button>
                ) : (
                  <Button variant="ghost" className="text-xs" disabled={setStatus.isPending} onClick={() => setStatus.mutate({ id: q.id, status: "new" })}>
                    Restore
                  </Button>
                )}
              </div>
            </Card>
          );
        })}
      </div>
    </AdminShell>
  );
}
