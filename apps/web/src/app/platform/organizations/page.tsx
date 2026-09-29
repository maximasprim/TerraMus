"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { PlatformShell } from "@/components/platform-shell";
import { Card, Button, Input, ErrorState, EmptyState, StatusBadge } from "@/components/ui";
import { platformApiFetch, PlatformApiError } from "@/lib/platform-api";
import { usePlatformMe } from "@/lib/use-platform-auth";
import type { OrganizationSummaryOut } from "@/lib/platform-types";

export default function OrganizationsPage() {
  const queryClient = useQueryClient();
  const { data: me } = usePlatformMe();
  const canWrite = me?.role === "superadmin";
  const [search, setSearch] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);

  const orgsQuery = useQuery<OrganizationSummaryOut[]>({
    queryKey: ["platform-organizations", search],
    queryFn: () =>
      platformApiFetch<OrganizationSummaryOut[]>(
        `/api/v1/platform/organizations${search ? `?search=${encodeURIComponent(search)}` : ""}`,
      ),
  });

  const toggleSuspend = useMutation({
    mutationFn: ({ orgId, isSuspended }: { orgId: string; isSuspended: boolean }) =>
      platformApiFetch(`/api/v1/platform/organizations/${orgId}/status`, {
        method: "PATCH",
        body: JSON.stringify({ is_suspended: isSuspended }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["platform-organizations"] });
      setActionError(null);
    },
    onError: (err) => setActionError(err instanceof PlatformApiError ? err.message : "Failed to update organization"),
  });

  return (
    <PlatformShell>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl text-forest">Organizations</h1>
          <p className="text-sm text-muted">Every tenant on the platform.</p>
        </div>
        <Input
          placeholder="Search by name…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-64"
        />
      </div>

      {actionError && <div className="mb-4"><ErrorState message={actionError} /></div>}
      {orgsQuery.error && (
        <ErrorState message={orgsQuery.error instanceof PlatformApiError ? orgsQuery.error.message : "Failed to load organizations"} />
      )}
      {orgsQuery.data && orgsQuery.data.length === 0 && (
        <EmptyState title="No organizations found" body="Try a different search." />
      )}
      {orgsQuery.data && orgsQuery.data.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-hairline">
          <table className="w-full text-left text-sm">
            <thead className="bg-ink text-paper">
              <tr>
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Users</th>
                <th className="px-4 py-3 font-medium">Tier</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium" />
              </tr>
            </thead>
            <tbody>
              {orgsQuery.data.map((org, i) => (
                <tr key={org.id} className={i % 2 === 0 ? "bg-white/40" : "bg-white/70"}>
                  <td className="px-4 py-3">
                    <Link href={`/platform/organizations/${org.id}`} className="font-medium text-forest hover:underline">
                      {org.name}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-muted">{org.user_count}</td>
                  <td className="px-4 py-3 text-muted">
                    {org.subscription_tier ?? "-"}
                    {org.subscription_status && (
                      <span className="ml-1 text-xs text-muted">({org.subscription_status})</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={org.is_suspended ? "cancelled" : "active"} />
                  </td>
                  <td className="px-4 py-3 text-right">
                    {canWrite && (
                      <Button
                        variant="ghost"
                        className="text-xs"
                        disabled={toggleSuspend.isPending}
                        onClick={() => toggleSuspend.mutate({ orgId: org.id, isSuspended: !org.is_suspended })}
                      >
                        {org.is_suspended ? "Reactivate" : "Suspend"}
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </PlatformShell>
  );
}
