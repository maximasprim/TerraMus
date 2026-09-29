"""Custom domains for tenant public storefronts

Purely additive: four new nullable/defaulted columns on organizations.
Nothing existing changes.

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-21

"""
from alembic import op
import sqlalchemy as sa

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("custom_domain", sa.String(255), nullable=True))
    op.add_column("organizations", sa.Column("domain_verification_token", sa.String(64), nullable=True))
    op.add_column("organizations", sa.Column("domain_verified", sa.Boolean, nullable=False, server_default=sa.false()))
    op.add_column("organizations", sa.Column("domain_added_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "ix_organizations_custom_domain", "organizations", ["custom_domain"], unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_organizations_custom_domain", table_name="organizations")
    op.drop_column("organizations", "domain_added_at")
    op.drop_column("organizations", "domain_verified")
    op.drop_column("organizations", "domain_verification_token")
    op.drop_column("organizations", "custom_domain")
