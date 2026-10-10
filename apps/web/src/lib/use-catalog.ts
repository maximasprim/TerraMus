import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { EffectiveCatalog } from "@/lib/types";

/**
 * This organization's effective catalog: which modules (livestock / crops) and
 * which species / crop types a platform admin has left enabled for it.
 *
 * The query key matches the one the create-forms already use, so every screen
 * shares a single cached request. `data` is undefined until loaded (or if the
 * request fails) - callers must treat that as "everything allowed" (fail open),
 * so a slow or failed catalog fetch can never hide or block anything.
 */
export function useCatalog(enabled = true) {
  return useQuery<EffectiveCatalog>({
    queryKey: ["catalog"],
    queryFn: () => apiFetch<EffectiveCatalog>("/api/v1/catalog"),
    enabled,
  });
}
