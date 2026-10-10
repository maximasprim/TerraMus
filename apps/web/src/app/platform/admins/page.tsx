"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { PlatformShell } from "@/components/platform-shell";
import { Button, Input, Select, Modal, ErrorState, EmptyState } from "@/components/ui";
import { platformApiFetch, PlatformApiError } from "@/lib/platform-api";
import { usePlatformMe } from "@/lib/use-platform-auth";
import type { PlatformAdminOut } from "@/lib/platform-types";

export default function PlatformAdminsPage() {
  const queryClient = useQueryClient();
  const { data: me } = usePlatformMe();
  const canWrite = me?.role === "superadmin";
  const [modalOpen, setModalOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const adminsQuery = useQuery<PlatformAdminOut[]>({
    queryKey: ["platform-admins"],
    queryFn: () => platformApiFetch<PlatformAdminOut[]>("/api/v1/platform/admins"),
  });

  const createAdmin = useMutation({
    mutationFn: (body: { email: string; full_name: string; password: string; role: string }) =>
      platformApiFetch("/api/v1/platform/admins", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["platform-admins"] });
      setModalOpen(false);
      setError(null);
    },
    onError: (err) => setError(err instanceof PlatformApiError ? err.message : "Failed to create admin"),
  });

  const toggleActive = useMutation({
    mutationFn: ({ adminId, isActive }: { adminId: string; isActive: boolean }) =>
      platformApiFetch(`/api/v1/platform/admins/${adminId}/status`, {
        method: "PATCH", body: JSON.stringify({ is_active: isActive }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["platform-admins"] });
      setActionError(null);
    },
    onError: (err) => setActionError(err instanceof PlatformApiError ? err.message : "Failed to update admin"),
  });

  const changeRole = useMutation({
    mutationFn: ({ adminId, role }: { adminId: string; role: string }) =>
      platformApiFetch(`/api/v1/platform/admins/${adminId}/role`, {
        method: "PATCH", body: JSON.stringify({ role }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["platform-admins"] });
      setActionError(null);
    },
    onError: (err) => setActionError(err instanceof PlatformApiError ? err.message : "Failed to update role"),
  });

  return (
    <PlatformShell>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl text-forest">Platform admins</h1>
          <p className="text-sm text-muted">Who can access this console, and with what access.</p>
        </div>
        {canWrite && <Button onClick={() => { setError(null); setModalOpen(true); }}>+ Add admin</Button>}
      </div>

      {actionError && <div className="mb-4"><ErrorState message={actionError} /></div>}
      {adminsQuery.error && (
        <ErrorState message={adminsQuery.error instanceof PlatformApiError ? adminsQuery.error.message : "Failed to load admins"} />
      )}
      {adminsQuery.data && adminsQuery.data.length === 0 && (
        <EmptyState title="No platform admins" body="This shouldn't be possible if you're seeing this page." />
      )}
      {adminsQuery.data && adminsQuery.data.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-hairline">
          <table className="w-full text-left text-sm">
            <thead className="bg-ink text-paper">
              <tr>
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Email</th>
                <th className="px-4 py-3 font-medium">Role</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium" />
              </tr>
            </thead>
            <tbody>
              {adminsQuery.data.map((a, i) => (
                <tr key={a.id} className={i % 2 === 0 ? "bg-white/40" : "bg-white/70"}>
                  <td className="px-4 py-3 font-medium text-ink">
                    {a.full_name} {a.id === me?.id && <span className="text-xs text-muted">(you)</span>}
                  </td>
                  <td className="px-4 py-3 text-muted">{a.email}</td>
                  <td className="px-4 py-3">
                    {canWrite ? (
                      <Select
                        value={a.role}
                        onChange={(e) => changeRole.mutate({ adminId: a.id, role: e.target.value })}
                        disabled={changeRole.isPending || a.id === me?.id}
                        className="!w-auto text-xs"
                      >
                        <option value="superadmin">superadmin</option>
                        <option value="viewer">viewer</option>
                      </Select>
                    ) : (
                      <span className="uppercase text-xs text-muted">{a.role}</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-muted">{a.is_active ? "Active" : "Deactivated"}</td>
                  <td className="px-4 py-3 text-right">
                    {canWrite && a.id !== me?.id && (
                      <Button
                        variant="ghost"
                        className="text-xs"
                        disabled={toggleActive.isPending}
                        onClick={() => toggleActive.mutate({ adminId: a.id, isActive: !a.is_active })}
                      >
                        {a.is_active ? "Deactivate" : "Reactivate"}
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title="Add platform admin">
        <CreateAdminForm error={error} pending={createAdmin.isPending} onSubmit={(body) => createAdmin.mutate(body)} />
      </Modal>
    </PlatformShell>
  );
}

function CreateAdminForm({
  onSubmit,
  error,
  pending,
}: {
  onSubmit: (body: { email: string; full_name: string; password: string; role: string }) => void;
  error: string | null;
  pending: boolean;
}) {
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("superadmin");

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ email, full_name: fullName, password, role });
      }}
      className="space-y-3"
    >
      {error && <ErrorState message={error} />}
      <Input id="admin-name" label="Full name" required value={fullName} onChange={(e) => setFullName(e.target.value)} />
      <Input id="admin-email" label="Email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
      <Input
        id="admin-password" label="Temporary password (12+ characters)" type="password" required minLength={12} maxLength={72}
        value={password} onChange={(e) => setPassword(e.target.value)}
      />
      <Select id="admin-role" label="Role" value={role} onChange={(e) => setRole(e.target.value)}>
        <option value="superadmin">superadmin - full read/write access</option>
        <option value="viewer">viewer - read-only</option>
      </Select>
      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Creating…" : "Create admin"}
      </Button>
    </form>
  );
}
