"use client";

import { platformApiFetch } from "@/lib/platform-api";
import { setWorkspaceSession } from "@/lib/impersonation";

interface WorkspaceSessionOut {
  access_token: string;
  expires_at: string;
  organization_id: string;
  organization_name: string;
  acting_as: string;
}

/** Start a superadmin workspace session for an organization and land on `path` in the tenant's own admin app
 * (a full page load, so no cached data from anywhere else can carry over). Throws PlatformApiError on refusal. */
export async function openTenantWorkspace(orgId: string, path: string): Promise<void> {
  const s = await platformApiFetch<WorkspaceSessionOut>(`/api/v1/platform/organizations/${orgId}/workspace-session`, { method: "POST" });
  setWorkspaceSession({
    token: s.access_token, orgId: s.organization_id, orgName: s.organization_name, actingAs: s.acting_as, expiresAt: s.expires_at,
  });
  window.location.assign(path);
}
