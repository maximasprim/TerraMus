import uuid
from datetime import date, datetime, timezone

from sqlalchemy import String, Numeric, Date, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, UUIDPKMixin, TimestampMixin

# Spec §6 status list - enforced at the application layer (service.py) rather than
# a DB enum, so new statuses can be added without a migration during early phases.
ANIMAL_STATUSES = (
    "active", "for_sale", "reserved", "sold", "transferred",
    "deceased", "missing", "quarantined", "archived",
)

# Terminal statuses that must exclude the animal from active-herd calculations
# (spec §52.7 - "Animal death must remove it from active herd calculations").
INACTIVE_STATUSES = ("sold", "transferred", "deceased", "archived")


class Animal(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "animals"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    farm_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("farms.id"), index=True)
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id"), nullable=True
    )
    dam_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("animals.id"), nullable=True)
    sire_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("animals.id"), nullable=True)

    animal_number: Mapped[str] = mapped_column(String(64), index=True)  # org-scoped, human-facing (spec §60)
    ear_tag: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rfid: Mapped[str | None] = mapped_column(String(64), nullable=True)

    species: Mapped[str] = mapped_column(String(32))       # cattle | sheep (extensible, spec §11)
    breed: Mapped[str | None] = mapped_column(String(64), nullable=True)
    category: Mapped[str | None] = mapped_column(String(32), nullable=True)  # dairy|beef|calf|... / ram|ewe|lamb
    sex: Mapped[str] = mapped_column(String(8))             # male | female
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)

    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    estimated_birth_date: Mapped[bool] = mapped_column(default=False)

    acquisition_date: Mapped[date] = mapped_column(Date)
    acquisition_method: Mapped[str] = mapped_column(String(32))  # purchased|born_on_farm|transferred_in|gifted
    acquisition_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    current_value: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    expected_sale_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)

    current_weight: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    target_weight: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)

    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    health_status: Mapped[str] = mapped_column(String(32), default="healthy")
    reproductive_status: Mapped[str | None] = mapped_column(String(32), nullable=True)

    source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    previous_owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    supplier: Mapped[str | None] = mapped_column(String(128), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    events: Mapped[list["AnimalEvent"]] = relationship(
        back_populates="animal", cascade="all, delete-orphan",
        order_by="AnimalEvent.event_at", lazy="selectin",
    )
    weights: Mapped[list["WeightRecord"]] = relationship(
        back_populates="animal", cascade="all, delete-orphan",
        order_by="WeightRecord.recorded_at", lazy="selectin",
    )
    movements: Mapped[list["Movement"]] = relationship(
        back_populates="animal", cascade="all, delete-orphan",
        order_by="Movement.moved_at", lazy="selectin",
    )


class AnimalEvent(Base, UUIDPKMixin):
    """Immutable lifecycle timeline entry (spec §7). Append-only - no update/delete
    route exists, mirroring the audit_logs pattern from Phase 1."""
    __tablename__ = "animal_events"

    animal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("animals.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(64))  # e.g. acquired, vaccinated, weighed, listed, sold, milestone:*
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    animal: Mapped["Animal"] = relationship(back_populates="events")


class WeightRecord(Base, UUIDPKMixin):
    __tablename__ = "weight_records"

    animal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("animals.id"), index=True)
    weight_kg: Mapped[float] = mapped_column(Numeric(8, 2))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    animal: Mapped["Animal"] = relationship(back_populates="weights")


class Movement(Base, UUIDPKMixin):
    """Location change record (spec §10). Movements are append-only - the animal's
    current `location_id` is updated alongside, but history is preserved
    (spec §52.8: 'Transfers must preserve historical location data')."""
    __tablename__ = "movements"

    animal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("animals.id"), index=True)
    from_location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id"), nullable=True
    )
    to_location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("locations.id"))
    moved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    authorized_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    animal: Mapped["Animal"] = relationship(back_populates="movements")
