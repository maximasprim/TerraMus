import uuid
from datetime import date, datetime, timezone

from sqlalchemy import String, Numeric, Date, DateTime, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UUIDPKMixin

TRANSACTION_TYPES = ("income", "expense")
# Spec §23 category list.
TRANSACTION_CATEGORIES = (
    "livestock_sale", "milk_sale", "other_revenue",
    "livestock_acquisition", "feed", "veterinary", "labour", "transport",
    "utilities", "maintenance", "equipment", "marketing", "payment_processing_fee", "other_expense",
)


class FinanceTransaction(Base, UUIDPKMixin):
    """Spec §23. Append-only ledger - corrections are new entries (e.g. a
    reversing transaction), never edits, same principle as the inventory
    stock ledger (§14)."""
    __tablename__ = "finance_transactions"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    transaction_type: Mapped[str] = mapped_column(String(16), index=True)  # income | expense
    category: Mapped[str] = mapped_column(String(32), index=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(8), default="KES")
    reference_type: Mapped[str | None] = mapped_column(String(32), nullable=True)  # order|animal|payment|manual
    reference_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    transaction_date: Mapped[date] = mapped_column(Date, index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class Invoice(Base, UUIDPKMixin):
    """Spec §59. `invoice_number` is sequential per organization (via
    InvoiceCounter below), not globally - matches spec §60's per-org
    'invoice prefix' configuration concept."""
    __tablename__ = "invoices"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    invoice_number: Mapped[str] = mapped_column(String(32), index=True)
    subtotal: Mapped[float] = mapped_column(Numeric(12, 2))
    tax_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    total: Mapped[float] = mapped_column(Numeric(12, 2))
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InvoiceCounter(Base):
    """One row per organization; incremented under a row lock to hand out
    gap-free sequential invoice numbers safely under concurrent order-paid
    events (same locking pattern as commerce/service.py's animal row locks)."""
    __tablename__ = "invoice_counters"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    next_number: Mapped[int] = mapped_column(Integer, default=1)
