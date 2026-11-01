"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { Button, Input, Select, Modal, ErrorState, EmptyState, StatusBadge } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import type { Employee } from "@/lib/types";

const EMPLOYMENT_TYPES = ["full_time", "part_time", "casual", "contract"] as const;

export default function EmployeesPage() {
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data, isLoading, error: loadError } = useQuery<Employee[]>({
    queryKey: ["employees"],
    queryFn: () => apiFetch<Employee[]>("/api/v1/employees"),
  });

  const create = useMutation({
    mutationFn: (body: { full_name: string; job_title?: string; department?: string; employment_type: string; hire_date?: string }) =>
      apiFetch("/api/v1/employees", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["employees"] });
      setModalOpen(false);
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Failed to create employee"),
  });

  return (
    <AdminShell>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl text-forest">Employees</h1>
          <p className="text-sm text-muted">Farm staff - HR profiles, employment status, work shifts.</p>
        </div>
        <Button onClick={() => { setError(null); setModalOpen(true); }}>+ New employee</Button>
      </div>

      {loadError && <ErrorState message={loadError instanceof ApiError ? loadError.message : "Failed to load employees"} />}
      {isLoading && <p className="text-sm text-muted">Loading…</p>}
      {data && data.length === 0 && (
        <EmptyState title="No employees yet" body="Add farm staff to track roles and employment status." />
      )}

      {data && data.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-hairline">
          <table className="w-full text-left text-sm">
            <thead className="bg-forest text-paper">
              <tr>
                <th className="px-4 py-3 font-medium">Employee #</th>
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Job title</th>
                <th className="px-4 py-3 font-medium">Department</th>
                <th className="px-4 py-3 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {data.map((e, i) => (
                <tr key={e.id} className={i % 2 === 0 ? "bg-white/40" : "bg-white/70"}>
                  <td className="px-4 py-3">
                    <Link href={`/admin/employees/${e.id}`} className="font-mono text-xs text-forest hover:underline">
                      {e.employee_number}
                    </Link>
                  </td>
                  <td className="px-4 py-3 font-medium text-ink">{e.full_name}</td>
                  <td className="px-4 py-3 text-muted">{e.job_title ?? "-"}</td>
                  <td className="px-4 py-3 capitalize text-muted">{e.department ?? "-"}</td>
                  <td className="px-4 py-3"><StatusBadge status={e.employment_status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title="New employee">
        <EmployeeForm error={error} pending={create.isPending} onSubmit={(b) => create.mutate(b)} />
      </Modal>
    </AdminShell>
  );
}

function EmployeeForm({
  onSubmit,
  error,
  pending,
}: {
  onSubmit: (body: { full_name: string; job_title?: string; department?: string; employment_type: string; hire_date?: string }) => void;
  error: string | null;
  pending: boolean;
}) {
  const [fullName, setFullName] = useState("");
  const [jobTitle, setJobTitle] = useState("");
  const [department, setDepartment] = useState("");
  const [employmentType, setEmploymentType] = useState<string>(EMPLOYMENT_TYPES[0]);
  const [hireDate, setHireDate] = useState("");

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({
          full_name: fullName, job_title: jobTitle || undefined, department: department || undefined,
          employment_type: employmentType, hire_date: hireDate || undefined,
        });
      }}
      className="space-y-3"
    >
      {error && <ErrorState message={error} />}
      <Input id="emp-name" label="Full name" required value={fullName} onChange={(e) => setFullName(e.target.value)} />
      <Input id="emp-title" label="Job title" value={jobTitle} onChange={(e) => setJobTitle(e.target.value)} placeholder="Herdsman, Milker…" />
      <Input id="emp-dept" label="Department" value={department} onChange={(e) => setDepartment(e.target.value)} placeholder="livestock, dairy…" />
      <Select id="emp-type" label="Employment type" value={employmentType} onChange={(e) => setEmploymentType(e.target.value)}>
        {EMPLOYMENT_TYPES.map((t) => (
          <option key={t} value={t}>{t.replace(/_/g, " ")}</option>
        ))}
      </Select>
      <Input id="emp-hire" label="Hire date" type="date" value={hireDate} onChange={(e) => setHireDate(e.target.value)} />
      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Creating…" : "Create employee"}
      </Button>
    </form>
  );
}
