"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Button, Input, Select, Textarea, Modal, ErrorState, EmptyState, StatusBadge } from "@/components/ui";
import { platformApiFetch, PlatformApiError } from "@/lib/platform-api";
import { editFieldsFor, singularLabel, type ModuleConfig, type ModuleField } from "@/lib/platform-modules";
import { buildPatch, toFormValues, type EditField } from "@/lib/edit-configs";

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
        <Modal open={createOpen} onClose={() => setCreateOpen(false)} title={`Create ${singularLabel(config)}`}>
          <GenericForm orgId={orgId} fields={config.fields} error={formError} pending={create.isPending} onSubmit={(body) => create.mutate(body)} />
        </Modal>
      )}
      <PlatformEditModal orgId={orgId} config={config} record={editingRow} onClose={() => setEditingRow(null)} onSaved={invalidate} />
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

/**
 * The superadmin's Edit modal for ONE record. Used by the module list and by detail pages (e.g. the animal page), so
 * every place offers exactly the same form - the tenant's edit fields plus the platform extras - and saves the same way.
 * Pass `record={null}` to keep it closed. Renders nothing for modules that can't be edited.
 */
export function PlatformEditModal({
  orgId, config, record, onClose, onSaved,
}: {
  orgId: string;
  config: ModuleConfig;
  record: Record<string, unknown> | null;
  onClose: () => void;
  /** Called after a successful save, before the modal closes - refresh whatever is showing this record. */
  onSaved?: () => void;
}) {
  if (!config.fields || !config.itemPath) return null;
  return (
    <Modal open={!!record} onClose={onClose} title={`Edit ${singularLabel(config)}`}>
      {/* the body mounts fresh on every open, so a previous error or half-typed value never leaks into the next edit */}
      {record && <PlatformEditBody orgId={orgId} config={config} record={record} onClose={onClose} onSaved={onSaved} />}
    </Modal>
  );
}

function PlatformEditBody({
  orgId, config, record, onClose, onSaved,
}: { orgId: string; config: ModuleConfig; record: Record<string, unknown>; onClose: () => void; onSaved?: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      platformApiFetch(config.itemPath!(orgId, String(record.id)), { method: "PATCH", body: JSON.stringify(body) }),
    onSuccess: () => { onSaved?.(); onClose(); },
    onError: (err) => setError(err instanceof PlatformApiError ? err.message : "Failed to save"),
  });
  return (
    <GenericForm
      orgId={orgId} fields={editFieldsFor(config)} error={error} pending={save.isPending} initial={record}
      onSubmit={(body) => save.mutate(body)} onClose={onClose}
    />
  );
}

/** The tenant's field vocabulary, so edits can reuse the tenant's own patch logic. A picker holds an id, i.e. text. */
function toEditField(f: ModuleField): EditField {
  const type: EditField["type"] =
    f.type === "boolean" ? "checkbox"
    : f.type === "select" || f.type === "textarea" || f.type === "number" || f.type === "integer" || f.type === "date" || f.type === "email" ? f.type
    : "text";
  return { name: f.name, label: f.label, type, options: f.options, required: f.required };
}

const optionLabel = (o: string) => o.replace(/_/g, " ");

function FieldHint({ hint }: { hint?: string }) {
  return hint ? <p className="mt-1 text-xs text-muted">{hint}</p> : null;
}

/**
 * Create and Edit share this form.
 *  - Create: blank optional fields are left out of the request.
 *  - Edit (when `initial` is given): behaves exactly like the tenant's edit screen - only fields that changed are
 *    sent, a blank clears an optional field, a required field can't be cleared, and numbers are validated. It uses
 *    the tenant's own buildPatch so the two can't behave differently.
 */
