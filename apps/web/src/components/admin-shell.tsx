"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { clsx } from "clsx";
import { LayoutDashboard, Beef, Sprout, LogOut, MapPin, Users, ShoppingCart, Tag, Package, Wallet, Truck, UserCog, Wrench, Search, Settings, UsersRound, CalendarClock, Bell, Newspaper, CreditCard, ExternalLink, Inbox } from "lucide-react";
import { useRequireAuth, useLogout } from "@/lib/use-auth";

const NAV = [
  { href: "/admin/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/admin/livestock", label: "Livestock", icon: Beef },
  { href: "/admin/crops", label: "Crops", icon: Sprout },
  { href: "/admin/listings", label: "Listings", icon: Tag },
  { href: "/admin/reservations", label: "Reservations", icon: CalendarClock },
  { href: "/admin/inventory", label: "Inventory", icon: Package },
  { href: "/admin/procurement", label: "Procurement", icon: Truck },
  { href: "/admin/finance", label: "Finance", icon: Wallet },
  { href: "/admin/billing", label: "Billing", icon: CreditCard },
  { href: "/admin/farms", label: "Farms", icon: MapPin },
  { href: "/admin/employees", label: "Employees", icon: UserCog },
  { href: "/admin/assets", label: "Assets", icon: Wrench },
  { href: "/admin/customers", label: "Customers", icon: Users },
  { href: "/admin/orders", label: "Orders", icon: ShoppingCart },
  { href: "/admin/inquiries", label: "Inquiries", icon: Inbox },
  { href: "/admin/cms", label: "Site Content", icon: Newspaper },
  { href: "/admin/notifications", label: "Notifications", icon: Bell },
  { href: "/admin/users", label: "Team", icon: UsersRound },
  { href: "/admin/search", label: "Search", icon: Search },
  { href: "/admin/settings", label: "Settings", icon: Settings },
];

export function AdminShell({ children }: { children: React.ReactNode }) {
  const { me, ready } = useRequireAuth();
  const logout = useLogout();
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
      <aside className="flex w-60 flex-col border-r border-hairline bg-forest text-paper">
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
