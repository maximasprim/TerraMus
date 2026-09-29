import uuid
from datetime import date, datetime, timezone

from sqlalchemy import String, Numeric, Date, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, UUIDPKMixin, TimestampMixin

PRICING_TYPES = ("fixed", "negotiable", "price_on_request")
RESERVATION_STATUSES = ("active", "completed", "expired", "cancelled")

# Spec §19 order lifecycle, plus terminal side-states.
ORDER_STATUSES = (
    "pending", "payment_pending", "paid", "processing", "ready_for_fulfillment",
    "dispatched", "delivered", "completed", "cancelled", "refunded",
    "partially_refunded", "failed",
)


class Listing(Base, UUIDPKMixin, TimestampMixin):
    """Spec §17 - one active listing per product (enforced by partial unique
    indexes in the migrations: one per animal_id, one per crop_planting_id).
    Exactly one of animal_id/crop_planting_id is set (CHECK constraint,
    migration 0021) - a listing sells either one specific animal, or some
    quantity of a crop planting's produce, never both."""
    __tablename__ = "listings"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    animal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("animals.id"), nullable=True, index=True)
    crop_planting_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crop_plantings.id"), nullable=True, index=True
    )
    slug: Mapped[str] = mapped_column(String(255), index=True)  # spec §45: /livestock/dairy-cattle/holstein-cow-001
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    pricing_type: Mapped[str] = mapped_column(String(32), default="fixed")
    price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)  # per-unit price for crop-produce listings
    unit: Mapped[str | None] = mapped_column(String(16), nullable=True)  # kg|bags|crates… - only set for crop-produce listings
    low_stock_threshold: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)  # crop-produce only - alert when available quantity falls at/below this
    featured: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class Reservation(Base, UUIDPKMixin, TimestampMixin):
    """Spec §18. `status` tracks the reservation's own lifecycle; the animal's
    own `status` field (Phase 2) is what actually blocks a second buyer -
    they're kept in sync by commerce/service.py, not duplicated as the source
    of truth."""
    __tablename__ = "reservations"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    animal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("animals.id"), index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), index=True)

    reservation_date: Mapped[date] = mapped_column(Date)
    expiry_date: Mapped[date] = mapped_column(Date)
    deposit_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class Order(Base, UUIDPKMixin, TimestampMixin):
    """Spec §19."""
    __tablename__ = "orders"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    delivery_option: Mapped[str] = mapped_column(String(16), default="pickup")  # pickup|delivery
    delivery_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    total_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", lazy="selectin",
    )
    status_events: Mapped[list["OrderStatusEvent"]] = relationship(
        back_populates="order", cascade="all, delete-orphan",
        order_by="OrderStatusEvent.changed_at", lazy="selectin",
    )


class OrderItem(Base, UUIDPKMixin):
    """Exactly one of animal_id/crop_planting_id is set (CHECK constraint,
    migration 0021). `quantity` defaults to 1 - meaningless-but-harmless for
    an animal item (always exactly one unit), meaningful for a crop-produce
    item (how much was bought, in the listing's `unit`)."""
    __tablename__ = "order_items"

    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id"), index=True)
    animal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("animals.id"), nullable=True, index=True)
    crop_planting_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crop_plantings.id"), nullable=True, index=True
    )
    quantity: Mapped[float] = mapped_column(Numeric(12, 2), default=1)
    price: Mapped[float] = mapped_column(Numeric(12, 2))  # price snapshot at time of order - per-unit for crop items

    order: Mapped["Order"] = relationship(back_populates="items")


class OrderStatusEvent(Base, UUIDPKMixin):
    """Append-only - every order status transition is logged (spec §19: 'Every
    status transition should be logged')."""
    __tablename__ = "order_status_events"

    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    order: Mapped["Order"] = relationship(back_populates="status_events")