function GenericForm({
  orgId, fields, initial, error, pending, onSubmit, onClose,
}: {
  orgId: string;
  fields: ModuleField[];
  initial?: Record<string, unknown>;
  error: string | null;
  pending: boolean;
  onSubmit: (body: Record<string, unknown>) => void;
  /** Edit only: closes the modal (Cancel, and when nothing was changed). */
  onClose?: () => void;
}) {
  const editing = initial !== undefined;
  // Edit forms show the tenant's own inline messages ("Name can't be empty.") instead of the browser's generic
  // required-field bubble, so the superadmin sees exactly what a tenant sees. Create forms keep native validation.
  const editFields = fields.map(toEditField);
  const [initialValues] = useState(() => toFormValues(editFields, initial ?? {}));
  const [values, setValues] = useState<Record<string, string | boolean>>(initialValues);
  const [localError, setLocalError] = useState<string | null>(null);

  function set(name: string, value: string | boolean) {
    setValues((prev) => ({ ...prev, [name]: value }));
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        setLocalError(null);
        if (editing) {
          const { patch, error: invalid } = buildPatch(editFields, initialValues, values);
          if (invalid) { setLocalError(invalid); return; }
          if (Object.keys(patch).length === 0) { onClose ? onClose() : setLocalError("Nothing to save - no fields were changed."); return; }
          onSubmit(patch);
          return;
        }
        const body: Record<string, unknown> = {};
        for (const f of fields) {
          const v = values[f.name];
          if (v === "" || v === undefined) continue; // omit blanks rather than sending empty strings for optional fields
          body[f.name] = f.type === "number" || f.type === "integer" ? Number(v) : v;
        }
        onSubmit(body);
      }}
      className="space-y-3"
    >
      {(localError ?? error) && <ErrorState message={(localError ?? error) as string} />}
      {fields.map((f) => {
        const id = `field-${f.name}`;
        if (f.type === "farm_picker" || f.type === "location_picker" || f.type === "supplier_picker") {
          return (
            <div key={f.name}>
              <RelationPickerField id={id} orgId={orgId} field={f} value={String(values[f.name] ?? "")} onChange={(v) => set(f.name, v)} />
              <FieldHint hint={f.hint} />
            </div>
          );
        }
        if (f.type === "select") {
          // When editing, "Select…" is only offered if the value is already blank - like the tenant form, a value
          // that is set can be changed but not accidentally wiped to nothing.
          const blankAllowed = !editing || String(initialValues[f.name] ?? "") === "";
          return (
            <div key={f.name}>
              <Select id={id} label={f.label} required={!editing && f.required} value={String(values[f.name] ?? "")} onChange={(e) => set(f.name, e.target.value)}>
                {blankAllowed && <option value="">Select…</option>}
                {f.options?.map((o) => <option key={o} value={o}>{optionLabel(o)}</option>)}
              </Select>
              <FieldHint hint={f.hint} />
            </div>
          );
        }
        if (f.type === "textarea") {
          return (
            <div key={f.name}>
              <Textarea id={id} label={f.label} required={!editing && f.required} value={String(values[f.name] ?? "")} onChange={(e) => set(f.name, e.target.value)} />
              <FieldHint hint={f.hint} />
            </div>
          );
        }
        if (f.type === "boolean") {
          return (
            <div key={f.name}>
              <label className="flex items-center gap-2 text-sm text-ink">
                <input type="checkbox" checked={Boolean(values[f.name])} onChange={(e) => set(f.name, e.target.checked)} />
                {f.label}
              </label>
              <FieldHint hint={f.hint} />
            </div>
          );
        }
        return (
          <div key={f.name}>
            <Input
              id={id} label={f.label} required={!editing && f.required}
              type={f.type === "number" || f.type === "integer" ? "number" : f.type === "date" ? "date" : f.type === "email" ? "email" : "text"}
              step={f.type === "integer" ? 1 : f.type === "number" ? "any" : undefined}
              value={String(values[f.name] ?? "")} onChange={(e) => set(f.name, e.target.value)}
            />
            <FieldHint hint={f.hint} />
          </div>
        );
      })}
      {editing ? (
        <div className="flex justify-end gap-2 pt-1">
          {onClose && <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>}
          <Button type="submit" disabled={pending}>{pending ? "Saving…" : "Save changes"}</Button>
        </div>
      ) : (
        <Button type="submit" disabled={pending} className="w-full">
          {pending ? "Saving…" : "Save"}
        </Button>
      )}
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
