"use client";

import { useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, clearTokens, getAccessToken, isNetworkFailure, readCachedMe, setTokens, writeCachedMe } from "@/lib/api";
import { hasPermission } from "@/lib/permissions";
import type { MeResponse, TokenPair } from "@/lib/types";

export function useMe() {
  return useQuery<MeResponse>({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        const me = await apiFetch<MeResponse>("/api/v1/auth/me");
        writeCachedMe(me);
        return me;
      } catch (e) {
        // No signal (e.g. at the crush pen): open with the last known profile instead of failing.
        // The backend re-checks every permission on every request, so a stale copy cannot grant access.
        if (isNetworkFailure(e)) {
          const cached = readCachedMe<MeResponse>();
          if (cached) return cached;
        }
        throw e;
      }
    },
    enabled: typeof window !== "undefined" && !!getAccessToken(),
    retry: false,
  });
}

/** `can("livestock.update")` - whether the signed-in user holds a backend permission, for showing or
 * hiding action buttons. Reads the cached /auth/me (no extra request). A usability layer only: the
 * backend re-checks every request. Allows everything until permissions have loaded (fail open). */
export function useCan() {
  const permissions = useMe().data?.permissions;
  return useCallback((code: string) => hasPermission(permissions, code), [permissions]);
}

/** Redirects to /login if there's no valid session. Use at the top of any
 * protected page/layout rather than duplicating the check everywhere. */
export function useRequireAuth() {
  const router = useRouter();
  const meQuery = useMe();

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    if (meQuery.isError) {
      // A lost connection is not a lost session: never sign the user out because the network is down.
      if (isNetworkFailure(meQuery.error)) return;
      clearTokens();
      router.replace("/login");
      return;
    }
  }, [meQuery.isError, meQuery.data, router]);

  // `ready` is simply "the session is known". It used to be a per-mount flag that started false, so
  // every page that mounted a fresh shell flashed a full-screen "Loading..." even though the session
  // was already cached. Deriving it from the data removes that flash.
  return { me: meQuery.data, ready: !!meQuery.data };
}

export function useLogin() {
  const queryClient = useQueryClient();
  const router = useRouter();

  return useCallback(
    async (email: string, password: string) => {
      const tokens = await apiFetch<TokenPair>("/api/v1/auth/login", {
        method: "POST",
        auth: false,
        body: JSON.stringify({ email, password }),
      });
      setTokens(tokens.access_token, tokens.refresh_token);
      await queryClient.invalidateQueries({ queryKey: ["me"] });
      router.push("/admin/dashboard");
    },
    [queryClient, router],
  );
}

/** Spec §1/§64: register a brand-new organization (tenant) and its owner
 * user in one call - POST /api/v1/auth/register has existed on the backend
 * since Phase 1, but no page in apps/web ever called it; every account
 * used for local testing so far was created via curl. This closes that
 * gap: the actual "sign up your farm" entry point a real first-time user
 * needs. */
export function useRegisterOrganization() {
  const queryClient = useQueryClient();
  const router = useRouter();

  return useCallback(
    async (body: { organization_name: string; full_name: string; email: string; phone?: string; password: string }) => {
      const tokens = await apiFetch<TokenPair>("/api/v1/auth/register", {
        method: "POST",
        auth: false,
        body: JSON.stringify(body),
      });
      setTokens(tokens.access_token, tokens.refresh_token);
      await queryClient.invalidateQueries({ queryKey: ["me"] });
      router.push("/admin/dashboard");
    },
    [queryClient, router],
  );
}

export function useLogout() {
  const router = useRouter();
  const queryClient = useQueryClient();
  return useCallback(() => {
    clearTokens();
    queryClient.clear();
    router.push("/login");
  }, [router, queryClient]);
}
