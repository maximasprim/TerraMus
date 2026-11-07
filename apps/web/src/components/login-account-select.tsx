"use client";

import { Select } from "@/components/ui";
import type { LoginAccount } from "@/lib/use-login-accounts";

/** Picker for the "Login account" of an employee: accounts nobody is linked to yet, plus the one this employee
 * already has. An empty value means "no login account". */
export function LoginAccountSelect({
  id,
  accounts,
  value,
  onChange,
  currentEmployeeId,
  label = "Login account (optional)",
}: {
  id: string;
  accounts: LoginAccount[];
  value: string;
  onChange: (userId: string) => void;
  currentEmployeeId?: string;
  label?: string;
}) {
  const options = accounts.filter((a) => a.employee_id === null || a.employee_id === currentEmployeeId);
  return (
    <Select id={id} label={label} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">No login account</option>
      {options.map((a) => (
        <option key={a.id} value={a.id}>
          {a.full_name} - {a.email}
          {a.is_active ? "" : " (inactive)"}
        </option>
      ))}
    </Select>
  );
}
