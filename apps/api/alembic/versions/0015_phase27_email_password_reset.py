"""Phase 27: email channel + password reset (spec 13/55/5)

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-06

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])
    op.create_index("ix_password_reset_tokens_token_hash", "password_reset_tokens", ["token_hash"], unique=True)

    op.create_table(
        "email_outbox",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("to_email", sa.String(255), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("body_text", sa.String(2000), nullable=False),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("accepted", sa.Boolean, nullable=False),
        sa.Column("related_user_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_email_outbox_organization_id", "email_outbox", ["organization_id"])
    op.create_index("ix_email_outbox_to_email", "email_outbox", ["to_email"])


def downgrade() -> None:
    op.drop_table("email_outbox")
    op.drop_table("password_reset_tokens")
