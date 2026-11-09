"use client";

import { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, Button, Input, Modal, ErrorState, TagChip } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import { SECTION_PERMISSIONS } from "@/lib/permissions";
import { useCatalog } from "@/lib/use-catalog";
import type { RoleDetail, RoleCatalog } from "@/lib/types";

/** Sidebar names, for the "pages this role can open" list. */
const SECTION_LABELS: Record<string, string> = {
  "/admin/dashboard": "Dashboard", "/admin/livestock": "Livestock", "/admin/cycles": "Production Cycles",
  "/admin/feedlot": "Feedlot", "/admin/weights": "Weights", "/admin/groups": "Flocks & Fish", "/admin/fodder": "Fodder", "/admin/crops": "Crops",
  "/admin/listings": "Listings", "/admin/reservations": "Reservations", "/admin/inventory": "Inventory",
  "/admin/procurement": "Procurement", "/admin/finance": "Finance", "/admin/receivables": "Receivables",
  "/admin/billing": "Billing", "/admin/farms": "Farms", "/admin/employees": "Employees", "/admin/assets": "Assets",
  "/admin/fuel": "Fuel", "/admin/customers": "Customers", "/admin/training": "Training", "/admin/orders": "Orders",
  "/admin/inquiries": "Inquiries", "/admin/cms": "Site Content", "/admin/reviews": "Reviews", "/admin/audit": "Audit log",
  "/admin/users": "Team", "/admin/search": "Search", "/admin/settings": "Settings", "/admin/reports": "Reports",
  "/admin/notifications": "Notifications",
};

/** Permission group for the on/off switches of the tabs on an animal's page (identity/permissions.py). */
const TAB_GROUP = "animaltabs";
/** Switches that show things rather than allow actions: a new role starts with all of them on. */
const isVisibilityCode = (code: string) => code === "notifications.view" || code.startsWith(`${TAB_GROUP}.`);

/** Pages grouped by the permission that opens them (pages sharing a permission switch together). */
function pageGroups(): { permission: string; prefixes: string[] }[] {
  const byPerm = new Map<string, string[]>();
  for (const s of SECTION_PERMISSIONS) {
    if (!s.permission || s.prefix.split("/").length !== 3 || !SECTION_LABELS[s.prefix]) continue;
    byPerm.set(s.permission, [...(byPerm.get(s.permission) ?? []), s.prefix]);
  }
  return Array.from(byPerm, ([permission, prefixes]) => ({ permission, prefixes }));
}

export function RolesPanel() {
  const qc = useQueryClient();
  const [editing, setEditing] = useState<RoleDetail | "new" | null>(null);

  const rolesQ = useQuery<RoleDetail[]>({ queryKey: ["role-details"], queryFn: () => apiFetch<RoleDetail[]>("/api/v1/roles") });
  const catalogQ = useQuery<RoleCatalog>({ queryKey: ["role-catalog"], queryFn: () => apiFetch<RoleCatalog>("/api/v1/roles/catalog") });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["role-details"] });
    qc.invalidateQueries({ queryKey: ["roles"] });
    qc.invalidateQueries({ queryKey: ["users"] });
    qc.invalidateQueries({ queryKey: ["me"] });
  };

  return (
    <div>
      <div className="mb-4 flex items-center justify-between gap-3">
        <p className="text-sm text-muted">
          Choose what each role can open and do. Changes apply to everyone with that role straight away.
        </p>
        <Button onClick={() => setEditing("new")}>+ New role</Button>
      </div>

      {rolesQ.error && <ErrorState message={rolesQ.error instanceof ApiError ? rolesQ.error.message : "Failed to load roles"} />}
      <div className="grid gap-3 md:grid-cols-2">
        {(rolesQ.data ?? []).map((r) => (
          <Card key={r.id} className="p-4">
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="font-medium text-ink">{r.name}</p>
                <p className="text-xs text-muted">
                  {r.user_count} {r.user_count === 1 ? "person" : "people"} · {r.permissions.length} permissions
                  {r.differs_from_default && " · customised"}
                </p>
              </div>
              {r.locked ? (
                <TagChip>Locked</TagChip>
              ) : (
                <Button variant="ghost" className="text-xs" onClick={() => setEditing(r)}>Edit access</Button>
              )}
            </div>
            {r.description && <p className="mt-2 text-xs text-muted">{r.description}</p>}
            {r.locked && (
              <p className="mt-2 text-xs text-muted">
                {r.name === "Farm Owner" ? "Always has full access so the farm can never be locked out." : "Storefront customers; managed automatically."}
              </p>
            )}
          </Card>
        ))}
      </div>

      <Modal open={editing !== null} onClose={() => setEditing(null)} title={editing === "new" ? "New role" : `Access for ${editing?.name ?? ""}`} size="lg">
        {editing !== null && catalogQ.data && (
          <RoleEditor
            key={editing === "new" ? "new" : editing.id}
            role={editing === "new" ? null : editing}
            catalog={catalogQ.data}
            onDone={() => { setEditing(null); refresh(); }}
          />
        )}
        {editing !== null && !catalogQ.data && <p className="text-sm text-muted">Loading…</p>}
      </Modal>
    </div>
  );
}

