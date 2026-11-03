"use client";

import { useState } from "react";
import { Button, Card, ErrorState } from "@/components/ui";
import { PlatformApiError } from "@/lib/platform-api";
import { openTenantWorkspace } from "@/lib/platform-workspace";

/** What a platform console tab shows to a superadmin when the tenant's own page does the whole job: one button
 * into that page, in the organization's real admin app. */
export function PlatformWorkspaceHandoff({ orgId, label, menu }: { orgId: string; label: string; menu: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function open() {
    setError(null);
    setBusy(true);
    try {
      await openTenantWorkspace(orgId, menu);
    } catch (err) {
      setBusy(false);
      setError(err instanceof PlatformApiError ? err.message : "Could not open the workspace");
    }
  }

  return (
    <Card>
      <p className="font-display text-lg text-forest">{label} is managed in the organization&apos;s workspace</p>
      <p className="mt-1 text-sm text-muted">
        This opens the organization&apos;s own {label.toLowerCase()} page, where you can do everything their owner can. Your
        changes are recorded against your platform account.
      </p>
      {error && <div className="mt-3"><ErrorState message={error} /></div>}
      <div className="mt-4">
        <Button disabled={busy} onClick={open}>{busy ? "Opening…" : `Open ${label} in workspace`}</Button>
      </div>
    </Card>
  );
}
