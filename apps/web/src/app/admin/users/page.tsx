"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { Card, Button, Input, Modal, ErrorState, EmptyState, TagChip } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import { RolesPanel } from "@/components/roles-panel";
import { useCan } from "@/lib/use-auth";
import type { UserMe, Role, Employee } from "@/lib/types";

// The API already returns `phone`; UserMe (shared type) just doesn't declare it.
type TeamUser = UserMe & { phone?: string | null };

type UserDetailsBody = {
  full_name: string;
  email: string;
  phone: string;
  is_active: boolean;
  new_password?: string;
};

export default function UsersPage() {
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingUser, setEditingUser] = useState<UserMe | null>(null);
  const [roleError, setRoleError] = useState<string | null>(null);
  const [detailsUser, setDetailsUser] = useState<TeamUser | null>(null);
  const [detailsError, setDetailsError] = useState<string | null>(null);
  const [tab, setTab] = useState<"team" | "roles">("team");

  const usersQuery = useQuery<TeamUser[]>({
    queryKey: ["users"],
    queryFn: () => apiFetch<TeamUser[]>("/api/v1/users"),
  });
  const rolesQuery = useQuery<Role[]>({
    queryKey: ["roles"],
    queryFn: () => apiFetch<Role[]>("/api/v1/users/roles"),
  });

  // Employment status next to each login. Only for people who may see employee records; for everyone else
  // this stays empty and the Team page looks exactly as before.
  const can = useCan();
  const employeesQuery = useQuery<Employee[]>({
    queryKey: ["employees"],
    queryFn: () => apiFetch<Employee[]>("/api/v1/employees"),
    enabled: can("employees.manage"),
    retry: false,
  });
  const employeeByUser = new Map<string, Employee>();
  for (const e of employeesQuery.data ?? []) if (e.user_id) employeeByUser.set(e.user_id, e);

  const invite = useMutation({
    mutationFn: (body: { full_name: string; email: string; phone?: string; password: string; role_ids: string[] }) =>
      apiFetch("/api/v1/users", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      setModalOpen(false);
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Failed to invite user"),
  });

  const updateRoles = useMutation({
    mutationFn: ({ userId, roleIds }: { userId: string; roleIds: string[] }) =>
      apiFetch(`/api/v1/users/${userId}/roles`, { method: "PATCH", body: JSON.stringify({ role_ids: roleIds }) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      setEditingUser(null);
      setRoleError(null);
    },
    onError: (err) => setRoleError(err instanceof ApiError ? err.message : "Failed to update roles"),
  });

  const updateDetails = useMutation({
    mutationFn: ({ userId, body }: { userId: string; body: UserDetailsBody }) =>
      apiFetch(`/api/v1/users/${userId}`, { method: "PATCH", body: JSON.stringify(body) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      setDetailsUser(null);
      setDetailsError(null);
    },
    onError: (err) => setDetailsError(err instanceof ApiError ? err.message : "Failed to save changes"),
  });

  return (
    <AdminShell>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl text-forest">Team</h1>
          <p className="text-sm text-muted">Staff accounts and their roles.</p>
        </div>
        <Button onClick={() => { setError(null); setModalOpen(true); }}>+ Invite staff member</Button>
      </div>

      <div className="mb-4 flex gap-1 border-b border-hairline text-sm">
        {([["team", "Team"], ["roles", "Roles & access"]] as const).map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={`-mb-px border-b-2 px-4 py-2 ${tab === key ? "border-forest font-medium text-forest" : "border-transparent text-muted hover:text-ink"}`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "roles" && <RolesPanel />}
      {tab === "team" && (
      <>

      {usersQuery.error && (
        <ErrorState message={usersQuery.error instanceof ApiError ? usersQuery.error.message : "Failed to load team"} />
      )}
      {usersQuery.data && usersQuery.data.length === 0 && (
        <EmptyState title="No team members yet" body="Invite your first staff member." />
      )}
      {usersQuery.data && usersQuery.data.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-hairline">
          <table className="w-full text-left text-sm">
            <thead className="bg-forest text-paper">
              <tr>
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Email</th>
                <th className="px-4 py-3 font-medium">Roles</th>
                <th className="px-4 py-3 font-medium"> Actions</th>
              </tr>
            </thead>
            <tbody>
              {usersQuery.data.map((u, i) => (
                <tr key={u.id} className={i % 2 === 0 ? "bg-white/40" : "bg-white/70"}>
                  <td className="px-4 py-3 font-medium text-ink">
                    {u.full_name}
                    {!u.is_active && <span className="ml-2 text-xs font-normal text-clay">Inactive</span>}
                    <EmployeeLink employee={employeeByUser.get(u.id)} accountActive={u.is_active} />
                  </td>
                  <td className="px-4 py-3 text-muted">{u.email}</td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {u.roles.length === 0 ? (
                        <span className="text-xs text-muted">No roles</span>
                      ) : (
                        u.roles.map((r) => <TagChip key={r.id}>{r.name}</TagChip>)
                      )}
                    </div>
                  </td>
                  <td className="flex flex-row gap-2 whitespace-nowrap px-4 py-3 text-right">
                    <Button
                      variant="ghost"
                      className="text-xs"
                      onClick={() => { setDetailsError(null); setDetailsUser(u); }}
                    >
                      Edit details
                    </Button>
                    <Button
                      variant="ghost"
                      className="text-xs"
                      onClick={() => { setRoleError(null); setEditingUser(u); }}
                    >
                      Edit roles
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      </>
      )}

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title="Invite staff member">
        <InviteForm
          error={error}
          pending={invite.isPending}
          roles={rolesQuery.data ?? []}
          onSubmit={(body) => invite.mutate(body)}
        />
      </Modal>

      <Modal open={!!detailsUser} onClose={() => setDetailsUser(null)} title="Edit team member">
        {detailsUser && (
          <DetailsEditForm
            key={detailsUser.id}
            user={detailsUser}
            error={detailsError}
            pending={updateDetails.isPending}
            onSubmit={(body) => updateDetails.mutate({ userId: detailsUser.id, body })}
          />
        )}
      </Modal>

      <Modal open={!!editingUser} onClose={() => setEditingUser(null)} title="Edit roles">
        {editingUser && (
          <RoleEditForm
            user={editingUser}
            roles={rolesQuery.data ?? []}
            error={roleError}
            pending={updateRoles.isPending}
            onSubmit={(roleIds) => updateRoles.mutate({ userId: editingUser.id, roleIds })}
          />
        )}
      </Modal>
    </AdminShell>
  );
}

function InviteForm({
  onSubmit,
  error,
  pending,
  roles,
}: {
  onSubmit: (body: { full_name: string; email: string; phone?: string; password: string; role_ids: string[] }) => void;
  error: string | null;
  pending: boolean;
  roles: Role[];
}) {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [roleIds, setRoleIds] = useState<string[]>([]);

  const toggleRole = (id: string) =>
    setRoleIds((prev) => (prev.includes(id) ? prev.filter((r) => r !== id) : [...prev, id]));

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ full_name: fullName, email, phone: phone || undefined, password, role_ids: roleIds });
      }}
      className="space-y-3"
    >
      {error && <ErrorState message={error} />}
      <Input id="inv-name" label="Full name" required value={fullName} onChange={(e) => setFullName(e.target.value)} />
      <Input id="inv-email" label="Email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
      <Input id="inv-phone" label="Phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
      <Input
        id="inv-password" label="Temporary password" type="password" required minLength={8}
        value={password} onChange={(e) => setPassword(e.target.value)}
      />
      <div>
        <p className="mb-1 text-sm font-medium text-ink">Roles</p>
        <div className="flex flex-wrap gap-2">
          {roles.map((role) => (
            <label
              key={role.id}
              className="flex cursor-pointer items-center gap-1.5 rounded-full border border-hairline bg-white px-3 py-1 text-xs text-ink"
            >
              <input type="checkbox" checked={roleIds.includes(role.id)} onChange={() => toggleRole(role.id)} />
              {role.name}
            </label>
          ))}
        </div>
      </div>
      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Inviting…" : "Invite"}
      </Button>
    </form>
  );
}

function EmployeeLink({ employee, accountActive }: { employee?: Employee; accountActive: boolean }) {
  if (!employee) return null;
  const status = employee.employment_status.replace(/_/g, " ");
  const left = employee.employment_status === "terminated" || employee.employment_status === "suspended";
  return (
    <div className="mt-0.5 text-xs font-normal text-muted">
      <Link href={`/admin/employees/${employee.id}`} className="text-forest hover:underline">
        {employee.employee_number}
      </Link>
      {" · "}
      <span className="capitalize">{status}</span>
      {left && accountActive && <span className="ml-1 text-clay">- login still active</span>}
    </div>
  );
}

function DetailsEditForm({
  user,
  onSubmit,
  error,
  pending,
}: {
  user: TeamUser;
  onSubmit: (body: UserDetailsBody) => void;
  error: string | null;
  pending: boolean;
}) {
  const [fullName, setFullName] = useState(user.full_name);
  const [email, setEmail] = useState(user.email);
  const [phone, setPhone] = useState(user.phone ?? "");
  const [isActive, setIsActive] = useState(user.is_active);
  const [newPassword, setNewPassword] = useState("");

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({
          full_name: fullName,
          email,
          phone,
          is_active: isActive,
          ...(newPassword ? { new_password: newPassword } : {}),
        });
      }}
      className="space-y-3"
    >
      {error && <ErrorState message={error} />}
      <Input id="det-name" label="Full name" required minLength={2} value={fullName} onChange={(e) => setFullName(e.target.value)} />
      <Input id="det-email" label="Email (used to sign in)" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
      <Input id="det-phone" label="Phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
      <Input
        id="det-password" label="Set a new password (optional)" type="password" minLength={8} autoComplete="new-password"
        value={newPassword} onChange={(e) => setNewPassword(e.target.value)}
      />
      <label className="flex cursor-pointer items-center gap-2 text-sm text-ink">
        <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} />
        Account is active (untick to stop them signing in)
      </label>
      <p className="text-xs text-muted">
        Setting a new password or deactivating the account signs them out of every device.
      </p>
      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Saving…" : "Save changes"}
      </Button>
    </form>
  );
}

function RoleEditForm({
  user,
  roles,
  onSubmit,
  error,
  pending,
}: {
  user: UserMe;
  roles: Role[];
  onSubmit: (roleIds: string[]) => void;
  error: string | null;
  pending: boolean;
}) {
  const [roleIds, setRoleIds] = useState<string[]>(user.roles.map((r) => r.id));

  const toggleRole = (id: string) =>
    setRoleIds((prev) => (prev.includes(id) ? prev.filter((r) => r !== id) : [...prev, id]));

  return (
    <form onSubmit={(e) => { e.preventDefault(); onSubmit(roleIds); }} className="space-y-3">
      {error && <ErrorState message={error} />}
      <p className="text-sm text-muted">{user.full_name} ({user.email})</p>
      <div className="flex flex-wrap gap-2">
        {roles.map((role) => (
          <label
            key={role.id}
            className="flex cursor-pointer items-center gap-1.5 rounded-full border border-hairline bg-white px-3 py-1 text-xs text-ink"
          >
            <input type="checkbox" checked={roleIds.includes(role.id)} onChange={() => toggleRole(role.id)} />
            {role.name}
          </label>
        ))}
      </div>
      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Saving…" : "Save roles"}
      </Button>
    </form>
  );
}
