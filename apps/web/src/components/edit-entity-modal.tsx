"use client";

import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button, ErrorState, Input, Modal, Select, Textarea } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import { buildPatch, EDIT_CONFIGS, toFormValues, type EditEntity, type EditField } from "@/lib/edit-configs";

/**
 * One edit form for every entity that supports PATCH (animals, crops, assets,
 * employees, suppliers). Driven by EDIT_CONFIGS, sends only the fields the user
 * actually changed, and refreshes the listed queries on success.
 */
export function EditEntityModal({
  entity,
  id,
  record,
  open,
  onClose,
  invalidate,
}: {
  entity: EditEntity;
  id: string;
  record: object;
  open: boolean;
  onClose: () => void;
  /** react-query keys to refresh after saving (the page's own queries). */
  invalidate: unknown[][];
}) {
  const config = EDIT_CONFIGS[entity];
  const fields: EditField[] = config.fields; // widen: each entity's list is narrowly typed by `satisfies`
  const queryClient = useQueryClient();
  const source = record as Record<string, unknown>;
  const [form, setForm] = useState(() => toFormValues(fields, source));
  const [error, setError] = useState<string | null>(null);

  // Start from the latest saved values every time the dialog is opened.
  useEffect(() => {
    if (open) {
      setForm(toFormValues(fields, source));
      setError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset only on open / when switching record
  }, [open, id]);

  const save = useMutation({
    mutationFn: (patch: Record<string, unknown>) => apiFetch(config.path(id), { method: "PATCH", body: JSON.stringify(patch) }),
    onSuccess: () => {
      invalidate.forEach((queryKey) => queryClient.invalidateQueries({ queryKey }));
      onClose();
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : `Couldn't save the ${config.noun}.`),
  });

  const submit = () => {
    const { patch, error: problem } = buildPatch(fields, toFormValues(fields, source), form);
    if (problem) return setError(problem);
    if (Object.keys(patch).length === 0) return onClose(); // nothing changed - don't send an empty PATCH
    setError(null);
    save.mutate(patch);
  };

  const set = (name: string, value: string | boolean) => setForm((f) => ({ ...f, [name]: value }));

  return (
    <Modal open={open} onClose={onClose} title={`Edit ${config.noun}`}>
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        {error && <ErrorState message={error} />}
        {fields.map((f) => {
          const id = `edit-${entity}-${f.name}`;
          const value = form[f.name];
          if (f.type === "checkbox") {
            return (
              <label key={f.name} className="flex cursor-pointer items-center gap-2 text-sm text-ink">
                <input type="checkbox" checked={Boolean(value)} onChange={(e) => set(f.name, e.target.checked)} className="h-4 w-4 accent-forest" />
                {f.label}
              </label>
            );
          }
          if (f.type === "select") {
            return (
              <Select key={f.name} id={id} label={f.label} value={String(value)} onChange={(e) => set(f.name, e.target.value)}>
                {f.options?.map((o) => (
                  <option key={o} value={o}>{o.replace(/_/g, " ")}</option>
                ))}
              </Select>
            );
          }
          if (f.type === "textarea") {
            return <Textarea key={f.name} id={id} label={f.label} rows={3} value={String(value)} onChange={(e) => set(f.name, e.target.value)} />;
          }
          return (
            <div key={f.name}>
              <Input
                id={id}
                label={f.label}
                type={f.type === "number" || f.type === "integer" ? "number" : f.type}
                step={f.type === "number" ? "any" : undefined}
                value={String(value)}
                onChange={(e) => set(f.name, e.target.value)}
              />
              {f.hint && <p className="mt-1 text-xs text-muted">{f.hint}</p>}
            </div>
          );
        })}
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={save.isPending}>{save.isPending ? "Saving…" : "Save changes"}</Button>
        </div>
      </form>
    </Modal>
  );
}
