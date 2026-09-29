import uuid
from datetime import date, datetime, timezone

from sqlalchemy import String, Integer, Date, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, UUIDPKMixin, TimestampMixin

BREEDING_METHODS = ("natural", "artificial_insemination")
PREGNANCY_STATUSES = ("bred", "confirmed_pregnant", "not_pregnant", "delivered", "aborted")
PREGNANCY_CHECK_RESULTS = ("confirmed", "not_pregnant", "inconclusive")


class BreedingRecord(Base, UUIDPKMixin, TimestampMixin):
    """Spec §7 (Breeding & Genetics Service): mating, AI, pregnancy, delivery,
    lineage. One row per mating/insemination event."""
    __tablename__ = "breeding_records"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    dam_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("animals.id"), index=True)
    sire_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("animals.id"), nullable=True)
    sire_external: Mapped[str | None] = mapped_column(String(255), nullable=True)  # e.g. AI straw/bull ID off-farm

    method: Mapped[str] = mapped_column(String(32))
    mating_date: Mapped[date] = mapped_column(Date)
    expected_delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    pregnancy_status: Mapped[str] = mapped_column(String(32), default="bred", index=True)

    actual_delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    offspring_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    recorded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    pregnancy_checks: Mapped[list["PregnancyCheck"]] = relationship(
        back_populates="breeding_record", cascade="all, delete-orphan",
        order_by="PregnancyCheck.check_date", lazy="selectin",
    )


class PregnancyCheck(Base, UUIDPKMixin):
    """Append-only, like the other historical-fact tables."""
    __tablename__ = "pregnancy_checks"

    breeding_record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("breeding_records.id"), index=True
    )
    check_date: Mapped[date] = mapped_column(Date)
    result: Mapped[str] = mapped_column(String(16))
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    performed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    breeding_record: Mapped["BreedingRecord"] = relationship(back_populates="pregnancy_checks")
