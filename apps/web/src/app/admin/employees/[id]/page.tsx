"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { Card, StatusBadge, ErrorState, Button, Input } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import type { EmployeeDetail, WorkShift } from "@/lib/types";

const STATUS_TRANSITIONS: Record<string, string[]> = {
  active: ["on_leave", "suspended", "terminated"],
  on_leave: ["active", "terminated"],
  suspended: ["active", "terminated"],
  terminated: [],
};

export default function EmployeeDetailPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [statusError, setStatusError] = useState<string | null>(null);
  const [shiftDate, setShiftDate] = useState("");
  const [startTime, setStartTime] = useState("");
  const [endTime, setEndTime] = useState("");
  const [shiftError, setShiftError] = useState<string | null>(null);

  const employeeQuery = useQuery<EmployeeDetail>({
    queryKey: ["employee", id],
    queryFn: () => apiFetch<EmployeeDetail>(`/api/v1/employees/${id}`),
  });
  const shiftsQuery = useQuery<WorkShift[]>({
    queryKey: ["employee-shifts", id],
    queryFn: () => apiFetch<WorkShift[]>(`/api/v1/employees/${id}/shifts`),
  });

  const changeStatus = useMutation({
    mutationFn: (status: string) =>
      apiFetch(`/api/v1/employees/${id}/status`, { method: "PATCH", body: JSON.stringify({ status }) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["employee", id] });
      queryClient.invalidateQueries({ queryKey: ["employees"] });
      setStatusError(null);
    },
    onError: (err) => setStatusError(err instanceof ApiError ? err.message : "Failed to change status"),
  });

  const addShift = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/employees/${id}/shifts`, {
        method: "POST",
        body: JSON.stringify({
          shift_date: shiftDate,
          start_time: startTime || undefined,
          end_time: endTime || undefined,
        }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["employee-shifts", id] });
      setShiftDate("");
      setStartTime("");
      setEndTime("");
      setShiftError(null);
    },
    onError: (err) => setShiftError(err instanceof ApiError ? err.message : "Failed to add shift"),
  });

  if (employeeQuery.error) {
    return (
      <AdminShell>
        <ErrorState message={employeeQuery.error instanceof ApiError ? employeeQuery.error.message : "Failed to load employee"} />
      </AdminShell>
    );
  }
  if (!employeeQuery.data) {
    return (
      <AdminShell>
        <p className="text-sm text-muted">Loading…</p>
      </AdminShell>
    );
  }

  const employee = employeeQuery.data;
  const nextStatuses = STATUS_TRANSITIONS[employee.employment_status] ?? [];

  return (
    <AdminShell>
      <div className="mb-6 flex items-start justify-between">
        <div>
          <div className="mb-2"><StatusBadge status={employee.employment_status} /></div>
          <h1 className="font-display text-2xl text-forest">{employee.full_name}</h1>
          <p className="text-sm text-muted">
            {employee.employee_number} · {employee.job_title ?? "No title"} · {employee.department ?? "No department"}
          </p>
        </div>
      </div>

      {nextStatuses.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <span className="text-xs uppercase tracking-wider text-muted">Change status:</span>
          {nextStatuses.map((next) => (
            <Button
              key={next}
              variant="ghost"
              className="px-3 py-1 text-xs capitalize"
              disabled={changeStatus.isPending}
              onClick={() => changeStatus.mutate(next)}
            >
              → {next.replace(/_/g, " ")}
            </Button>
          ))}
        </div>
      )}
      {statusError && <div className="mb-4"><ErrorState message={statusError} /></div>}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card>
          <h2 className="mb-3 font-display text-lg text-forest">Status history</h2>
          {employee.status_history.length === 0 ? (
            <p className="text-sm text-muted">No status changes yet.</p>
          ) : (
            <ol className="relative space-y-4 border-l border-hairline pl-6">
              {employee.status_history.map((event, i) => (
                <li key={i} className="relative">
                  <span className="absolute -left-[27px] top-1 h-2.5 w-2.5 rounded-full bg-brass" />
                  <p className="text-sm font-medium capitalize text-ink">
                    {event.from_status ? `${event.from_status.replace(/_/g, " ")} → ` : ""}
                    {event.to_status.replace(/_/g, " ")}
                  </p>
                  <p className="text-xs text-muted">{new Date(event.changed_at).toLocaleString()}</p>
                  {event.reason && <p className="text-xs text-muted">{event.reason}</p>}
                </li>
              ))}
            </ol>
          )}
        </Card>

        <Card>
          <h2 className="mb-3 font-display text-lg text-forest">Work shifts</h2>
          {shiftError && <div className="mb-2"><ErrorState message={shiftError} /></div>}
          <form
            onSubmit={(e) => { e.preventDefault(); addShift.mutate(); }}
            className="mb-4 grid grid-cols-3 gap-2"
          >
            <Input type="date" required value={shiftDate} onChange={(e) => setShiftDate(e.target.value)} />
            <Input type="time" value={startTime} onChange={(e) => setStartTime(e.target.value)} />
            <Input type="time" value={endTime} onChange={(e) => setEndTime(e.target.value)} />
            <Button type="submit" disabled={addShift.isPending} className="col-span-3 text-xs">
              {addShift.isPending ? "Adding…" : "+ Add shift"}
            </Button>
          </form>
          {shiftsQuery.data && shiftsQuery.data.length === 0 && (
            <p className="text-sm text-muted">No shifts scheduled yet.</p>
          )}
          {shiftsQuery.data && shiftsQuery.data.length > 0 && (
            <ul className="space-y-2 text-sm">
              {shiftsQuery.data.map((s) => (
                <li key={s.id} className="flex justify-between border-b border-hairline/60 pb-2">
                  <span className="text-ink">{s.shift_date}</span>
                  <span className="text-muted">{s.start_time ?? "-"}{s.end_time ? ` – ${s.end_time}` : ""}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </AdminShell>
  );
}
