"""A separate switch for the Listings page.

Revision ID: 0046
Revises: 0045

Listings used to open for anyone holding `livestock.read`, so the owner could not give a role Livestock without
Listings or Listings without Livestock. This adds `listings.view`, which the Listings page and the listing READ
endpoints now accept (the endpoints still also accept `livestock.read`, so nothing that works today stops working).

Nothing may change for anyone on the day this runs: every existing role that holds `livestock.read` (built-in or
custom, in every organization) is granted `listings.view`. Roles without `livestock.read` could not open Listings
before and do not get it. From then on the owner can tick or untick Listings independently of Livestock.

Downgrade removes the permission and every grant of it.
"""
import uuid

from alembic import op
from sqlalchemy import text

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None

CODE = "listings.view"
DESCRIPTION = "Open the Listings page"


def upgrade() -> None:
    bind = op.get_bind()
    row = bind.execute(text("SELECT id FROM permissions WHERE code = :c"), {"c": CODE}).fetchone()
    if row is None:
        pid = str(uuid.uuid4())
        bind.execute(text("INSERT INTO permissions (id, code, description) VALUES (:i, :c, :d)"),
                     {"i": pid, "c": CODE, "d": DESCRIPTION})
    else:
        pid = str(row[0])
    bind.execute(
        text(
            "INSERT INTO role_permissions (role_id, permission_id) "
            "SELECT rp.role_id, :p FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id "
            "WHERE p.code = 'livestock.read' ON CONFLICT (role_id, permission_id) DO NOTHING"
        ),
        {"p": pid},
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(text("DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code = :c)"), {"c": CODE})
    bind.execute(text("DELETE FROM permissions WHERE code = :c"), {"c": CODE})
