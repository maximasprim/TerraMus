"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { Card, EmptyState, ErrorState } from "@/components/ui";
import { apiFetchAll, ApiError } from "@/lib/api";
import type { AuditLogEntry } from "@/lib/types";

/** The API pages 100 at a time; 10 pages = the latest 1,000 entries. */
const PAGE_SIZE = 100;
const MAX_PAGES = 10;

const human = (s: string) => s.replace(/[._]/g, " ");
const show = (v: unknown) => {
  const text = typeof v === "string" ? v : JSON.stringify(v);
  return text.length > 90 ? `${text.slice(0, 90)}…` : text;
};

/** "field: before → after" lines for the keys that differ (or only new values for creations). */
function changes(entry: AuditLogEntry): { key: string; before?: string; after?: string }[] {
  const before = entry.previous_value ?? {};
  const after = entry.new_value ?? {};
  return [...new Set([...Object.keys(before), ...Object.keys(after)])]
    .filter((key) => JSON.stringify(before[key]) !== JSON.stringify(after[key]))
    .map((key) => ({
      key,
      before: key in before ? show(before[key]) : undefined,
      after: key in after ? show(after[key]) : undefined,
    }));
}

export default function AuditLogPage() {
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState<string | null>(null);

  const logs = useQuery<AuditLogEntry[]>({
    queryKey: ["audit-logs"],
    queryFn: () => apiFetchAll<AuditLogEntry>("/api/v1/audit-logs", { style: "offset", pageSize: PAGE_SIZE, maxPages: MAX_PAGES }),
  });

  const rows = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return logs.data ?? [];
    return (logs.data ?? []).filter((e) =>
      [e.action, e.entity_type, e.user_name ?? "system platform", e.entity_id ?? ""].join(" ").toLowerCase().replace(/[._]/g, " ").includes(needle),
    );
  }, [logs.data, search]);

  return (
    <AdminShell>
      <div className="mb-6">
        <h1 className="font-display text-2xl text-forest">Audit log</h1>
        <p className="text-sm text-muted">A record of who changed what, and when. Newest first.</p>
      </div>

      <input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Filter by person, action or record type…"
        aria-label="Filter the audit log"
        className="mb-4 w-full max-w-md rounded-md border border-hairline bg-white px-3 py-2 text-sm"
      />

      {logs.error && <ErrorState message={logs.error instanceof ApiError ? logs.error.message : "Failed to load the audit log"} />}
      {logs.isLoading && <p className="text-sm text-muted">Loading…</p>}
      {logs.data && logs.data.length === 0 && <EmptyState title="No activity recorded yet" body="Changes to users, roles, livestock and crops will appear here." />}
      {logs.data && logs.data.length > 0 && rows.length === 0 && <p className="text-sm text-muted">Nothing matches &ldquo;{search}&rdquo;.</p>}

      {rows.length > 0 && (
        <Card className="overflow-x-auto p-0">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-hairline text-xs uppercase tracking-wider text-muted">
              <tr>
                <th className="px-4 py-3">When</th>
                <th className="px-4 py-3">Who</th>
                <th className="px-4 py-3">What</th>
                <th className="px-4 py-3">Record</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {rows.map((e) => {
                const diff = changes(e);
                const expanded = open === e.id;
                return (
                  <tr key={e.id} className="border-b border-hairline/60 align-top last:border-0">
                    <td className="whitespace-nowrap px-4 py-3 text-muted">{new Date(e.created_at).toLocaleString()}</td>
                    <td className="px-4 py-3">{e.user_name ?? <span className="text-muted">System / platform support</span>}</td>
                    <td className="px-4 py-3 capitalize">{human(e.action)}</td>
                    <td className="px-4 py-3">
                      <span className="capitalize">{human(e.entity_type)}</span>
                      {e.entity_id && <span className="ml-1 font-mono text-xs text-muted">{e.entity_id.slice(0, 8)}</span>}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {diff.length > 0 && (
                        <button type="button" onClick={() => setOpen(expanded ? null : e.id)} className="text-xs text-forest underline underline-offset-4">
                          {expanded ? "Hide" : "Details"}
                        </button>
                      )}
                      {expanded && (
                        <ul className="mt-2 space-y-1 text-left text-xs">
                          {diff.map((d) => (
                            <li key={d.key}>
                              <span className="font-medium text-ink">{human(d.key)}:</span>{" "}
                              {d.before !== undefined && <span className="text-clay line-through">{d.before}</span>}
                              {d.before !== undefined && d.after !== undefined && " → "}
                              {d.after !== undefined && <span className="text-forest">{d.after}</span>}
                            </li>
                          ))}
                        </ul>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      )}
      {logs.data && logs.data.length >= PAGE_SIZE * MAX_PAGES && (
        <p className="mt-3 text-xs text-muted">Showing the latest {(PAGE_SIZE * MAX_PAGES).toLocaleString()} entries.</p>
      )}
    </AdminShell>
  );
}
