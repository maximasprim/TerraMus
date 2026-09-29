import uuid
from datetime import date, datetime

from sqlalchemy import String, Text, Numeric, Date, DateTime, ForeignKey, Boolean, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, UUIDPKMixin, TimestampMixin

# Spec §26 lifecycle: REQUEST -> APPROVAL -> PURCHASE ORDER -> RECEIVED -> INVOICED -> PAID,
# plus rejected/cancelled off-ramps from the pre-received states (mirrors the
# commerce order/animal state-machine pattern in modules/commerce/service.py).
PURCHASE_ORDER_STATUSES = (
    "requested", "approved", "ordered", "received", "invoiced", "paid",
    "rejected", "cancelled",
)


class Supplier(Base, UUIDPKMixin, TimestampMixin):
    """Spec §9/§26 supplier fields."""
    __tablename__ = "suppliers"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    name: Mapped[str] = mapped_column(String(255))
    contact_person: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tax_pin: Mapped[str | None] = mapped_column(String(64), nullable=True)  # spec §57 - KRA PIN, not hard-required
    products_supplied: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_terms: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    purchase_orders: Mapped[list["PurchaseOrder"]] = relationship(back_populates="supplier")


class PurchaseOrder(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "purchase_orders"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id"), index=True)
    po_number: Mapped[str] = mapped_column(String(32), index=True)  # per-org sequential, like Invoice (finance module)
    status: Mapped[str] = mapped_column(String(16), default="requested", index=True)
    order_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expected_delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    supplier: Mapped["Supplier"] = relationship(back_populates="purchase_orders")
    items: Mapped[list["PurchaseOrderItem"]] = relationship(
        back_populates="purchase_order", cascade="all, delete-orphan", lazy="selectin",
    )


class PurchaseOrderItem(Base, UUIDPKMixin):
    __tablename__ = "purchase_order_items"

    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_orders.id"), index=True
    )
    # Optional link to the inventory catalog: a PO line tied to a tracked
    # InventoryItem creates a real StockMovement on receipt (spec §26/§9);
    # a line left unlinked (e.g. a one-off service charge) does not.
    inventory_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inventory_items.id"), nullable=True
    )
    description: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[float] = mapped_column(Numeric(12, 2))
    unit_cost: Mapped[float] = mapped_column(Numeric(12, 2))

    purchase_order: Mapped["PurchaseOrder"] = relationship(back_populates="items")


class PurchaseOrderStatusEvent(Base, UUIDPKMixin):
    """Append-only status history - same pattern/trigger as
    commerce.OrderStatusEvent (spec §28: audit logs should not be editable)."""
    __tablename__ = "purchase_order_status_events"

    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_orders.id"), index=True
    )
    from_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    to_status: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PurchaseOrderCounter(Base):
    """Per-org gap-free PO numbering under a row lock - identical pattern to
    finance.InvoiceCounter (spec §60's per-org numbering-format concept)."""
    __tablename__ = "purchase_order_counters"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    next_number: Mapped[int] = mapped_column(Integer, default=1)
