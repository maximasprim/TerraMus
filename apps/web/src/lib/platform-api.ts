"use client";

/**
 * Separate from lib/api.ts on purpose, mirroring the backend's own
 * separation (apps/api/app/modules/platform_admin/security.py): a
 * platform-admin JWT carries "type": "platform_admin", is rejected by
 * every tenant route, and - unlike the tenant flow - has no refresh token
 * at all (apps/api/app/modules/platform_admin/router.py's /auth/login only
 * ever returns an access token). So this client uses its own localStorage
 * key and, on a 401, just clears the token and lets the caller redirect to
 * /platform/login rather than attempting a silent refresh that doesn't
 * exist on the backend.
 */

export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const PLATFORM_ACCESS_KEY = "platform.access_token";

export function getPlatformToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(PLATFORM_ACCESS_KEY);
}

export function setPlatformToken(token: string) {
  localStorage.setItem(PLATFORM_ACCESS_KEY, token);
}

export function clearPlatformToken() {
  localStorage.removeItem(PLATFORM_ACCESS_KEY);
}

export class PlatformApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function platformApiFetch<T>(
  path: string,
  options: RequestInit & { auth?: boolean } = {},
): Promise<T> {
  const { auth = true, headers, ...rest } = options;
  const finalHeaders: Record<string, string> = {
    "Content-Type": "application/json",
    ...(headers as Record<string, string> | undefined),
  };
  const token = getPlatformToken();
  if (auth && token) finalHeaders.Authorization = `Bearer ${token}`;

  const resp = await fetch(`${API_BASE}${path}`, { ...rest, headers: finalHeaders });

  if (resp.status === 401 && auth) {
    clearPlatformToken();
  }

  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      /* non-JSON error body */
    }
    throw new PlatformApiError(resp.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }

  if (resp.status === 204) return undefined as T;
  return resp.json() as Promise<T>;
}
