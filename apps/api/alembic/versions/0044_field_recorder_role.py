"""Field Recorder role, and the narrower `feedlot.intake` permission it relies on.

Revision ID: 0044
Revises: 0043

Until now, taking a batch in (creating an intake batch and registering its animals) needed `feedlot.manage`, which
also allows editing/deleting batches, costing documents, worksheet import and the Finance ledger sync. That is far
more than someone working in the field should hold. This migration:

1. adds the permission `feedlot.intake` (create intake batches, register / link animals) - the three intake routes
   now accept `feedlot.intake` OR `feedlot.manage`, so every existing role keeps working exactly as before;
2. grants `feedlot.intake` to each organization's "Farm Owner" role (which holds every permission);
3. creates the system role "Field Recorder" for every existing organization that has no role of that name yet
   (new organizations get it from identity/permissions.py DEFAULT_ROLE_GRANTS at registration). An organization that
   already made its own role with this name is left alone.

No other role, user or route is changed. Downgrade removes only the system "Field Recorder" roles and the new
permission.
"""
import uuid
from datetime import datetime, timezone

from alembic import op
from sqlalchemy import text

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None

NEW_PERMISSION = ("feedlot.intake", "Record feedlot intake: create intake batches and register animals into them")
ROLE_NAME = "Field Recorder"
ROLE_DESCRIPTION = "Records weights, takes in batches and writes health records in the field"
# Keep in step with identity/permissions.py DEFAULT_ROLE_GRANTS["Field Recorder"].
ROLE_GRANTS = [
    "cycles.read",
    "feedlot.read", "feedlot.weigh", "feedlot.intake",
    "livestock.read", "livestock.create",
    "health.read", "health.create",
    "search.use",
]


def _seed() -> None:
    bind = op.get_bind()
    code, description = NEW_PERMISSION
    existing = {r[0] for r in bind.execute(text("SELECT code FROM permissions")).fetchall()}
    if code not in existing:
        bind.execute(
            text("INSERT INTO permissions (id, code, description) VALUES (:i, :c, :d)"),
            {"i": str(uuid.uuid4()), "c": code, "d": description},
        )
    pid = {c: str(i) for i, c in bind.execute(text("SELECT id, code FROM permissions")).fetchall()}

    # 2. Farm Owner holds every permission.
    for (role_id,) in bind.execute(text("SELECT id FROM roles WHERE name = 'Farm Owner' AND is_system = true")).fetchall():
        bind.execute(
            text("INSERT INTO role_permissions (role_id, permission_id) VALUES (:r, :p) ON CONFLICT (role_id, permission_id) DO NOTHING"),
            {"r": str(role_id), "p": pid[code]},
        )

    # 3. The role, once per organization that does not already have one by this name.
    have_it = {
        org_id for (org_id,) in bind.execute(
            text("SELECT organization_id FROM roles WHERE name = :n"), {"n": ROLE_NAME}
        ).fetchall()
    }
    now = datetime.now(timezone.utc)
    for (org_id,) in bind.execute(text("SELECT id FROM organizations")).fetchall():
        if org_id in have_it:
            continue
        role_id = str(uuid.uuid4())
        bind.execute(
            text(
                "INSERT INTO roles (id, organization_id, name, description, is_system, created_at, updated_at) "
                "VALUES (:id, :org, :name, :description, true, :now, :now)"
            ),
            {"id": role_id, "org": str(org_id), "name": ROLE_NAME, "description": ROLE_DESCRIPTION, "now": now},
        )
        for grant in ROLE_GRANTS:
            if grant in pid:
                bind.execute(
                    text("INSERT INTO role_permissions (role_id, permission_id) VALUES (:r, :p)"),
                    {"r": role_id, "p": pid[grant]},
                )


def upgrade() -> None:
    _seed()


def downgrade() -> None:
    bind = op.get_bind()
    system_roles = "SELECT id FROM roles WHERE name = :n AND is_system = true"
    bind.execute(text(f"DELETE FROM user_roles WHERE role_id IN ({system_roles})"), {"n": ROLE_NAME})
    bind.execute(text(f"DELETE FROM role_permissions WHERE role_id IN ({system_roles})"), {"n": ROLE_NAME})
    bind.execute(text("DELETE FROM roles WHERE name = :n AND is_system = true"), {"n": ROLE_NAME})
    bind.execute(
        text("DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code = :c)"),
        {"c": NEW_PERMISSION[0]},
    )
    bind.execute(text("DELETE FROM permissions WHERE code = :c"), {"c": NEW_PERMISSION[0]})
