import { AdminShellLayout } from "@/components/admin-shell";

/**
 * One persistent shell for every /admin page. Without this, each page created its own shell, so the
 * whole sidebar was torn down and rebuilt (behind a full-screen "Loading…") on every navigation.
 * Pages still wrap themselves in <AdminShell>; inside this layout that is a no-op.
 */
export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return <AdminShellLayout>{children}</AdminShellLayout>;
}
