"use client";

/**
 * A superadmin's "workspace session": the tenant admin app opened as one organization (see
 * apps/api/app/modules/platform_admin/impersonation.py).
 *
 * Held in sessionStorage - per tab, gone when the tab closes - and deliberately NOT in localStorage, so it can
 * never overwrite or leak into a normal tenant login in the same browser. While a session exists,
 * lib/api.ts sends its token instead of the stored tenant token, and never tries to refresh it (it has no
 * refresh token; when it expires the person simply returns to the platform console).
 */

const SESSION_KEY = "farm.workspace_session";

export interface WorkspaceSession {
  token: string;
  orgId: string;
  orgName: string;
  actingAs: string;
  expiresAt: string;
}

export function getWorkspaceSession(): WorkspaceSession | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    return raw ? (JSON.parse(raw) as WorkspaceSession) : null;
  } catch {
    return null;
  }
}

export function isWorkspaceSession(): boolean {
  return getWorkspaceSession() !== null;
}

export function setWorkspaceSession(session: WorkspaceSession): void {
  sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
}

export function clearWorkspaceSession(): void {
  try { sessionStorage.removeItem(SESSION_KEY); } catch { /* ignore */ }
}

/** Leave the workspace and go back to the organization in the platform console. A full page load on purpose:
 * it drops every cached tenant query so nothing from this organization can appear in the next one. */
export function exitWorkspace(): void {
  const orgId = getWorkspaceSession()?.orgId;
  clearWorkspaceSession();
  window.location.assign(orgId ? `/platform/organizations/${orgId}` : "/platform/organizations");
}
