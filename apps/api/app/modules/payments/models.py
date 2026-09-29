import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Numeric, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, UUIDPKMixin, TimestampMixin

PAYMENT_PROVIDERS = ("mock", "mpesa", "stripe")
PAYMENT_STATUSES = ("initiated", "pending", "successful", "failed", "cancelled", "refunded", "partially_refunded")


class Payment(Base, UUIDPKMixin, TimestampMixin):
    """Spec §11/§20. Status is only ever advanced by a verified webhook
    callback (payments/service.py handle_webhook) - never by a direct client
    request, per spec §20/§65.10."""
    __tablename__ = "payments"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id"), index=True)
    provider: Mapped[str] = mapped_column(String(16), index=True)
    provider_reference: Mapped[str] = mapped_column(String(128), index=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(8), default="KES")
    status: Mapped[str] = mapped_column(String(16), default="initiated", index=True)
    initiated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payment_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    webhook_events: Mapped[list["PaymentWebhookEvent"]] = relationship(
        back_populates="payment", cascade="all, delete-orphan", lazy="selectin",
    )


class PaymentWebhookEvent(Base, UUIDPKMixin):
    """Append-only log of every received callback, keyed by the provider's own
    event id - the idempotency mechanism (spec §20: 'never process the same
    callback twice'). A duplicate insert on (provider, event_id) is rejected
    by a DB unique constraint, not just an application-layer check."""
    __tablename__ = "payment_webhook_events"

    payment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("payments.id"), nullable=True)
    provider: Mapped[str] = mapped_column(String(16))
    event_id: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16))
    raw_payload: Mapped[dict] = mapped_column(JSONB)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    payment: Mapped["Payment"] = relationship(back_populates="webhook_events")
