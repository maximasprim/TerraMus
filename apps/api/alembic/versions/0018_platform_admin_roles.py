"""Platform admin roles (superadmin / viewer)

Purely additive: one new column, defaults every existing platform admin
(created via scripts/seed_platform_admin.py before this migration) to
"superadmin", so nobody loses access they already had.

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-19

"""
from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "platform_admins",
        sa.Column("role", sa.String(16), nullable=False, server_default="superadmin"),
    )


def downgrade() -> None:
    op.drop_column("platform_admins", "role")
