"use client";

import { useEffect, useState } from "react";
import { ShieldAlert } from "lucide-react";
import { exitWorkspace, getWorkspaceSession, type WorkspaceSession } from "@/lib/impersonation";

/** Shown at the top of every tenant admin page while a superadmin is working inside an organization. Renders
 * nothing for ordinary tenant users. */
export function ImpersonationBanner() {
  const [session, setSession] = useState<WorkspaceSession | null>(null);
  useEffect(() => setSession(getWorkspaceSession()), []);
  if (!session) return null;
  return (
    <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-clay/30 bg-clay/5 px-4 py-2 text-sm text-clay">
      <span className="flex items-center gap-2">
        <ShieldAlert size={16} />
        <span>
          Superadmin workspace: you are working inside <strong>{session.orgName}</strong> as {session.actingAs}. Every change
          is recorded against your platform account.
        </span>
      </span>
      <button type="button" onClick={exitWorkspace} className="rounded-md border border-clay/40 px-3 py-1 font-medium hover:bg-clay/10">
        Exit workspace
      </button>
    </div>
  );
}
