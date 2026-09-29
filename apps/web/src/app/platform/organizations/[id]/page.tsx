"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { PlatformShell } from "@/components/platform-shell";
import { Card, Button, ErrorState } from "@/components/ui";
import { platformApiFetch, PlatformApiError } from "@/lib/platform-api";
import { usePlatformMe } from "@/lib/use-platform-auth";
import { PLATFORM_MODULES } from "@/lib/platform-modules";
import type { OrganizationSummaryOut } from "@/lib/platform-types";

export default function OrganizationDetailPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const { data: me } = usePlatformMe();
  const canWrite = me?.role === "superadmin";
  const [error, setError] = useState<string | null>(null);

  const orgQuery = useQuery<OrganizationSummaryOut>({
    queryKey: ["platform-organization", id],
    queryFn: () => platformApiFetch<OrganizationSummaryOut>(`/api/v1/platform/organizations/${id}`),
  });

  const toggleSuspend = useMutation({
    mutationFn: (isSuspended: boolean) =>
      platformApiFetch(`/api/v1/platform/organizations/${id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ is_suspended: isSuspended }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["platform-organization", id] });
      queryClient.invalidateQueries({ queryKey: ["platform-organizations"] });
      setError(null);
    },
    onError: (err) => setError(err instanceof PlatformApiError ? err.message : "Failed to update organization"),
  });

  if (orgQuery.error) {
    return (
      <PlatformShell>
        <ErrorState message={orgQuery.error instanceof PlatformApiError ? orgQuery.error.message : "Failed to load organization"} />
      </PlatformShell>
    );
  }
  if (!orgQuery.data) {
    return (
      <PlatformShell>
        <p className="text-sm text-muted">Loading…</p>
      </PlatformShell>
    );
  }

  const org = orgQuery.data;

  return (
    <PlatformShell>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl text-forest">{org.name}</h1>
          <p className="text-sm text-muted">{org.slug} · {org.currency}</p>
        </div>
        {canWrite && (
          <Button
            variant={org.is_suspended ? "primary" : "ghost"}
            disabled={toggleSuspend.isPending}
            onClick={() => toggleSuspend.mutate(!org.is_suspended)}
          >
            {org.is_suspended ? "Reactivate organization" : "Suspend organization"}
          </Button>
        )}
      </div>

      {error && <div className="mb-4"><ErrorState message={error} /></div>}

      {org.is_suspended && (
        <div className="mb-6 rounded-lg border border-clay/30 bg-clay/5 px-4 py-3 text-sm text-clay">
          This organization is suspended. Its users cannot log in or make any API requests until reactivated.
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <Card>
          <p className="text-xs font-medium uppercase tracking-wider text-muted">Users</p>
          <p className="font-display text-2xl text-forest">{org.user_count}</p>
        </Card>
        <Card>
          <p className="text-xs font-medium uppercase tracking-wider text-muted">Subscription tier</p>
          <p className="font-display text-2xl text-forest">{org.subscription_tier ?? "-"}</p>
        </Card>
        <Card>
          <p className="text-xs font-medium uppercase tracking-wider text-muted">Subscription status</p>
          <p className="font-display text-2xl text-forest capitalize">{org.subscription_status ?? "-"}</p>
        </Card>
      </div>

      <p className="mt-6 text-xs text-muted">
        Created {new Date(org.created_at).toLocaleDateString()}.
      </p>

      <div className="mb-2 mt-8 flex flex-wrap gap-1 border-b border-hairline">
        {PLATFORM_MODULES.map((m) => (
          <Link
            key={m.slug}
            href={`/platform/organizations/${org.id}/${m.slug}`}
            className="rounded-t-md px-3 py-2 text-sm text-muted hover:bg-white/40"
          >
            {m.label}
          </Link>
        ))}
      </div>
      <p className="text-xs text-muted">
        Browse this organization&apos;s data by module above - health, breeding, and dairy records
        are per-animal and aren&apos;t covered by this tab bar; use the API directly for those
        (see HOW_TO_APPLY.md).
      </p>
    </PlatformShell>
  );
}
