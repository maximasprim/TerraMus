"""Global permission catalog (spec §5). Codes are the source of truth for
authorization checks; role names/UI labels are cosmetic only."""

PERMISSIONS: list[tuple[str, str]] = [
    ("livestock.read", "View livestock records"),
    ("livestock.create", "Register new livestock"),
    ("livestock.update", "Update livestock records"),
    ("livestock.delete", "Delete/archive livestock records"),
    ("livestock.sell", "Mark livestock as sold / manage sales"),
    ("health.read", "View health records"),
    ("health.create", "Create health records"),
    ("breeding.read", "View breeding records"),
    ("breeding.create", "Create breeding records"),
    ("dairy.read", "View dairy production records"),
    ("dairy.create", "Record milk production"),
    ("crops.read", "View crop/plant planting records"),
    ("crops.create", "Register new crop plantings"),
    ("crops.update", "Update crop planting records"),
    ("crops.delete", "Delete/archive crop planting records"),
    ("crops.harvest", "Record crop harvests"),
    ("finance.read", "View financial records"),
    ("finance.create", "Create financial records"),
    ("inventory.read", "View inventory"),
    ("inventory.adjust", "Adjust inventory / stock movements"),
    ("procurement.manage", "Manage suppliers and purchase orders"),
    ("orders.manage", "Manage customer orders"),
    ("listings.manage", "Create and manage e-commerce livestock listings"),
    ("cms.manage", "Manage public website content (blog, testimonials, FAQs, banners, farm profile)"),
    ("payments.manage", "Manage/reconcile payments"),
    ("customers.manage", "Manage customer records"),
    ("users.manage", "Manage organization users and roles"),
    ("farm.manage", "Manage farm/branch/location configuration"),
    ("reports.view", "View reports and analytics"),
    ("audit.view", "View audit logs"),
    ("employees.manage", "Manage farm employee/staff profiles and employment status"),
    ("assets.manage", "Manage farm assets and equipment"),
    ("search.use", "Use global search across livestock, customers, orders, invoices, suppliers, and inventory"),
    ("feedlot.read", "View feedlot batches, performance, costing and profitability"),
    ("feedlot.weigh", "Record weigh days (bulk weights)"),
    ("feedlot.intake", "Record feedlot intake: create intake batches and register animals into them"),
    ("feedlot.manage", "Manage feedlot batches, costing documents and worksheet import/export"),
    ("training.read", "View training courses, sessions and enrolments"),
    ("training.manage", "Manage training courses, sessions, enrolments and certificates"),
    ("groups.read", "View flocks / fish / rabbit groups and their records"),
    ("groups.record", "Record daily group data (mortality, eggs, feed, weights)"),
    ("groups.manage", "Create, sell and close flocks / fish / rabbit groups"),
    ("fodder.read", "View fodder plots, production, stock, costs and reports"),
    ("fodder.record", "Record fodder harvests, costs, issues, losses and stock counts"),
    ("fodder.manage", "Manage fodder products, prices, plots, cycles, investments, purchases and sales"),
    ("cycles.read", "View production cycles and filter reports by cycle"),
    ("cycles.manage", "Create, edit, close and reopen production cycles; assign records to a cycle"),
    # --- What a role SEES (visibility switches the farm owner ticks per role in Team > Roles) -------------------
    # These only show or hide screens; what a person may DO is still decided by the permissions above.
    ("notifications.view", "Open the Notifications page"),
    ("animaltabs.timeline", "Show the Timeline tab on an animal's page"),
    ("animaltabs.health", "Show the Health tab on an animal's page"),
    ("animaltabs.weights", "Show the Weights tab on an animal's page"),
    ("animaltabs.movements", "Show the Movements tab on an animal's page"),
    ("animaltabs.breeding", "Show the Breeding tab on an animal's page"),
    ("animaltabs.dairy", "Show the Dairy tab on an animal's page"),
]

