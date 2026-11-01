import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin, UUIDPKMixin

CYCLE_STATUSES = ("planned", "running", "closed")
ENTERPRISES = ("feedlot", "fodder", "crops", "poultry", "fish", "rabbits", "training", "mixed")


class ProductionCycle(Base, UUIDPKMixin, TimestampMixin):
    """A named production run ("Cycle 1") that groups feedlot batches, finance, receivables, fuel, fodder,
    flocks, crops, training, stock movements and costing documents so every report can be sliced by it.

    Membership is explicit, never inferred from dates, because cycles can overlap (a new intake can arrive
    while the previous cycle's last bulls are still being sold)."""
    __tablename__ = "production_cycles"
    __table_args__ = (
        UniqueConstraint("organization_id", "cycle_number", name="uq_production_cycles_org_number"),
        UniqueConstraint("organization_id", "name", name="uq_production_cycles_org_name"),
        CheckConstraint("status in ('planned','running','closed')", name="ck_production_cycles_valid_status"),
        CheckConstraint("end_date is null or start_date is null or end_date >= start_date",
                        name="ck_production_cycles_valid_dates"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    farm_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("farms.id"), nullable=True)
    cycle_number: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(120))
    enterprise: Mapped[str] = mapped_column(String(24), default="feedlot")
    status: Mapped[str] = mapped_column(String(12), default="planned")
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    close_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
