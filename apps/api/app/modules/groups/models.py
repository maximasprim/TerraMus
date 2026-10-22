import uuid
from datetime import date, datetime, timezone

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin, UUIDPKMixin

SPECIES = ("poultry", "rabbits", "fish", "pigs", "other")
RECORD_TYPES = ("mortality", "cull", "production", "feed", "weight_sample", "sale", "addition")


class AnimalGroup(Base, UUIDPKMixin, TimestampMixin):
    """A flock / pond / hutch managed by headcount rather than individual animals."""
    __tablename__ = "animal_groups"
    __table_args__ = (UniqueConstraint("organization_id", "code"),
                      CheckConstraint("species in ('poultry','rabbits','fish','pigs','other')", name="valid_species"),
                      CheckConstraint("status in ('active','closed')", name="valid_status"),
                      CheckConstraint("initial_count > 0 and current_count >= 0", name="valid_counts"))
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    farm_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("farms.id"), nullable=True)
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(160))
    species: Mapped[str] = mapped_column(String(16))
    purpose: Mapped[str | None] = mapped_column(String(24), nullable=True)
    breed: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source: Mapped[str | None] = mapped_column(String(160), nullable=True)
    start_date: Mapped[date] = mapped_column(Date)
    initial_count: Mapped[int] = mapped_column(Integer)
    current_count: Mapped[int] = mapped_column(Integer)
    acquisition_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    status: Mapped[str] = mapped_column(String(12), default="active")
    closed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class GroupRecord(Base, UUIDPKMixin):
    __tablename__ = "group_records"
    __table_args__ = (CheckConstraint("record_type in ('mortality','cull','production','feed','weight_sample','sale','addition')", name="valid_record_type"),
                      CheckConstraint("quantity >= 0", name="non_negative_quantity"))
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("animal_groups.id"), index=True)
    record_date: Mapped[date] = mapped_column(Date, index=True)
    record_type: Mapped[str] = mapped_column(String(16))
    quantity: Mapped[float] = mapped_column(Numeric(12, 2))
    unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    value: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    avg_weight_kg: Mapped[float | None] = mapped_column(Numeric(8, 3), nullable=True)
    product: Mapped[str | None] = mapped_column(String(24), nullable=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
