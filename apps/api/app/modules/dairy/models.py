import uuid
from datetime import date, datetime, timezone

from sqlalchemy import String, Numeric, Date, DateTime, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, UUIDPKMixin

MILK_SESSIONS = ("morning", "midday", "evening")


class LactationCycle(Base, UUIDPKMixin):
    """Spec §8 (Dairy Production Service): one cycle per calving-to-dry-off period."""
    __tablename__ = "lactation_cycles"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    animal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("animals.id"), index=True)
    start_date: Mapped[date] = mapped_column(Date)  # calving date
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # dry-off date
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    records: Mapped[list["MilkProductionRecord"]] = relationship(
        back_populates="lactation_cycle", order_by="MilkProductionRecord.production_date", lazy="selectin",
    )


class MilkProductionRecord(Base, UUIDPKMixin):
    __tablename__ = "milk_production_records"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    animal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("animals.id"), index=True)
    lactation_cycle_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lactation_cycles.id"), nullable=True
    )

    production_date: Mapped[date] = mapped_column(Date, index=True)
    session: Mapped[str] = mapped_column(String(16))  # morning|midday|evening
    quantity_liters: Mapped[float] = mapped_column(Numeric(6, 2))
    rejected: Mapped[bool] = mapped_column(Boolean, default=False)
    rejection_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    recorded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    lactation_cycle: Mapped["LactationCycle"] = relationship(back_populates="records")
