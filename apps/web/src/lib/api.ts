"use client";

/**
 * Thin API client for the FastAPI backend built in apps/api.
 *
 * Access tokens are held in memory + localStorage (short-lived, 15 min per
 * apps/api/app/core/config.py); refresh tokens are localStorage-only and
 * used to silently mint a new access token on a 401. This mirrors exactly
 * the token contract apps/api/app/modules/identity already implements -
 * nothing here is invented, it's a client for a real, tested backend.
 */

export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const ACCESS_KEY = "farm.access_token";
const REFRESH_KEY = "farm.refresh_token";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ACCESS_KEY);
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(REFRESH_KEY);
}

export function setTokens(access: string, refresh: string) {
  localStorage.setItem(ACCESS_KEY, access);
  localStorage.setItem(REFRESH_KEY, refresh);
}

export function clearTokens() {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

import { fetchAllPages, formatErrorDetail, type FetchAllOptions } from "@/lib/api-utils";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

// The backend ROTATES refresh tokens: using one revokes it. If several requests
// hit an expired access token at the same moment (a dashboard fires many in
// parallel) and each refreshed on its own, the first would win and the rest
// would be rejected - and their failure cleared the tokens, logging the user
// out mid-session. So all concurrent refreshes share one in-flight request.
let refreshInFlight: Promise<string | null> | null = null;

function refreshAccessToken(): Promise<string | null> {
  if (!refreshInFlight) {
    refreshInFlight = performRefresh().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

/** Called after a 401. If a different access token is now stored, another
 * request already refreshed while this one was in flight - just use that one
 * instead of rotating the refresh token again. */
async function tokenAfter401(tokenUsed: string | null): Promise<string | null> {
  const current = getAccessToken();
  if (current && current !== tokenUsed) return current;
  return refreshAccessToken();
}

async function performRefresh(): Promise<string | null> {
  const refresh_token = getRefreshToken();
  if (!refresh_token) return null;
  const resp = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token }),
  });
  if (!resp.ok) {
    clearTokens();
    return null;
  }
  const data = await resp.json();
  setTokens(data.access_token, data.refresh_token);
  return data.access_token as string;
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit & { auth?: boolean } = {},
): Promise<T> {
  const { auth = true, headers, ...rest } = options;
  const doFetch = async (token: string | null) => {
    const finalHeaders: Record<string, string> = {
      "Content-Type": "application/json",
      ...(headers as Record<string, string> | undefined),
    };
    // Multipart uploads: the browser must generate the Content-Type (with its
    // boundary) itself - forcing application/json would break the request.
    if (typeof FormData !== "undefined" && rest.body instanceof FormData) delete finalHeaders["Content-Type"];
    if (auth && token) finalHeaders.Authorization = `Bearer ${token}`;
    return fetch(`${API_BASE}${path}`, { ...rest, headers: finalHeaders });
  };

  const tokenUsed = getAccessToken();
  let resp = await doFetch(tokenUsed);

  if (resp.status === 401 && auth) {
    const newToken = await tokenAfter401(tokenUsed);
    if (newToken) {
      resp = await doFetch(newToken);
    }
  }

  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(resp.status, formatErrorDetail(detail));
  }

  if (resp.status === 204) return undefined as T;
  return resp.json() as Promise<T>;
}

/** For multipart/form-data endpoints (bulk import) - apiFetch always sets
 * Content-Type: application/json, which would break a file upload; this
 * intentionally omits that header so fetch sets the correct multipart
 * boundary itself. */
export async function apiUpload<T>(
  path: string,
  formData: FormData,
  options: { method?: string } = {},
): Promise<T> {
  const doFetch = async (token: string | null) => {
    const headers: Record<string, string> = {};
    if (token) headers.Authorization = `Bearer ${token}`;
    return fetch(`${API_BASE}${path}`, { method: options.method ?? "POST", headers, body: formData });
  };

  const tokenUsed = getAccessToken();
  let resp = await doFetch(tokenUsed);
  if (resp.status === 401) {
    const newToken = await tokenAfter401(tokenUsed);
    if (newToken) resp = await doFetch(newToken);
  }
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(resp.status, formatErrorDetail(detail));
  }
  return resp.json() as Promise<T>;
}

/** For binary responses (invoice/report PDFs, animal QR SVGs) - triggers a
 * browser download rather than trying to parse the response as JSON. */
export async function apiDownload(path: string, filename: string): Promise<void> {
  const doFetch = (token: string | null) =>
    fetch(`${API_BASE}${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : undefined });

  // Same silent refresh as apiFetch - downloads used to simply fail once the
  // 15-minute access token had expired.
  const tokenUsed = getAccessToken();
  let resp = await doFetch(tokenUsed);
  if (resp.status === 401) {
    const newToken = await tokenAfter401(tokenUsed);
    if (newToken) resp = await doFetch(newToken);
  }
  if (!resp.ok) {
    let detail: unknown = resp.statusText;
    try {
      const body = await resp.json();
      detail = body.detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(resp.status, formatErrorDetail(detail));
  }
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

/** GET a list endpoint that paginates, returning every row (see api-utils.fetchAllPages). */
export function apiFetchAll<T>(path: string, options?: FetchAllOptions): Promise<T[]> {
  return fetchAllPages<T>(path, (url) => apiFetch<T[]>(url), options);
}
