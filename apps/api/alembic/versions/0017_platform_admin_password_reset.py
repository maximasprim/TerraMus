"""Platform admin password reset tokens

Purely additive: one new table. Nothing existing changes.

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-19

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_admin_password_reset_tokens",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("platform_admin_id", pg.UUID(as_uuid=True), sa.ForeignKey("platform_admins.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_platform_admin_password_reset_tokens_platform_admin_id",
        "platform_admin_password_reset_tokens", ["platform_admin_id"],
    )
    op.create_index(
        "ix_platform_admin_password_reset_tokens_token_hash",
        "platform_admin_password_reset_tokens", ["token_hash"], unique=True,
    )


def downgrade() -> None:
    op.drop_table("platform_admin_password_reset_tokens")
