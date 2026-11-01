"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { Card, Button, Input, ErrorState, StatusBadge } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import type { OrganizationSettings } from "@/lib/types";

interface EmailOutboxEntry {
  id: string;
  to_email: string;
  subject: string;
  provider: string;
  accepted: boolean;
  sent_at: string;
}

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<Partial<OrganizationSettings>>({});
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const { data, isLoading, error: loadError } = useQuery<OrganizationSettings>({
    queryKey: ["organization-settings"],
    queryFn: () => apiFetch<OrganizationSettings>("/api/v1/organization/settings"),
  });

  useEffect(() => {
    if (data) setForm(data);
  }, [data]);

  const outboxQuery = useQuery<EmailOutboxEntry[]>({
    queryKey: ["email-outbox"],
    queryFn: () => apiFetch<EmailOutboxEntry[]>("/api/v1/notifications/email-outbox"),
  });

  const save = useMutation({
    mutationFn: () =>
      apiFetch("/api/v1/organization/settings", {
        method: "PATCH",
        body: JSON.stringify({
          currency: form.currency, timezone: form.timezone,
          invoice_prefix: form.invoice_prefix, po_prefix: form.po_prefix,
          employee_prefix: form.employee_prefix, asset_prefix: form.asset_prefix,
          tax_rate: form.tax_rate, default_weight_unit: form.default_weight_unit,
          default_volume_unit: form.default_volume_unit,
        }),
      }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["organization-settings"], updated);
      setError(null);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Failed to save settings"),
  });

  return (
    <AdminShell>
      <div className="mb-6">
        <h1 className="font-display text-2xl text-forest">Organization settings</h1>
        <p className="text-sm text-muted">Currency, timezone, document numbering, tax rate, and default units.</p>
         <Link href="/admin/settings/domain" className="mt-1 inline-block text-sm text-forest hover:underline">
          Custom domain →
        </Link>
      </div>

      {loadError && <ErrorState message={loadError instanceof ApiError ? loadError.message : "Failed to load settings"} />}
      {isLoading && <p className="text-sm text-muted">Loading…</p>}

      {data && (
        <Card className="max-w-xl">
          <form
            onSubmit={(e) => { e.preventDefault(); save.mutate(); }}
            className="space-y-4"
          >
            {error && <ErrorState message={error} />}
            {saved && <p className="text-sm text-moss">Settings saved.</p>}

            <div className="grid grid-cols-2 gap-4">
              <Input
                label="Currency" value={form.currency ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, currency: e.target.value }))}
              />
              <Input
                label="Timezone" value={form.timezone ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, timezone: e.target.value }))}
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <Input
                label="Invoice number prefix" value={form.invoice_prefix ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, invoice_prefix: e.target.value }))}
              />
              <Input
                label="Purchase order prefix" value={form.po_prefix ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, po_prefix: e.target.value }))}
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <Input
                label="Employee number prefix" value={form.employee_prefix ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, employee_prefix: e.target.value }))}
              />
              <Input
                label="Asset number prefix" value={form.asset_prefix ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, asset_prefix: e.target.value }))}
              />
            </div>

            <Input
              label="Tax rate (%)" type="number" min="0" max="100" step="0.01"
              value={form.tax_rate ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, tax_rate: e.target.value }))}
            />
            <p className="-mt-2 text-xs text-muted">Applied to every new invoice's subtotal - existing invoices are never recalculated.</p>

            <div className="grid grid-cols-2 gap-4">
              <Input
                label="Default weight unit" value={form.default_weight_unit ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, default_weight_unit: e.target.value }))}
              />
              <Input
                label="Default volume unit" value={form.default_volume_unit ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, default_volume_unit: e.target.value }))}
              />
            </div>

            <Button type="submit" disabled={save.isPending} className="w-full">
              {save.isPending ? "Saving…" : "Save settings"}
            </Button>
          </form>
        </Card>
      )}

      <div className="mt-8">
        <h2 className="mb-3 font-display text-lg text-forest">Email send log</h2>
        <p className="mb-3 text-sm text-muted">
          Every email this system has attempted to send - password resets, order confirmations -
          regardless of which provider handled it.
        </p>
        {outboxQuery.error && (
          <ErrorState message={outboxQuery.error instanceof ApiError ? outboxQuery.error.message : "Failed to load email log"} />
        )}
        {outboxQuery.data && outboxQuery.data.length === 0 && (
          <p className="text-sm text-muted">No emails sent yet.</p>
        )}
        {outboxQuery.data && outboxQuery.data.length > 0 && (
          <div className="overflow-hidden rounded-lg border border-hairline">
            <table className="w-full text-left text-sm">
              <thead className="bg-forest text-paper">
                <tr>
                  <th className="px-4 py-3 font-medium">To</th>
                  <th className="px-4 py-3 font-medium">Subject</th>
                  <th className="px-4 py-3 font-medium">Provider</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Sent</th>
                </tr>
              </thead>
              <tbody>
                {outboxQuery.data.map((e, i) => (
                  <tr key={e.id} className={i % 2 === 0 ? "bg-white/40" : "bg-white/70"}>
                    <td className="px-4 py-3 text-ink">{e.to_email}</td>
                    <td className="px-4 py-3 text-muted">{e.subject}</td>
                    <td className="px-4 py-3 uppercase text-muted">{e.provider}</td>
                    <td className="px-4 py-3"><StatusBadge status={e.accepted ? "sent" : "failed"} /></td>
                    <td className="px-4 py-3 text-muted">{new Date(e.sent_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </AdminShell>
  );
}
