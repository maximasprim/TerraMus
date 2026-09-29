"""Platform admin (superuser) + billing/subscriptions (M-Pesa Daraja)

Purely additive: four new tables, plus one new nullable-with-default column
on the existing `organizations` table. Nothing existing is altered or
dropped, so this cannot break any current query, model, or test.

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-19

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- organizations.is_suspended (additive column, safe default) -------
    op.add_column(
        "organizations",
        sa.Column("is_suspended", sa.Boolean, nullable=False, server_default=sa.false()),
    )

    # --- platform_admins ----------------------------------------------------
    op.create_table(
        "platform_admins",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_platform_admins_email", "platform_admins", ["email"], unique=True)

    # --- subscription_tiers --------------------------------------------------
    op.create_table(
        "subscription_tiers",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("monthly_price_kes", sa.Numeric(12, 2), nullable=False),
        sa.Column("max_users", sa.Integer, nullable=True),
        sa.Column("max_animals", sa.Integer, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_subscription_tiers_slug", "subscription_tiers", ["slug"], unique=True)

    # --- subscriptions --------------------------------------------------------
    op.create_table(
        "subscriptions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("tier_id", pg.UUID(as_uuid=True), sa.ForeignKey("subscription_tiers.id"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="trialing"),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", name="uq_subscriptions_organization_id"),
    )
    op.create_index("ix_subscriptions_organization_id", "subscriptions", ["organization_id"])
    op.create_index("ix_subscriptions_status", "subscriptions", ["status"])

    # --- subscription_payments -------------------------------------------------
    op.create_table(
        "subscription_payments",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("subscription_id", pg.UUID(as_uuid=True), sa.ForeignKey("subscriptions.id"), nullable=False),
        sa.Column("tier_id", pg.UUID(as_uuid=True), sa.ForeignKey("subscription_tiers.id"), nullable=False),
        sa.Column("provider", sa.String(16), nullable=False, server_default="mpesa"),
        sa.Column("provider_reference", sa.String(128), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="KES"),
        sa.Column("status", sa.String(16), nullable=False, server_default="initiated"),
        sa.Column("initiated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payment_metadata", pg.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_subscription_payments_organization_id", "subscription_payments", ["organization_id"])
    op.create_index("ix_subscription_payments_subscription_id", "subscription_payments", ["subscription_id"])
    op.create_index("ix_subscription_payments_provider", "subscription_payments", ["provider"])
    op.create_index("ix_subscription_payments_provider_reference", "subscription_payments", ["provider_reference"])
    op.create_index("ix_subscription_payments_status", "subscription_payments", ["status"])

    # --- subscription_payment_webhook_events -------------------------------------
    op.create_table(
        "subscription_payment_webhook_events",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("payment_id", pg.UUID(as_uuid=True), sa.ForeignKey("subscription_payments.id"), nullable=True),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("event_id", sa.String(255), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("raw_payload", pg.JSONB, nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "provider", "event_id", name="uq_subscription_payment_webhook_events_provider_event_id"
        ),
    )


def downgrade() -> None:
    op.drop_table("subscription_payment_webhook_events")
    op.drop_table("subscription_payments")
    op.drop_table("subscriptions")
    op.drop_table("subscription_tiers")
    op.drop_table("platform_admins")
    op.drop_column("organizations", "is_suspended")