# The visibility switches above. Every staff role starts with ALL of them on, so nothing disappears for anyone until
# the farm owner unticks it. (Keep in step with migration 0045.)
VISIBILITY_PERMISSIONS: list[str] = [code for code, _ in PERMISSIONS[-7:]]

# Default role -> permission grants used by org bootstrap/seed data (spec §5, §61).
DEFAULT_ROLE_GRANTS: dict[str, list[str]] = {
    "Farm Owner": [code for code, _ in PERMISSIONS],  # full access within the org
    "Farm Manager": [
        "cycles.read", "cycles.manage",
        "fodder.read", "fodder.record", "fodder.manage",
        "training.read", "training.manage", "groups.read", "groups.record", "groups.manage",
        "feedlot.read", "feedlot.weigh", "feedlot.manage",
        "livestock.read", "livestock.create", "livestock.update", "livestock.sell",
        "health.read", "breeding.read", "dairy.read",
        "crops.read", "crops.create", "crops.update", "crops.harvest",
        "inventory.read", "inventory.adjust", "procurement.manage",
        "orders.manage", "listings.manage", "customers.manage", "farm.manage", "reports.view",
        "employees.manage", "assets.manage", "search.use",
    ],
    "Livestock Manager": [
        "cycles.read",
        "fodder.read", "fodder.record",
        "groups.read", "groups.record", "groups.manage",
        "feedlot.read", "feedlot.weigh", "feedlot.manage",
        "livestock.read", "livestock.create", "livestock.update",
        "breeding.read", "breeding.create", "dairy.read", "dairy.create", "reports.view", "search.use",
    ],
    "Crop Manager": [
        "crops.read", "crops.create", "crops.update", "crops.harvest", "reports.view", "search.use",
        "livestock.read", "listings.manage", "orders.manage",
    ],
    "Veterinarian": [
        "cycles.read",
        "fodder.read",
        "groups.read",
        "feedlot.read",
        "livestock.read", "health.read", "health.create", "breeding.read", "reports.view", "search.use",
    ],
    "Farm Worker": [
        "cycles.read",
        "fodder.read", "fodder.record",
        "groups.read", "groups.record",
        "feedlot.read", "feedlot.weigh",
        "livestock.read", "health.create", "dairy.create", "crops.read", "crops.harvest", "search.use",
    ],
    # Field recorder: weighs, takes batches in and writes health records, but cannot edit/delete batches, touch
    # costing, import worksheets, post to Finance, sell or cull (those stay on feedlot.manage / livestock.sell).
    "Field Recorder": [
        "cycles.read",
        "feedlot.read", "feedlot.weigh", "feedlot.intake",
        "livestock.read", "livestock.create",
        "health.read", "health.create",
        "search.use",
    ],
    "Inventory Manager": [
        "cycles.read",
        "inventory.read", "inventory.adjust", "procurement.manage", "reports.view", "assets.manage", "search.use",
    ],
    "Accountant": [
        "cycles.read",
        "fodder.read",
        "training.read", "groups.read",
        "feedlot.read",
        "finance.read", "finance.create", "payments.manage", "reports.view", "search.use",
    ],
    "Sales Manager": [
        "cycles.read",
        "fodder.read",
        "training.read", "training.manage",
        "feedlot.read",
        "livestock.read", "livestock.sell", "orders.manage", "listings.manage", "customers.manage",
        "payments.manage", "reports.view", "cms.manage", "search.use",
    ],
    "System Administrator": [
        "users.manage", "farm.manage", "audit.view", "reports.view", "employees.manage", "search.use",
    ],
    "Customer": [],  # customers access their own data via ownership checks, not RBAC perms
}


for _role_name, _grants in DEFAULT_ROLE_GRANTS.items():
    # Farm Owner already holds every code; Customer is the storefront account role and sees no admin screens.
    if _role_name not in ("Farm Owner", "Customer"):
        _grants.extend(c for c in VISIBILITY_PERMISSIONS if c not in _grants)
