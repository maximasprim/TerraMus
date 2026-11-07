"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

/** A staff login account and the employee record (if any) it is linked to. */
export interface LoginAccount {
  id: string;
  full_name: string;
  email: string;
  is_active: boolean;
  employee_id: string | null;
  employee_number: string | null;
}

export const LOGIN_ACCOUNTS_KEY = ["employee-login-accounts"] as const;

/** Needs the employees.manage permission (the API says 403 otherwise, which just leaves `data` empty). */
export function useLoginAccounts(enabled = true) {
  return useQuery<LoginAccount[]>({
    queryKey: LOGIN_ACCOUNTS_KEY,
    queryFn: () => apiFetch<LoginAccount[]>("/api/v1/employees/login-accounts"),
    enabled,
    retry: false,
  });
}
