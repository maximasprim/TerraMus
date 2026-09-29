import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Numeric, Boolean, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, UUIDPKMixin, TimestampMixin

SUBSCRIPTION_STATUSES = ("trialing", "active", "past_due", "cancelled")
SUBSCRIPTION_PAYMENT_STATUSES = ("initiated", "pending", "successful", "failed")


class SubscriptionTier(Base, UUIDPKMixin, TimestampMixin):
    """A billing plan/tier a tenant can be on. Deliberately separate from any
    per-org RBAC role (identity.models.Role) - a tier gates plan-level
    limits (seats, animal count) and pricing, not in-app permissions."""
    __tablename__ = "subscription_tiers"

    name: Mapped[str] = mapped_column(String(64))
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    monthly_price_kes: Mapped[float] = mapped_column(Numeric(12, 2))
    max_users: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None = unlimited
    max_animals: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None = unlimited
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)  # False = no longer offered to new subscribers


class Subscription(Base, UUIDPKMixin, TimestampMixin):
    """One row per organization - its current billing plan and period. This
    table is entirely additive: nothing on `organizations` changes, and
    every existing tenant query is unaffected. Rows are created lazily (see
    billing/service.py get_or_create_subscription) the first time an org's
    subscription is looked at, rather than at org-registration time, so
    identity.service.register_organization needs no changes either."""
    __tablename__ = "subscriptions"
    __table_args__ = (UniqueConstraint("organization_id", name="uq_subscriptions_organization_id"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    tier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("subscription_tiers.id"))
    status: Mapped[str] = mapped_column(String(16), default="trialing", index=True)
    current_period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False)

    tier: Mapped["SubscriptionTier"] = relationship(lazy="selectin")


class SubscriptionPayment(Base, UUIDPKMixin, TimestampMixin):
    """Mirrors app.modules.payments.models.Payment's shape and idempotency
    pattern exactly, but for subscription billing rather than order
    payments - kept as a separate table rather than reusing `payments`
    because `payments.order_id` is a required (non-nullable) FK to
    `orders.id`, and a subscription payment has no order. Reuses the SAME
    PaymentProvider abstraction (app.modules.payments.providers.get_provider)
    and the same MpesaDarajaProvider - no new M-Pesa integration code, just a
    new place to record the result."""
    __tablename__ = "subscription_payments"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    subscription_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("subscriptions.id"), index=True)
    tier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("subscription_tiers.id"))
    provider: Mapped[str] = mapped_column(String(16), default="mpesa", index=True)
    provider_reference: Mapped[str] = mapped_column(String(128), index=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(8), default="KES")
    status: Mapped[str] = mapped_column(String(16), default="initiated", index=True)
    initiated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payment_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class SubscriptionPaymentWebhookEvent(Base, UUIDPKMixin):
    """Append-only idempotency log, identical pattern to
    payments.models.PaymentWebhookEvent - a duplicate (provider, event_id)
    is rejected at the DB level by the unique constraint below, not just an
    application-level check (see billing/service.py handle_mpesa_webhook)."""
    __tablename__ = "subscription_payment_webhook_events"
    __table_args__ = (
        UniqueConstraint("provider", "event_id", name="uq_subscription_payment_webhook_events_provider_event_id"),
    )

    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscription_payments.id"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(16))
    event_id: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16))
    raw_payload: Mapped[dict] = mapped_column(JSONB)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
