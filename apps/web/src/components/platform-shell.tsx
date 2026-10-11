"use client";

import Link from "next/link";
import { createContext, useContext } from "react";
import { usePathname } from "next/navigation";
import { clsx } from "clsx";
import { LayoutDashboard, BarChart3, Building2, ShieldCheck, LogOut } from "lucide-react";
import { useRequirePlatformAuth, usePlatformLogout } from "@/lib/use-platform-auth";
import { ShellFrame } from "@/components/shell-frame";

const NAV = [
  { href: "/platform/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/platform/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/platform/organizations", label: "Organizations", icon: Building2 },
  { href: "/platform/admins", label: "Admins", icon: ShieldCheck },
];

/** True inside app/platform/layout.tsx, which renders the shell once for every console page. */
const ShellProvided = createContext(false);

/** Pages under /platform that are NOT part of the signed-in console (no sidebar, no auth gate). */
const BARE_ROUTES = ["/platform/login", "/platform/reset-password"];

function PlatformShellFrame({ children }: { children: React.ReactNode }) {
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
    // bg-ink (near-black charcoal) rather than the tenant shell's bg-forest - deliberately reads as
    // a different, higher-privilege surface at a glance, using an existing design token rather than
    // introducing a new color.
    <ShellFrame
      sidebarClassName="bg-ink"
      mobileTitle="TerraMus Admin"
      mainClassName="p-3"
      brand={
        <div className="border-b border-white/10 px-6 py-5">
          <p className="font-display text-lg italic">TerraMus Admin</p>
          <p className="text-xs text-paper/60">
            {me?.full_name} · <span className="uppercase">{me?.role}</span>
          </p>
        </div>
      }
      nav={NAV.map(({ href, label, icon: Icon }) => (
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
      footer={
        <>
          {me?.role === "viewer" && (
            <div className="mx-3 mb-3 rounded-md border border-brass/30 bg-brass/10 px-3 py-2 text-xs text-brass-light">
              Viewer role - read-only. Write actions are disabled here and blocked by the API.
            </div>
          )}
          <button
            onClick={logout}
            className="flex w-full items-center gap-2 border-t border-white/10 px-6 py-4 text-sm text-paper/70 hover:text-paper"
          >
            <LogOut size={16} />
            Sign out
          </button>
        </>
      }
    >
      {children}
    </ShellFrame>
  );
}

/**
 * What every console page wraps itself in. Inside app/platform/layout.tsx the shell already exists
 * and persists across navigation, so this just renders the page; used on its own it renders the full
 * shell exactly as before.
 */
export function PlatformShell({ children }: { children: React.ReactNode }) {
  const provided = useContext(ShellProvided);
  return provided ? <>{children}</> : <PlatformShellFrame>{children}</PlatformShellFrame>;
}

/** Rendered once by app/platform/layout.tsx so the sidebar is never rebuilt when moving between pages. */
export function PlatformShellLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() ?? "";
  if (BARE_ROUTES.some((route) => pathname === route || pathname.startsWith(`${route}/`))) {
    return <>{children}</>;
  }
  return (
    <ShellProvided.Provider value={true}>
      <PlatformShellFrame>{children}</PlatformShellFrame>
    </ShellProvided.Provider>
  );
}
