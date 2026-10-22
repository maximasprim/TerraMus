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
    ("feedlot.manage", "Manage feedlot batches, costing documents and worksheet import/export"),
    ("training.read", "View training courses, sessions and enrolments"),
    ("training.manage", "Manage training courses, sessions, enrolments and certificates"),
    ("groups.read", "View flocks / fish / rabbit groups and their records"),
    ("groups.record", "Record daily group data (mortality, eggs, feed, weights)"),
    ("groups.manage", "Create, sell and close flocks / fish / rabbit groups"),
]

# Default role -> permission grants used by org bootstrap/seed data (spec §5, §61).
DEFAULT_ROLE_GRANTS: dict[str, list[str]] = {
    "Farm Owner": [code for code, _ in PERMISSIONS],  # full access within the org
    "Farm Manager": [
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
        "groups.read",
        "feedlot.read",
        "livestock.read", "health.read", "health.create", "breeding.read", "reports.view", "search.use",
    ],
    "Farm Worker": [
        "groups.read", "groups.record",
        "feedlot.read", "feedlot.weigh",
        "livestock.read", "health.create", "dairy.create", "crops.read", "crops.harvest", "search.use",
    ],
    "Inventory Manager": [
        "inventory.read", "inventory.adjust", "procurement.manage", "reports.view", "assets.manage", "search.use",
    ],
    "Accountant": [
        "training.read", "groups.read",
        "feedlot.read",
        "finance.read", "finance.create", "payments.manage", "reports.view", "search.use",
    ],
    "Sales Manager": [
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
