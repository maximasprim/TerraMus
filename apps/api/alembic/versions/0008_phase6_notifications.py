"""Phase 6: notifications, notification_preferences

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-10

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(16), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.String(500), nullable=False),
        sa.Column("related_entity_type", sa.String(32), nullable=True),
        sa.Column("related_entity_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("is_read", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "category in ('health','breeding','inventory','orders','payments','system')",
            name="valid_notification_category",
        ),
    )
    op.create_index("ix_notifications_organization_id", "notifications", ["organization_id"])
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_is_read", "notifications", ["is_read"])

    op.create_table(
        "notification_preferences",
        sa.Column("user_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("category", sa.String(16), primary_key=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_table("notification_preferences")
    op.drop_table("notifications")
