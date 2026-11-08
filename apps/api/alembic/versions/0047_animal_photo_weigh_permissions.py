"""Separate ticks for adding an animal's photo and recording its weight.

Revision ID: 0047
Revises: 0046

Until now both needed `livestock.update` (the same tick that lets a role edit an animal or change its status). This adds
`livestock.photo` and `livestock.weigh`; the photo upload and the single-animal weight endpoints now accept either the
new tick or `livestock.update`, so nothing that works today stops working.

Nothing may change for anyone on the day this runs: every existing role that holds `livestock.update` (built-in or
custom, in every organization) is granted both new permissions, so their boxes show ticked. Other roles do not get them
(they could not do either before) - the owner can tick them per role.

Downgrade removes the permissions and every grant of them.
"""
import uuid

from alembic import op
from sqlalchemy import text

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None

NEW = [
    ("livestock.photo", "Add or replace an animal's photo"),
    ("livestock.weigh", "Record an animal's weight"),
]


def upgrade() -> None:
    bind = op.get_bind()
    for code, description in NEW:
        row = bind.execute(text("SELECT id FROM permissions WHERE code = :c"), {"c": code}).fetchone()
        if row is None:
            pid = str(uuid.uuid4())
            bind.execute(text("INSERT INTO permissions (id, code, description) VALUES (:i, :c, :d)"),
                         {"i": pid, "c": code, "d": description})
        else:
            pid = str(row[0])
        bind.execute(
            text(
                "INSERT INTO role_permissions (role_id, permission_id) "
                "SELECT rp.role_id, :p FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id "
                "WHERE p.code = 'livestock.update' ON CONFLICT (role_id, permission_id) DO NOTHING"
            ),
            {"p": pid},
        )


def downgrade() -> None:
    bind = op.get_bind()
    for code, _ in NEW:
        bind.execute(text("DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code = :c)"), {"c": code})
        bind.execute(text("DELETE FROM permissions WHERE code = :c"), {"c": code})
