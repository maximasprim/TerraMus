import uuid
from datetime import date, datetime, timezone

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UUIDPKMixin

ENTRY_TYPES = ("charge", "payment", "writeoff")
PAYMENT_METHODS = ("cash", "mpesa", "bank", "cheque", "other")
REFERENCE_TYPES = ("feedlot_sale", "training_enrolment", "crop_sale", "fodder_sale", "group_sale", "order", "manual")


class AccountEntry(Base, UUIDPKMixin):
    """Customer account ledger (credit sales). balance = charges - payments - write-offs.
    Entries are never edited: a mistake is corrected with a further entry."""
    __tablename__ = "account_entries"
    __table_args__ = (CheckConstraint("entry_type in ('charge','payment','writeoff')", name="valid_entry_type"),
                      CheckConstraint("amount > 0", name="positive_amount"))

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), index=True)
    entry_type: Mapped[str] = mapped_column(String(12))
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    entry_date: Mapped[date] = mapped_column(Date, index=True)
    reference_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    method: Mapped[str | None] = mapped_column(String(16), nullable=True)
    receipt_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    farm_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("farms.id"), nullable=True)
    activity: Mapped[str | None] = mapped_column(String(24), nullable=True)
    salesperson: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
