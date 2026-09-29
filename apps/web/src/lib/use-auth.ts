"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, clearTokens, getAccessToken, setTokens } from "@/lib/api";
import type { MeResponse, TokenPair } from "@/lib/types";

export function useMe() {
  return useQuery<MeResponse>({
    queryKey: ["me"],
    queryFn: () => apiFetch<MeResponse>("/api/v1/auth/me"),
    enabled: typeof window !== "undefined" && !!getAccessToken(),
    retry: false,
  });
}

/** Redirects to /login if there's no valid session. Use at the top of any
 * protected page/layout rather than duplicating the check everywhere. */
export function useRequireAuth() {
  const router = useRouter();
  const meQuery = useMe();
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    if (meQuery.isError) {
      clearTokens();
      router.replace("/login");
      return;
    }
    if (meQuery.data) setChecked(true);
  }, [meQuery.isError, meQuery.data, router]);

  return { me: meQuery.data, ready: checked && !meQuery.isLoading };
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
