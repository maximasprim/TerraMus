"use client";

import type { ReactNode } from "react";
import { useCan } from "@/lib/use-auth";

/** Renders its children only if the signed-in user holds `permission` (a backend
 * permission code). Hides buttons a role can't use instead of letting them click
 * into a 403. A usability layer only - the backend enforces every request. */
export function Can({ permission, children }: { permission: string; children: ReactNode }) {
  const can = useCan();
  return can(permission) ? <>{children}</> : null;
}
