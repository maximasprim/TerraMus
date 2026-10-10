"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Button, Input, Select, Textarea, Modal, ErrorState, EmptyState, StatusBadge } from "@/components/ui";
import { platformApiFetch, PlatformApiError } from "@/lib/platform-api";
import type { ModuleConfig, ModuleField } from "@/lib/platform-modules";

function formatCell(value: unknown, format?: string): React.ReactNode {
  if (value === null || value === undefined || value === "") return <span className="text-muted">-</span>;
  if (format === "badge") return <StatusBadge status={String(value)} />;
  if (format === "shortid") return <span className="font-mono text-xs">{String(value).slice(0, 8).toUpperCase()}</span>;
  if (format === "date") return new Date(String(value)).toLocaleDateString();
  if (format === "currency") return `KES ${Number(value).toLocaleString()}`;
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "object") return <span className="font-mono text-xs">{JSON.stringify(value)}</span>;
  return String(value);
}

export function PlatformResourceBrowser({ orgId, config, canWrite }: { orgId: string; config: ModuleConfig; canWrite: boolean }) {
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [editingRow, setEditingRow] = useState<Record<string, unknown> | null>(null);
  const [statusRow, setStatusRow] = useState<Record<string, unknown> | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  const listQuery = useQuery<Record<string, unknown>[]>({
    queryKey: ["platform-resource", config.slug, orgId],
    queryFn: () => platformApiFetch<Record<string, unknown>[]>(config.listPath(orgId)),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["platform-resource", config.slug, orgId] });

  const create = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      platformApiFetch(config.createPath!(orgId), { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => { invalidate(); setCreateOpen(false); setFormError(null); },
    onError: (err) => setFormError(err instanceof PlatformApiError ? err.message : "Failed to create"),
  });

  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) =>
      platformApiFetch(config.itemPath!(orgId, id), { method: "PATCH", body: JSON.stringify(body) }),
    onSuccess: () => { invalidate(); setEditingRow(null); setFormError(null); },
    onError: (err) => setFormError(err instanceof PlatformApiError ? err.message : "Failed to save"),
  });

  const changeStatus = useMutation({
    mutationFn: ({ id, value }: { id: string; value: string }) =>
      platformApiFetch(config.statusAction!.path(orgId, id), {
        method: config.statusAction!.method ?? "PATCH", body: JSON.stringify({ [config.statusAction!.field]: value }),
      }),
    onSuccess: () => { invalidate(); setStatusRow(null); setFormError(null); },
    onError: (err) => setFormError(err instanceof PlatformApiError ? err.message : "Failed to change status"),
  });

  const runSimpleAction = useMutation({
    mutationFn: (id: string) => platformApiFetch(config.simpleAction!.path(orgId, id), { method: "POST" }),
    onSuccess: () => invalidate(),
    onError: (err) => setFormError(err instanceof PlatformApiError ? err.message : "Action failed"),
  });

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <p className="text-sm text-muted">
          {listQuery.data ? `${listQuery.data.length} record${listQuery.data.length === 1 ? "" : "s"}` : "Loading…"}
        </p>
        {canWrite && config.fields && config.createPath && (
          <Button onClick={() => { setFormError(null); setCreateOpen(true); }}>+ Create</Button>
        )}
      </div>

      {listQuery.error && (
        <ErrorState message={listQuery.error instanceof PlatformApiError ? listQuery.error.message : "Failed to load"} />
      )}
      {listQuery.data && listQuery.data.length === 0 && (
        <EmptyState title={`No ${config.label.toLowerCase()} yet`} body="Nothing here for this organization." />
      )}
      {listQuery.data && listQuery.data.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-hairline">
          <table className="w-full text-left text-sm">
            <thead className="bg-ink text-paper">
              <tr>
                {config.columns.map((c) => <th key={c.key} className="px-4 py-3 font-medium">{c.label}</th>)}
                {canWrite && (config.itemPath || config.statusAction || config.simpleAction) && <th className="px-4 py-3 font-medium" />}
              </tr>
            </thead>
            <tbody>
              {listQuery.data.map((row, i) => (
                <tr key={String(row.id ?? i)} className={i % 2 === 0 ? "bg-white/40" : "bg-white/70"}>
                  {config.columns.map((c, ci) => (
                    <td key={c.key} className="px-4 py-3 text-ink">
                      {ci === 0 && config.rowHref ? (
                        <a href={config.rowHref(orgId, String(row.id))} className="font-medium text-forest hover:underline">
                          {formatCell(row[c.key], c.format)}
                        </a>
                      ) : (
                        formatCell(row[c.key], c.format)
                      )}
                    </td>
                  ))}
                  {canWrite && (config.itemPath || config.statusAction || config.simpleAction) && (
                    <td className="px-4 py-3 text-right space-x-2">
                      {config.fields && config.itemPath && (
                        <Button variant="ghost" className="text-xs" onClick={() => { setFormError(null); setEditingRow(row); }}>
                          Edit
                        </Button>
                      )}
                      {config.statusAction && (
                        <Button variant="ghost" className="text-xs" onClick={() => { setFormError(null); setStatusRow(row); }}>
                          {config.statusAction.label}
                        </Button>
                      )}
                      {config.simpleAction && (
                        <Button
                          variant="ghost" className="text-xs" disabled={runSimpleAction.isPending}
                          onClick={() => {
                            if (window.confirm(config.simpleAction!.confirmText)) runSimpleAction.mutate(String(row.id));
                          }}
                        >
                          {config.simpleAction.label}
                        </Button>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {config.fields && (
        <Modal open={createOpen} onClose={() => setCreateOpen(false)} title={`Create ${config.label.slice(0, -1) || config.label}`}>
          <GenericForm orgId={orgId} fields={config.fields} error={formError} pending={create.isPending} onSubmit={(body) => create.mutate(body)} />
        </Modal>
      )}
      {config.fields && config.itemPath && (
        <Modal open={!!editingRow} onClose={() => setEditingRow(null)} title={`Edit ${config.label.slice(0, -1) || config.label}`}>
          {editingRow && (
            <GenericForm
              orgId={orgId} fields={[...config.fields.filter((f) => !f.createOnly), ...(config.editExtraFields ?? [])]} error={formError} pending={update.isPending} initial={editingRow}
              onSubmit={(body) => update.mutate({ id: String(editingRow.id), body })}
            />
          )}
        </Modal>
      )}
      {config.statusAction && (
        <Modal open={!!statusRow} onClose={() => setStatusRow(null)} title={config.statusAction.label}>
          {statusRow && (
            <StatusForm
              currentValue={String(statusRow[config.statusAction.field] ?? "")}
              options={config.statusAction.options}
              error={formError} pending={changeStatus.isPending}
              onSubmit={(value) => changeStatus.mutate({ id: String(statusRow.id), value })}
            />
          )}
        </Modal>
      )}
    </div>
  );
}

/** Builds a plain form from a field list - text/number/date/boolean/select/
 * textarea inputs, no per-module hand-written form code. Relational fields
 * (farm_id, supplier_id, etc.) render as plain text inputs for the admin to
 * paste a UUID into - see platform-modules.ts's module docstring for why
 * that's an intentional simplification here rather than a proper picker. */
function GenericForm({
  orgId, fields, initial, error, pending, onSubmit,
}: {
  orgId: string;
  fields: ModuleField[];
  initial?: Record<string, unknown>;
  error: string | null;
  pending: boolean;
  onSubmit: (body: Record<string, unknown>) => void;
}) {
  const [values, setValues] = useState<Record<string, string | boolean>>(() => {
    const v: Record<string, string | boolean> = {};
    for (const f of fields) {
      const existing = initial?.[f.name];
      v[f.name] = f.type === "boolean" ? Boolean(existing) : existing !== undefined && existing !== null ? String(existing) : "";
    }
    return v;
  });

  function set(name: string, value: string | boolean) {
    setValues((prev) => ({ ...prev, [name]: value }));
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        const body: Record<string, unknown> = {};
        for (const f of fields) {
          const v = values[f.name];
          if (v === "" || v === undefined) continue; // omit blanks rather than sending empty strings for optional fields
          body[f.name] = f.type === "number" ? Number(v) : v;
        }
        onSubmit(body);
      }}
      className="space-y-3"
    >
      {error && <ErrorState message={error} />}
      {fields.map((f) => {
        const id = `field-${f.name}`;
        if (f.type === "farm_picker" || f.type === "location_picker" || f.type === "supplier_picker") {
          return (
            <RelationPickerField
              key={f.name} id={id} orgId={orgId} field={f}
              value={String(values[f.name] ?? "")} onChange={(v) => set(f.name, v)}
            />
          );
        }
        if (f.type === "select") {
          return (
            <Select key={f.name} id={id} label={f.label} required={f.required} value={String(values[f.name] ?? "")} onChange={(e) => set(f.name, e.target.value)}>
              <option value="">Select…</option>
              {f.options?.map((o) => <option key={o} value={o}>{o}</option>)}
            </Select>
          );
        }
        if (f.type === "textarea") {
          return (
            <Textarea key={f.name} id={id} label={f.label} required={f.required} value={String(values[f.name] ?? "")} onChange={(e) => set(f.name, e.target.value)} />
          );
        }
        if (f.type === "boolean") {
          return (
            <label key={f.name} className="flex items-center gap-2 text-sm text-ink">
              <input type="checkbox" checked={Boolean(values[f.name])} onChange={(e) => set(f.name, e.target.checked)} />
              {f.label}
            </label>
          );
        }
        return (
          <Input
            key={f.name} id={id} label={f.label} required={f.required}
            type={f.type === "number" ? "number" : f.type === "date" ? "date" : "text"}
            placeholder={f.hint}
            value={String(values[f.name] ?? "")} onChange={(e) => set(f.name, e.target.value)}
          />
        );
      })}
      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Saving…" : "Save"}
      </Button>
    </form>
  );
}

interface FarmWithBranches {
  id: string;
  name: string;
  branches: { id: string; name: string; locations: { id: string; name: string }[] }[];
}

/** Backs farm_picker / location_picker / supplier_picker field types.
 * Farms come back nested (farm -> branches -> locations, matching
 * GET /api/v1/farms's own shape) from the new
 * GET .../organizations/{org_id}/farms endpoint - locations are flattened
 * into "Branch - Location" option labels here since that's the only level
 * an asset/employee actually assigns to. Suppliers reuse this module's own
 * list endpoint (the "suppliers" ModuleConfig's listPath) rather than a
 * separate lookup. */
function RelationPickerField({
  id, orgId, field, value, onChange,
}: {
  id: string;
  orgId: string;
  field: ModuleField;
  value: string;
  onChange: (value: string) => void;
}) {
  const farmsQuery = useQuery<FarmWithBranches[]>({
    queryKey: ["platform-farms", orgId],
    queryFn: () => platformApiFetch<FarmWithBranches[]>(`/api/v1/platform/organizations/${orgId}/farms`),
    enabled: field.type === "farm_picker" || field.type === "location_picker",
  });

  const suppliersQuery = useQuery<Record<string, unknown>[]>({
    queryKey: ["platform-resource", "suppliers", orgId],
    queryFn: () => platformApiFetch<Record<string, unknown>[]>(`/api/v1/platform/organizations/${orgId}/procurement/suppliers`),
    enabled: field.type === "supplier_picker",
  });

  if (field.type === "farm_picker") {
    return (
      <Select id={id} label={field.label} required={field.required} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{farmsQuery.isLoading ? "Loading farms…" : "Select a farm…"}</option>
        {(farmsQuery.data ?? []).map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
      </Select>
    );
  }

  if (field.type === "location_picker") {
    const options = (farmsQuery.data ?? []).flatMap((f) =>
      f.branches.flatMap((b) => b.locations.map((l) => ({ id: l.id, label: `${f.name} / ${b.name} - ${l.name}` }))),
    );
    return (
      <Select id={id} label={field.label} required={field.required} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{farmsQuery.isLoading ? "Loading locations…" : "Select a location…"}</option>
        {options.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
      </Select>
    );
  }

  // supplier_picker
  return (
    <Select id={id} label={field.label} required={field.required} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">{suppliersQuery.isLoading ? "Loading suppliers…" : "Select a supplier…"}</option>
      {(suppliersQuery.data ?? []).map((s) => <option key={String(s.id)} value={String(s.id)}>{String(s.name)}</option>)}
    </Select>
  );
}

function StatusForm({
  currentValue, options, error, pending, onSubmit,
}: {
  currentValue: string;
  options: string[];
  error: string | null;
  pending: boolean;
  onSubmit: (value: string) => void;
}) {
  const [value, setValue] = useState(currentValue || options[0]);
  return (
    <form onSubmit={(e) => { e.preventDefault(); onSubmit(value); }} className="space-y-3">
      {error && <ErrorState message={error} />}
      <Select id="status-value" label="New status" value={value} onChange={(e) => setValue(e.target.value)}>
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
      </Select>
      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Saving…" : "Save"}
      </Button>
    </form>
  );
}
