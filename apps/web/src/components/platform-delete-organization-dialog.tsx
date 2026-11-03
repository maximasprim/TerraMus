"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ErrorState, Input, Modal } from "@/components/ui";
import { PlatformApiError, platformApiFetch } from "@/lib/platform-api";

interface DeletionPreview {
  organization_name: string;
  total_records: number;
  counts: Record<string, number>;
}

/** Permanent deletion of a SUSPENDED organization. The server enforces every rule (suspended, superadmin, exact
 * name, the admin's own password); this dialog just makes the consequences visible first and asks for the two
 * confirmations. */
export function DeleteOrganizationDialog({
  orgId, orgName, open, onClose, onDeleted,
}: { orgId: string; orgName: string; open: boolean; onClose: () => void; onDeleted: () => void }) {
  const [typedName, setTypedName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) { setTypedName(""); setPassword(""); setError(null); }
  }, [open, orgId]);

  const preview = useQuery<DeletionPreview>({
    queryKey: ["platform-deletion-preview", orgId],
    queryFn: () => platformApiFetch<DeletionPreview>(`/api/v1/platform/organizations/${orgId}/deletion-preview`),
    enabled: open,
    staleTime: 0,
    gcTime: 0,
  });

  const remove = useMutation({
    mutationFn: () =>
      platformApiFetch(`/api/v1/platform/organizations/${orgId}/permanent-delete`, {
        method: "POST",
        body: JSON.stringify({ confirm_name: typedName, password }),
      }),
    onSuccess: () => onDeleted(),
    onError: (err) => setError(err instanceof PlatformApiError ? err.message : "Could not delete the organization"),
  });

  const top = Object.entries(preview.data?.counts ?? {}).filter(([k]) => k !== "organizations").slice(0, 6);
  const ready = typedName === orgName && password.length > 0 && !remove.isPending;

  return (
    <Modal open={open} onClose={remove.isPending ? () => {} : onClose} title="Delete organization permanently">
      <p className="text-sm text-ink">
        You are about to permanently delete <strong>{orgName}</strong> and everything in it. <strong>This cannot be undone</strong>,
        and the organization&apos;s users will no longer be able to sign in.
      </p>

      <div className="mt-3 rounded-md border border-hairline bg-white/60 px-3 py-2 text-sm">
        {preview.isLoading && <span className="text-muted">Counting records…</span>}
        {preview.error && <span className="text-clay">Could not count the records to be deleted.</span>}
        {preview.data && (
          <>
            <p className="text-ink"><strong>{preview.data.total_records.toLocaleString()}</strong> records will be deleted.</p>
            {top.length > 0 && (
              <p className="mt-1 text-xs text-muted">
                Largest: {top.map(([k, n]: [string, number]) => `${k.replace(/_/g, " ")} (${n.toLocaleString()})`).join(", ")}
              </p>
            )}
          </>
        )}
      </div>
      <p className="mt-2 text-xs text-muted">
        Consider exporting anything you need to keep first, such as billing records. The audit log is append-only, so its
        entries about this organization are kept.
      </p>

      <div className="mt-4 space-y-3">
        <Input
          label={`Type "${orgName}" to confirm`}
          value={typedName}
          onChange={(e) => setTypedName(e.target.value)}
          autoComplete="off"
        />
        <Input
          label="Your platform password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
        />
      </div>

      {error && <div className="mt-3"><ErrorState message={error} /></div>}

      <div className="mt-5 flex justify-end gap-2">
        <button
          type="button"
          onClick={onClose}
          disabled={remove.isPending}
          className="rounded-md border border-hairline px-4 py-2 text-sm text-ink hover:bg-hairline/40 disabled:opacity-50"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={() => { setError(null); remove.mutate(); }}
          disabled={!ready}
          className="rounded-md bg-clay px-4 py-2 text-sm font-medium text-paper hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {remove.isPending ? "Deleting…" : "Delete permanently"}
        </button>
      </div>
    </Modal>
  );
}