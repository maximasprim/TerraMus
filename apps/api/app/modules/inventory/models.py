import uuid
from datetime import date, datetime, timezone

from sqlalchemy import String, Numeric, Date, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, UUIDPKMixin, TimestampMixin

ITEM_CATEGORIES = ("feed", "medicine", "vaccine", "supply", "equipment", "consumable")
MOVEMENT_TYPES = (
    "purchase", "sale", "consumption", "transfer", "adjustment",
    "wastage", "return", "expired", "opening_balance",
)
# Spec §14 - direction each movement type applies to the running balance.
# "adjustment" is the one type where the caller supplies a signed delta directly.
IN_TYPES = {"purchase", "opening_balance", "return"}
OUT_TYPES = {"consumption", "wastage", "expired", "sale", "transfer"}


class InventoryItem(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "inventory_items"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    farm_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("farms.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(32), index=True)
    unit: Mapped[str] = mapped_column(String(16))  # kg|l|bag|unit|...
    reorder_level: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    allow_negative_stock: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    movements: Mapped[list["StockMovement"]] = relationship(
        back_populates="item", cascade="all, delete-orphan",
        order_by="StockMovement.moved_at", lazy="selectin",
    )


class StockMovement(Base, UUIDPKMixin):
    """Append-only ledger entry (spec §14 - 'maintain a complete inventory ledger,
    do not simply overwrite stock quantities'). Current stock is always the SUM
    of this table, never a mutable counter."""
    __tablename__ = "stock_movements"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("inventory_items.id"), index=True)

    movement_type: Mapped[str] = mapped_column(String(32), index=True)
    quantity: Mapped[float] = mapped_column(Numeric(12, 2))  # signed: +in / -out, computed by the service
    unit_cost: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    batch_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    animal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)  # feed-cost-per-animal
    reference: Mapped[str | None] = mapped_column(String(255), nullable=True)  # PO number, invoice, etc.
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)

    performed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    moved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    item: Mapped["InventoryItem"] = relationship(back_populates="movements")
