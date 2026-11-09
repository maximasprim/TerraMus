"""Weights report: batch target weight, and the permissions for the new Weights page.

Revision ID: 0048
Revises: 0047

  * intake_batches.target_weight_kg  - the market-ready weight for a batch (an animal's own target_weight, which
    already existed, overrides it). Nullable: nothing has a target until the owner sets one.
  * weights.view     - open the Weights page. Granted to every existing role that holds livestock.read.
  * weights.targets  - set batch/animal targets. Granted to every existing role that holds feedlot.manage or
    livestock.update.

Nothing that works today changes: no existing page or endpoint is touched, and roles that could not see animals do
not get the new page. Downgrade removes the column, the permissions and every grant of them.
"""
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None

NEW = [
    ("weights.view", "Open the Weights report", ("livestock.read",)),
    ("weights.targets", "Set target weights for batches and animals", ("feedlot.manage", "livestock.update")),
]


def upgrade() -> None:
    op.add_column("intake_batches", sa.Column("target_weight_kg", sa.Numeric(8, 2), nullable=True))
    bind = op.get_bind()
    for code, description, from_codes in NEW:
        row = bind.execute(text("SELECT id FROM permissions WHERE code = :c"), {"c": code}).fetchone()
        if row is None:
            pid = str(uuid.uuid4())
            bind.execute(text("INSERT INTO permissions (id, code, description) VALUES (:i, :c, :d)"),
                         {"i": pid, "c": code, "d": description})
        else:
            pid = str(row[0])
        for src in from_codes:
            bind.execute(
                text(
                    "INSERT INTO role_permissions (role_id, permission_id) "
                    "SELECT DISTINCT rp.role_id, CAST(:p AS uuid) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id "
                    "WHERE p.code = :src ON CONFLICT (role_id, permission_id) DO NOTHING"
                ),
                {"p": pid, "src": src},
            )


def downgrade() -> None:
    bind = op.get_bind()
    for code, _, _ in NEW:
        bind.execute(text("DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code = :c)"), {"c": code})
        bind.execute(text("DELETE FROM permissions WHERE code = :c"), {"c": code})
    op.drop_column("intake_batches", "target_weight_kg")
