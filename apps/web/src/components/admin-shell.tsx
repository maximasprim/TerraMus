"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect } from "react";
import { clsx } from "clsx";
import { LayoutDashboard, BarChart3, Beef, Sprout, LogOut, MapPin, Users, Wheat, ShoppingCart, Tag, Package, Wallet, Truck, UserCog, Wrench, Search, Settings, UsersRound, CalendarClock, Bell, Newspaper, CreditCard, ExternalLink, Inbox, History, Bird, Scale, Receipt, Fuel, GraduationCap, Star } from "lucide-react";
import { useRequireAuth, useLogout } from "@/lib/use-auth";
import { canAccessPath, firstAccessiblePath } from "@/lib/permissions";
import { useCatalog } from "@/lib/use-catalog";
import { ShellFrame } from "@/components/shell-frame";

const NAV = [
  { href: "/admin/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/admin/reports", label: "Reports", icon: BarChart3 },
  { href: "/admin/livestock", label: "Livestock", icon: Beef },
  { href: "/admin/feedlot", label: "Feedlot", icon: Scale },
  { href: "/admin/groups", label: "Flocks & Fish", icon: Bird },
  { href: "/admin/fodder", label: "Fodder", icon: Wheat },
  { href: "/admin/crops", label: "Crops", icon: Sprout },
  { href: "/admin/listings", label: "Listings", icon: Tag },
  { href: "/admin/reservations", label: "Reservations", icon: CalendarClock },
  { href: "/admin/inventory", label: "Inventory", icon: Package },
  { href: "/admin/procurement", label: "Procurement", icon: Truck },
  { href: "/admin/finance", label: "Finance", icon: Wallet },
  { href: "/admin/receivables", label: "Receivables", icon: Receipt },
  { href: "/admin/billing", label: "Billing", icon: CreditCard },
  { href: "/admin/farms", label: "Farms", icon: MapPin },
  { href: "/admin/employees", label: "Employees", icon: UserCog },
  { href: "/admin/assets", label: "Assets", icon: Wrench },
  { href: "/admin/fuel", label: "Fuel", icon: Fuel },
  { href: "/admin/customers", label: "Customers", icon: Users },
  { href: "/admin/training", label: "Training", icon: GraduationCap },
  { href: "/admin/orders", label: "Orders", icon: ShoppingCart },
  { href: "/admin/inquiries", label: "Inquiries", icon: Inbox },
  { href: "/admin/cms", label: "Site Content", icon: Newspaper },
  { href: "/admin/reviews", label: "Reviews", icon: Star },
  { href: "/admin/notifications", label: "Notifications", icon: Bell },
  { href: "/admin/audit", label: "Audit log", icon: History },
  { href: "/admin/users", label: "Team", icon: UsersRound },
  { href: "/admin/search", label: "Search", icon: Search },
  { href: "/admin/settings", label: "Settings", icon: Settings },
];

/** True inside app/admin/layout.tsx, which renders the shell once for every admin page. */
const ShellProvided = createContext(false);

function AdminShellFrame({ children }: { children: React.ReactNode }) {
  const { me, ready } = useRequireAuth();
  const logout = useLogout();
  // Modules a platform admin has switched off for this organization are left out of the
  // sidebar. Fails open: until /catalog has loaded (or if it errors) every entry shows.
  const { data: catalog } = useCatalog(ready);
  const moduleOff = (href: string) =>
    (href === "/admin/livestock" && catalog?.livestock_enabled === false) ||
    (href === "/admin/crops" && catalog?.crops_enabled === false);
  const pathname = usePathname();
  const router = useRouter();

  // Permission-aware UI (see lib/permissions.ts). `permissions` is undefined until
  // /auth/me has loaded, in which case everything is allowed - fail open.
  const permissions = me?.permissions;
  const allowed = canAccessPath(permissions, pathname);
  const sendToLanding = !allowed && pathname === "/admin/dashboard";
  useEffect(() => {
    // Roles without dashboard access (e.g. Farm Worker) are routed to the first page they can use.
    if (sendToLanding) router.replace(firstAccessiblePath(permissions));
  }, [sendToLanding, permissions, router]);

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-paper">
        <p className="font-display text-lg text-muted">Loading…</p>
      </div>
    );
  }

  return (
    <ShellFrame
      sidebarClassName="bg-forest"
      mobileTitle={me?.organization.name}
      mainClassName="p-4 sm:p-6 lg:p-8"
      brand={
        <div className="border-b border-white/10 px-6 py-5">
          <p className="font-display text-lg italic text-center leading-tight">{me?.organization.name}</p>
          <p className="text-xs text-paper/60 leading-tight">{me?.user.full_name}</p>
          {me?.organization.slug && (
            <a
              href={`/shop/${me.organization.slug}`}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-2 flex items-center gap-1 text-xs text-paper/70 hover:text-paper hover:underline"
            >
              <ExternalLink size={12} />
              View public shop
            </a>
          )}
        </div>
      }
      nav={NAV.filter(({ href }) => canAccessPath(permissions, href) && !moduleOff(href)).map(({ href, label, icon: Icon }) => (
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
        <button
          onClick={logout}
          className="flex w-full items-center gap-2 border-t border-white/10 px-6 py-4 text-sm text-paper/70 hover:text-paper"
        >
          <LogOut size={16} />
          Sign out
        </button>
      }
    >
      {allowed ? (
        children
      ) : sendToLanding ? (
        <p className="text-sm text-muted">Taking you to your workspace…</p>
      ) : (
        <div className="mx-auto mt-16 max-w-md rounded-lg border border-hairline bg-white p-8 text-center">
          <h1 className="font-display text-xl text-forest">You don&apos;t have access to this page</h1>
          <p className="mt-2 text-sm text-muted">
            Your role doesn&apos;t include this area. If you need it, ask the farm owner to update your role under Team.
          </p>
          <Link href={firstAccessiblePath(permissions)} className="mt-5 inline-block rounded-md bg-forest px-5 py-2.5 text-sm font-medium text-paper hover:bg-forest/90">
            Go to my workspace
          </Link>
        </div>
      )}
    </ShellFrame>
  );
}

/**
 * What every admin page wraps itself in. Inside app/admin/layout.tsx the shell already exists and
 * persists across navigation, so this just renders the page; used on its own (e.g. in a test or a
 * page outside that layout) it renders the full shell exactly as before.
 */
export function AdminShell({ children }: { children: React.ReactNode }) {
  const provided = useContext(ShellProvided);
  return provided ? <>{children}</> : <AdminShellFrame>{children}</AdminShellFrame>;
}

/** Rendered once by app/admin/layout.tsx so the sidebar is never rebuilt when moving between pages. */
export function AdminShellLayout({ children }: { children: React.ReactNode }) {
  return (
    <ShellProvided.Provider value={true}>
      <AdminShellFrame>{children}</AdminShellFrame>
    </ShellProvided.Provider>
  );
}
