/**
 * Which backend permission each admin section needs.
 *
 * The backend enforces permissions on every route (apps/api/.../identity/
 * permissions.py) and returns the signed-in user's codes in /auth/me. This map
 * lets the UI match it: hide sections a role can't use, and show a clear
 * message (instead of a wall of 403 errors) if someone opens one directly.
 *
 * `permission` is the one the section's main data load needs - derived from the
 * routes each page actually calls, and verified against the backend by
 * `python scripts/contract_audit/run.py`. `null` = any signed-in user (the
 * backend doesn't restrict it either). This is a usability layer only: the
 * backend remains the sole authority and always re-checks.
 *
 * Order matters: it is the order of the sidebar, and `firstAccessiblePath`
 * picks the first section a user may open.
 */
export interface SectionPermission {
  prefix: string;
  permission: string | null;
}

export const SECTION_PERMISSIONS: SectionPermission[] = [
  { prefix: "/admin/dashboard", permission: "reports.view" },
  { prefix: "/admin/livestock", permission: "livestock.read" },
  { prefix: "/admin/feedlot", permission: "feedlot.read" },
  { prefix: "/admin/groups", permission: "groups.read" },
  { prefix: "/admin/crops", permission: "crops.read" },
  { prefix: "/admin/listings", permission: "livestock.read" },
  { prefix: "/admin/reservations", permission: "orders.manage" },
  { prefix: "/admin/inventory", permission: "inventory.read" },
  { prefix: "/admin/procurement", permission: "procurement.manage" },
  { prefix: "/admin/finance", permission: "finance.read" },
  { prefix: "/admin/receivables", permission: "finance.read" },
  { prefix: "/admin/billing", permission: "users.manage" },
  { prefix: "/admin/farms", permission: "farm.manage" },
  { prefix: "/admin/employees", permission: "employees.manage" },
  { prefix: "/admin/assets", permission: "assets.manage" },
  { prefix: "/admin/fuel", permission: "assets.manage" },
  { prefix: "/admin/customers", permission: "customers.manage" },
  { prefix: "/admin/training", permission: "training.read" },
  { prefix: "/admin/orders", permission: "orders.manage" },
  { prefix: "/admin/inquiries", permission: "orders.manage" },
  { prefix: "/admin/cms", permission: "cms.manage" },
  { prefix: "/admin/reviews", permission: "cms.manage" },
  { prefix: "/admin/notifications", permission: null },
  { prefix: "/admin/audit", permission: "audit.view" },
  { prefix: "/admin/users", permission: "users.manage" },
  { prefix: "/admin/search", permission: "search.use" },
  { prefix: "/admin/settings", permission: "farm.manage" },
  { prefix: "/admin/reports", permission: "reports.view" }, // not in the sidebar (reached from the dashboard)
  // Sub-pages that need a WRITE permission on top of their section's read permission. Longest prefix wins,
  // so these override the section entries above for just these pages.
  { prefix: "/admin/livestock/new", permission: "livestock.create" },
  { prefix: "/admin/crops/new", permission: "crops.create" },
];

/** Permission needed for a path, using the longest matching section prefix
 * (so /admin/livestock/123 and /admin/inventory/valuation inherit their section).
 * Unknown paths need nothing - fail open rather than lock people out. */
export function requiredPermission(pathname: string): string | null {
  let best: SectionPermission | null = null;
  for (const section of SECTION_PERMISSIONS) {
    const hit = pathname === section.prefix || pathname.startsWith(section.prefix + "/");
    if (hit && (best === null || section.prefix.length > best.prefix.length)) best = section;
  }
  return best ? best.permission : null;
}

/** `permissions` undefined means "not loaded yet" - allow, so the UI never
 * flashes an access-denied message while /auth/me is still in flight. */
export function hasPermission(permissions: string[] | undefined, required: string | null): boolean {
  if (required === null || permissions === undefined) return true;
  return permissions.includes(required);
}

export function canAccessPath(permissions: string[] | undefined, pathname: string): boolean {
  return hasPermission(permissions, requiredPermission(pathname));
}

/** First sidebar section this user may open (always exists: Notifications and
 * Billing need no permission). Used as the landing page for roles that can't
 * see the dashboard. */
export function firstAccessiblePath(permissions: string[] | undefined): string {
  // top-level sections only - a "/new" form is never a sensible landing page
  const found = SECTION_PERMISSIONS.find((s) => s.prefix.split("/").length === 3 && hasPermission(permissions, s.permission));
  return found ? found.prefix : "/admin/notifications";
}
