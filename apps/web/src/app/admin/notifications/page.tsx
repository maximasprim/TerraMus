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

  // Which categories are switched on. A category with no saved choice is ON (the backend default), so until this
  // loads - or if it fails - everything is shown as on rather than guessing "off".
  const prefsQuery = useQuery<{ category: string; enabled: boolean }[]>({
    queryKey: ["notification-preferences"],
    queryFn: () => apiFetch<{ category: string; enabled: boolean }[]>("/api/v1/notifications/preferences"),
  });
  const isOn = (cat: string) => prefsQuery.data?.find((p) => p.category === cat)?.enabled ?? true;

  const setPreference = useMutation({
    mutationFn: ({ category, enabled }: { category: string; enabled: boolean }) =>
      apiFetch("/api/v1/notifications/preferences", { method: "PUT", body: JSON.stringify({ category, enabled }) }),
    // flip the switch straight away, put it back if the save fails
    onMutate: async ({ category, enabled }) => {
      await queryClient.cancelQueries({ queryKey: ["notification-preferences"] });
      const previous = queryClient.getQueryData<{ category: string; enabled: boolean }[]>(["notification-preferences"]);
      queryClient.setQueryData<{ category: string; enabled: boolean }[]>(["notification-preferences"], (old = []) => [
        ...old.filter((p) => p.category !== category), { category, enabled },
      ]);
      return { previous };
    },
    onError: (_e, _v, ctx) => queryClient.setQueryData(["notification-preferences"], ctx?.previous),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["notification-preferences"] }),
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
        <p className="mb-1 text-sm font-medium text-ink">Categories</p>
        <p className="mb-2 text-xs text-muted">Green means you get these notifications. Red means that category is muted for you.</p>
        <div className="flex flex-wrap gap-2">
          {CATEGORIES.map((cat) => {
            const on = isOn(cat);
            return (
              <div
                key={cat}
                className={`flex items-center gap-2 rounded-full border px-3 py-1 text-xs ${on ? "border-green-500 bg-green-50 text-ink" : "border-red-400 bg-red-50 text-ink"}`}
              >
                <span className={`h-2 w-2 rounded-full ${on ? "bg-green-500" : "bg-red-500"}`} aria-hidden />
                <span className="capitalize">{cat}</span>
                <span className={`font-medium ${on ? "text-green-700" : "text-red-700"}`}>{on ? "On" : "Off"}</span>
                <div className="flex overflow-hidden rounded-full border border-hairline" role="group" aria-label={`${cat} notifications`}>
                  <button
                    type="button"
                    aria-pressed={on}
                    className={`px-2 py-0.5 ${on ? "bg-green-500 text-white" : "bg-white text-muted hover:text-ink"}`}
                    onClick={() => setPreference.mutate({ category: cat, enabled: true })}
                  >
                    on
                  </button>
                  <button
                    type="button"
                    aria-pressed={!on}
                    className={`px-2 py-0.5 ${!on ? "bg-red-500 text-white" : "bg-white text-muted hover:text-ink"}`}
                    onClick={() => setPreference.mutate({ category: cat, enabled: false })}
                  >
                    off
                  </button>
                </div>
              </div>
            );
          })}
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
