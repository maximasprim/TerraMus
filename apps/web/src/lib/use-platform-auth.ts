"use client";

import { useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { platformApiFetch, clearPlatformToken, getPlatformToken, setPlatformToken } from "@/lib/platform-api";
import type { PlatformAdminOut } from "@/lib/platform-types";

export function usePlatformMe() {
  return useQuery<PlatformAdminOut>({
    queryKey: ["platform-me"],
    queryFn: () => platformApiFetch<PlatformAdminOut>("/api/v1/platform/auth/me"),
    enabled: typeof window !== "undefined" && !!getPlatformToken(),
    retry: false,
  });
}

/** Redirects to /platform/login if there's no valid platform-admin session.
 * Same shape as lib/use-auth.ts's useRequireAuth, kept separate because the
 * two token stores and the two "am I logged in" checks are entirely
 * independent (see platform-api.ts's module docstring). */
export function useRequirePlatformAuth() {
  const router = useRouter();
  const meQuery = usePlatformMe();

  useEffect(() => {
    if (!getPlatformToken()) {
      router.replace("/platform/login");
      return;
    }
    if (meQuery.isError) {
      clearPlatformToken();
      router.replace("/platform/login");
      return;
    }
  }, [meQuery.isError, meQuery.data, router]);

  // `ready` is simply "the session is known". It used to be a per-mount flag that started false, so
  // every page that mounted a fresh shell flashed a full-screen "Loading..." even though the session
  // was already cached. Deriving it from the data removes that flash.
  return { me: meQuery.data, ready: !!meQuery.data };
}

export function usePlatformLogin() {
  const queryClient = useQueryClient();
  const router = useRouter();

  return useCallback(
    async (email: string, password: string) => {
      // Login is x-www-form-urlencoded (OAuth2PasswordRequestForm on the
      // backend), unlike every other JSON endpoint here - platformApiFetch
      // still works since we pass a pre-built body + explicit header.
      const body = new URLSearchParams({ username: email, password });
      const resp = await platformApiFetch<{ access_token: string }>("/api/v1/platform/auth/login", {
        method: "POST",
        auth: false,
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: body.toString(),
      });
      setPlatformToken(resp.access_token);
      await queryClient.invalidateQueries({ queryKey: ["platform-me"] });
      router.push("/platform/dashboard");
    },
    [queryClient, router],
  );
}

export function usePlatformLogout() {
  const router = useRouter();
  const queryClient = useQueryClient();
  return useCallback(() => {
    clearPlatformToken();
    queryClient.clear();
    router.push("/platform/login");
  }, [router, queryClient]);
}
