"""The tenant admin sidebar, as a platform admin sees it when choosing what a tenant may see.

KEEP IN SYNC with `NAV` in apps/web/src/components/admin-shell.tsx (same hrefs, same order) - tests/test_menu_visibility.py
fails if they drift. A menu key is simply the sidebar entry's path; hiding a key also hides every page under it.

Visibility only: this decides what a tenant's sidebar offers and which pages their admin app opens. It is not an
authorisation layer - what a user may *do* is still decided by their role's permissions on every API call.
"""
from __future__ import annotations

# (key, label, group)
MENUS: tuple[tuple[str, str, str], ...] = (
    ("/admin/dashboard", "Dashboard", "Overview"),
    ("/admin/reports", "Reports", "Overview"),
    ("/admin/livestock", "Livestock", "Farm operations"),
    ("/admin/cycles", "Production Cycles", "Farm operations"),
    ("/admin/feedlot", "Feedlot", "Farm operations"),
    ("/admin/weights", "Weights", "Farm operations"),
    ("/admin/groups", "Flocks & Fish", "Farm operations"),
    ("/admin/fodder", "Fodder", "Farm operations"),
    ("/admin/crops", "Crops", "Farm operations"),
    ("/admin/inventory", "Inventory", "Farm operations"),
    ("/admin/farms", "Farms", "Farm operations"),
    ("/admin/assets", "Assets", "Farm operations"),
    ("/admin/fuel", "Fuel", "Farm operations"),
    ("/admin/training", "Training", "Farm operations"),
    ("/admin/listings", "Listings", "Sales"),
    ("/admin/reservations", "Reservations", "Sales"),
    ("/admin/customers", "Customers", "Sales"),
    ("/admin/orders", "Orders", "Sales"),
    ("/admin/inquiries", "Inquiries", "Sales"),
    ("/admin/procurement", "Procurement", "Money"),
    ("/admin/finance", "Finance", "Money"),
    ("/admin/receivables", "Receivables", "Money"),
    ("/admin/billing", "Billing", "Money"),
    ("/admin/employees", "Employees", "People"),
    ("/admin/users", "Team", "People"),
    ("/admin/cms", "Site Content", "Public site"),
    ("/admin/reviews", "Reviews", "Public site"),
    ("/admin/notifications", "Notifications", "Account"),
    ("/admin/audit", "Audit log", "Account"),
    ("/admin/search", "Search", "Account"),
    ("/admin/settings", "Settings", "Account"),
)

# Always shown: the landing page and the one section every role can open, so a tenant can never be left with no
# usable page at all.
PROTECTED: frozenset[str] = frozenset({"/admin/dashboard", "/admin/notifications"})

ALL_KEYS: frozenset[str] = frozenset(key for key, _, _ in MENUS)
HIDEABLE_KEYS: frozenset[str] = ALL_KEYS - PROTECTED
