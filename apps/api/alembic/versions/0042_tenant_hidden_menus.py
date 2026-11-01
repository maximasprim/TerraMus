"""Per-tenant hidden sidebar menus.

Adds `tenant_catalog_settings.hidden_menus` (JSONB, nullable). NULL / [] means nothing is hidden, so every existing
organization behaves exactly as before. Purely additive.

Revision ID: 0042
Revises: 0041
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenant_catalog_settings", sa.Column("hidden_menus", pg.JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("tenant_catalog_settings", "hidden_menus")
