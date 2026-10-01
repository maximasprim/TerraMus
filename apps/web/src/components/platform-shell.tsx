"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { clsx } from "clsx";
import { LayoutDashboard, Building2, ShieldCheck, LogOut } from "lucide-react";
import { useRequirePlatformAuth, usePlatformLogout } from "@/lib/use-platform-auth";

const NAV = [
  { href: "/platform/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/platform/organizations", label: "Organizations", icon: Building2 },
  { href: "/platform/admins", label: "Admins", icon: ShieldCheck },
];

export function PlatformShell({ children }: { children: React.ReactNode }) {
  const { me, ready } = useRequirePlatformAuth();
  const logout = usePlatformLogout();
  const pathname = usePathname();

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-paper">
        <p className="font-display text-lg text-muted">Loading…</p>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen bg-paper">
      {/* bg-ink (near-black charcoal) rather than the tenant shell's
          bg-forest - deliberately reads as a different, higher-privilege
          surface at a glance, using an existing design token rather than
          introducing a new color. */}
      <aside className="flex w-60 flex-col border-r border-hairline bg-ink text-paper">
        <div className="border-b border-white/10 px-6 py-5">
          <p className="font-display text-lg italic">TerraMus Admin</p>
          <p className="text-xs text-paper/60">
            {me?.full_name} · <span className="uppercase">{me?.role}</span>
          </p>
        </div>
        <nav className="flex-1 space-y-1 px-3 py-4">
          {NAV.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className={clsx(
                "flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
                pathname.startsWith(href) ? "bg-white/10 font-medium" : "text-paper/70 hover:bg-white/5",
              )}
            >
              <Icon size={16} />
              {label}
            </Link>
          ))}
        </nav>
        {me?.role === "viewer" && (
          <div className="mx-3 mb-3 rounded-md border border-brass/30 bg-brass/10 px-3 py-2 text-xs text-brass-light">
            Viewer role - read-only. Write actions are disabled here and blocked by the API.
          </div>
        )}
        <button
          onClick={logout}
          className="flex items-center gap-2 border-t border-white/10 px-6 py-4 text-sm text-paper/70 hover:text-paper"
        >
          <LogOut size={16} />
          Sign out
        </button>
      </aside>
      <main className="flex-1 overflow-y-auto p-3">{children}</main>
    </div>
  );
}
