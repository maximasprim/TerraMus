"""Per-role choice of weigh form: several animals at once, or one animal at a time.

Revision ID: 0051
Revises: 0050

New permission weighform.multi. A role that holds it sees the weigh form with many rows (as before); a role without it
sees the one-animal-at-a-time form. It is granted to every existing role that can weigh (feedlot.weigh or
livestock.weigh) EXCEPT the system Field Recorder role, so the only change on deploy is that Field Recorder now gets the
one-at-a-time form. The farm owner can change any role under Team > Roles. Downgrade removes the permission and grants.
"""
import uuid

from alembic import op
from sqlalchemy import text

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None

CODE = "weighform.multi"
DESCRIPTION = "Weigh form: record several animals at once (leave off to record one animal at a time)"


def upgrade() -> None:
    bind = op.get_bind()
    row = bind.execute(text("SELECT id FROM permissions WHERE code = :c"), {"c": CODE}).fetchone()
    if row is None:
        pid = str(uuid.uuid4())
        bind.execute(text("INSERT INTO permissions (id, code, description) VALUES (:i, :c, :d)"), {"i": pid, "c": CODE, "d": DESCRIPTION})
    else:
        pid = str(row[0])
    bind.execute(
        text(
            "INSERT INTO role_permissions (role_id, permission_id) "
            "SELECT DISTINCT rp.role_id, CAST(:p AS uuid) FROM role_permissions rp "
            "JOIN permissions p ON p.id = rp.permission_id JOIN roles r ON r.id = rp.role_id "
            "WHERE p.code IN ('feedlot.weigh', 'livestock.weigh') AND NOT (r.is_system AND r.name = 'Field Recorder') "
            "ON CONFLICT (role_id, permission_id) DO NOTHING"
        ),
        {"p": pid},
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(text("DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code = :c)"), {"c": CODE})
    bind.execute(text("DELETE FROM permissions WHERE code = :c"), {"c": CODE})