function RoleEditor({ role, catalog, onDone }: { role: RoleDetail | null; catalog: RoleCatalog; onDone: () => void }) {
  const [name, setName] = useState(role?.name ?? "");
  const [description, setDescription] = useState(role?.description ?? "");
  // A brand-new role starts with every "show this" switch on (those the creator may grant), so it sees everything
  // until the owner unticks something; the owner then adds what it can DO.
  const [selected, setSelected] = useState<Set<string>>(
    new Set(role ? role.permissions : catalog.can_grant.filter(isVisibilityCode)),
  );
  const [error, setError] = useState<string | null>(null);
  const { data: tenantCatalog } = useCatalog();
  const hidden = tenantCatalog?.hidden_menus ?? [];

  const grantable = useMemo(() => new Set(catalog.can_grant), [catalog]);
  const groups = useMemo(pageGroups, []);
  const gateCodes = useMemo(() => new Set(groups.map((g) => g.permission)), [groups]);
  const tabSwitches = useMemo(() => catalog.permissions.filter((p) => p.group === TAB_GROUP), [catalog]);
  const byGroup = useMemo(() => {
    const m = new Map<string, { code: string; description: string }[]>();
    for (const p of catalog.permissions) {
      if (gateCodes.has(p.code) || p.group === TAB_GROUP) continue;
      m.set(p.group_label, [...(m.get(p.group_label) ?? []), p]);
    }
    return Array.from(m);
  }, [catalog, gateCodes]);

  const toggle = (code: string) =>
    setSelected((prev) => { const n = new Set(prev); n.has(code) ? n.delete(code) : n.add(code); return n; });
  // you can switch on only what you hold yourself; anything already on can always be switched off
  const disabled = (code: string) => !selected.has(code) && !grantable.has(code);

  const save = useMutation({
    mutationFn: () => {
      const body = { name: name.trim(), description: description.trim(), permissions: Array.from(selected) };
      return role
        ? apiFetch(`/api/v1/roles/${role.id}`, { method: "PUT", body: JSON.stringify(role.is_system ? { permissions: body.permissions } : body) })
        : apiFetch("/api/v1/roles", { method: "POST", body: JSON.stringify(body) });
    },
    onSuccess: onDone,
    onError: (e) => setError(e instanceof ApiError ? e.message : "Failed to save"),
  });
  const reset = useMutation({
    mutationFn: () => apiFetch(`/api/v1/roles/${role!.id}/reset`, { method: "POST" }),
    onSuccess: onDone,
    onError: (e) => setError(e instanceof ApiError ? e.message : "Failed to restore defaults"),
  });
  const remove = useMutation({
    mutationFn: () => apiFetch(`/api/v1/roles/${role!.id}`, { method: "DELETE" }),
    onSuccess: onDone,
    onError: (e) => setError(e instanceof ApiError ? e.message : "Failed to delete"),
  });

  const box = "flex cursor-pointer items-start gap-2 rounded-md border border-hairline bg-white px-3 py-2 text-sm text-ink";

  return (
    <form onSubmit={(e) => { e.preventDefault(); setError(null); save.mutate(); }} className="space-y-4">
      {error && <ErrorState message={error} />}
      {(!role || !role.is_system) && (
        <div className="grid gap-3 md:grid-cols-2">
          <Input id="role-name" label="Role name" required maxLength={64} value={name} onChange={(e) => setName(e.target.value)} />
          <Input id="role-desc" label="Description (optional)" maxLength={255} value={description} onChange={(e) => setDescription(e.target.value)} />
        </div>
      )}

      <section>
        <h3 className="mb-1 text-sm font-medium text-ink">Pages this role can open</h3>
        <p className="mb-2 text-xs text-muted">Untick a page to remove it from their menu and block it everywhere, including direct links.</p>
        <div className="grid gap-2 sm:grid-cols-2">
          {groups.map((g) => (
            <label key={g.permission} className={`${box} ${disabled(g.permission) ? "opacity-50" : ""}`}>
              <input type="checkbox" className="mt-1" checked={selected.has(g.permission)} disabled={disabled(g.permission)} onChange={() => toggle(g.permission)} />
              <span>
                {g.prefixes.map((p) => SECTION_LABELS[p]).join(" · ")}
                {g.prefixes.every((p) => hidden.includes(p)) && (
                  <span className="ml-1 text-xs text-muted">(turned off for your farm by the platform)</span>
                )}
              </span>
            </label>
          ))}
        </div>
      </section>

      {tabSwitches.length > 0 && (
        <section>
          <h3 className="mb-1 text-sm font-medium text-ink">Tabs shown on an animal&apos;s page</h3>
          <p className="mb-2 text-xs text-muted">
            Untick a tab to hide it from everyone with this role. Overview is always shown. This only changes what they see:
            what they can do is set by the permissions below.
          </p>
          <div className="grid gap-2 sm:grid-cols-3">
            {tabSwitches.map((p) => (
              <label key={p.code} className={`${box} ${disabled(p.code) ? "opacity-50" : ""}`}>
                <input type="checkbox" className="mt-1" checked={selected.has(p.code)} disabled={disabled(p.code)} onChange={() => toggle(p.code)} />
                <span>{p.code.slice(TAB_GROUP.length + 1).replace(/^./, (c) => c.toUpperCase())}</span>
              </label>
            ))}
          </div>
        </section>
      )}

      <section>
        <h3 className="mb-1 text-sm font-medium text-ink">What they can do inside those pages</h3>
        <div className="space-y-3">
          {byGroup.map(([label, perms]) => (
            <div key={label}>
              <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted">{label}</p>
              <div className="grid gap-2 sm:grid-cols-2">
                {perms.map((p) => (
                  <label key={p.code} className={`${box} ${disabled(p.code) ? "opacity-50" : ""}`}>
                    <input type="checkbox" className="mt-1" checked={selected.has(p.code)} disabled={disabled(p.code)} onChange={() => toggle(p.code)} />
                    <span>{p.description}</span>
                  </label>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      <div className="flex flex-wrap items-center gap-2">
        <Button type="submit" disabled={save.isPending || (!role?.is_system && !name.trim())}>{save.isPending ? "Saving…" : role ? "Save access" : "Create role"}</Button>
        {role?.is_system && role.differs_from_default && (
          <Button type="button" variant="ghost" disabled={reset.isPending}
            onClick={() => { if (confirm(`Restore ${role.name} to its default access?`)) { setError(null); reset.mutate(); } }}>
            Restore defaults
          </Button>
        )}
        {role && !role.is_system && (
          <Button type="button" variant="ghost" className="ml-auto text-clay" disabled={remove.isPending}
            onClick={() => { if (confirm(`Delete the ${role.name} role?`)) { setError(null); remove.mutate(); } }}>
            Delete role
          </Button>
        )}
      </div>
    </form>
  );
}
