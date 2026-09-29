"""Phase 15: customer self-service accounts - link users to customers (spec §16/§70)

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-05

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("customer_id", pg.UUID(as_uuid=True), sa.ForeignKey("customers.id"), nullable=True),
    )
    op.create_index("ix_users_customer_id", "users", ["customer_id"])


def downgrade() -> None:
    op.drop_index("ix_users_customer_id", table_name="users")
    op.drop_column("users", "customer_id")
