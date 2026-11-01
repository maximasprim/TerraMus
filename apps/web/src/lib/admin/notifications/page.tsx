"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { Card, Button, ErrorState, EmptyState } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import type { AppNotification } from "@/lib/types";

const CATEGORIES = ["health", "inventory", "payments", "orders", "breeding"] as const;

export default function NotificationsPage() {
  const queryClient = useQueryClient();
  const [unreadOnly, setUnreadOnly] = useState(false);

  const { data, isLoading, error } = useQuery<AppNotification[]>({
    queryKey: ["notifications", unreadOnly],
    queryFn: () => apiFetch<AppNotification[]>(`/api/v1/notifications${unreadOnly ? "?unread_only=true" : ""}`),
  });

  const markRead = useMutation({
    mutationFn: (id: string) => apiFetch(`/api/v1/notifications/${id}/read`, { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });

  const markAllRead = useMutation({
    mutationFn: () => apiFetch("/api/v1/notifications/read-all", { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });

  const setPreference = useMutation({
    mutationFn: ({ category, enabled }: { category: string; enabled: boolean }) =>
      apiFetch("/api/v1/notifications/preferences", { method: "PUT", body: JSON.stringify({ category, enabled }) }),
  });

  return (
    <AdminShell>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl text-forest">Notifications</h1>
          <p className="text-sm text-muted">Vaccinations due, low stock, payments, orders, breeding milestones.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" onClick={() => setUnreadOnly((v) => !v)}>
            {unreadOnly ? "Show all" : "Unread only"}
          </Button>
          <Button variant="ghost" disabled={markAllRead.isPending} onClick={() => markAllRead.mutate()}>
            Mark all read
          </Button>
        </div>
      </div>

      <div className="mb-6">
        <p className="mb-2 text-sm font-medium text-ink">Categories</p>
        <div className="flex flex-wrap gap-2">
          {CATEGORIES.map((cat) => (
            <div key={cat} className="flex items-center gap-1.5 rounded-full border border-hairline bg-white px-3 py-1 text-xs text-ink">
              <span className="capitalize">{cat}</span>
              <button
                className="text-forest hover:underline"
                onClick={() => setPreference.mutate({ category: cat, enabled: true })}
              >
                on
              </button>
              /
              <button
                className="text-muted hover:underline"
                onClick={() => setPreference.mutate({ category: cat, enabled: false })}
              >
                off
              </button>
            </div>
          ))}
        </div>
      </div>

      {error && <ErrorState message={error instanceof ApiError ? error.message : "Failed to load notifications"} />}
      {isLoading && <p className="text-sm text-muted">Loading…</p>}
      {data && data.length === 0 && <EmptyState title="Nothing here" body="You're all caught up." />}

      {data && data.length > 0 && (
        <div className="space-y-2">
          {data.map((n) => (
            <Card key={n.id} className={n.is_read ? "opacity-60" : undefined}>
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-sm font-medium text-ink">{n.title}</p>
                  <p className="text-sm text-muted">{n.body}</p>
                  <p className="mt-1 text-xs text-muted">{new Date(n.created_at).toLocaleString()}</p>
                </div>
                {!n.is_read && (
                  <Button variant="ghost" className="shrink-0 text-xs" onClick={() => markRead.mutate(n.id)}>
                    Mark read
                  </Button>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}
    </AdminShell>
  );
}
