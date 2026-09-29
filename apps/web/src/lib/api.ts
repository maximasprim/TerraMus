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

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function refreshAccessToken(): Promise<string | null> {
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
    if (auth && token) finalHeaders.Authorization = `Bearer ${token}`;
    return fetch(`${API_BASE}${path}`, { ...rest, headers: finalHeaders });
  };

  let resp = await doFetch(getAccessToken());

  if (resp.status === 401 && auth) {
    const newToken = await refreshAccessToken();
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
    throw new ApiError(resp.status, typeof detail === "string" ? detail : JSON.stringify(detail));
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

  let resp = await doFetch(getAccessToken());
  if (resp.status === 401) {
    const newToken = await refreshAccessToken();
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
    throw new ApiError(resp.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return resp.json() as Promise<T>;
}

/** For binary responses (invoice/report PDFs, animal QR SVGs) - triggers a
 * browser download rather than trying to parse the response as JSON. */
export async function apiDownload(path: string, filename: string): Promise<void> {
  const token = getAccessToken();
  const resp = await fetch(`${API_BASE}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!resp.ok) throw new ApiError(resp.status, resp.statusText);
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
