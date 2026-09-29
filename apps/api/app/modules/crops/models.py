import uuid
from datetime import date, datetime, timezone

from sqlalchemy import String, Numeric, Boolean, Date, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, UUIDPKMixin, TimestampMixin

# Mirrors livestock/models.py ANIMAL_STATUSES: enforced at the application
# layer (service.py) rather than a DB enum, so new statuses can be added
# without a migration.
PLANTING_STATUSES = (
    "growing", "ready_for_harvest", "harvesting", "harvested",
    "fallow", "failed", "archived",
)

# Terminal/inactive statuses excluded from active-crop calculations, mirroring
# livestock's INACTIVE_STATUSES.
INACTIVE_PLANTING_STATUSES = ("harvested", "failed", "archived")


class CropPlanting(Base, UUIDPKMixin, TimestampMixin):
    """One planted plot/batch of a crop (the plant-production equivalent of
    livestock's Animal). For a perennial/bearing crop (tea, avocado, coffee,
    etc.) a single planting is harvested repeatedly over years via multiple
    HarvestRecord rows; for an annual crop it is typically harvested once
    then moved to a terminal status.
    """
    __tablename__ = "crop_plantings"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    farm_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("farms.id"), index=True)
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id"), nullable=True
    )

    planting_number: Mapped[str] = mapped_column(String(64), index=True)  # org-scoped, human-facing, like animal_number
    crop_type: Mapped[str] = mapped_column(String(32))  # e.g. tea | avocado | maize (extensible - see catalog.py)
    variety: Mapped[str | None] = mapped_column(String(64), nullable=True)  # e.g. "Hass" avocado, "Purple Napier"
    is_perennial: Mapped[bool] = mapped_column(Boolean, default=False)

    area_size: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    area_unit: Mapped[str] = mapped_column(String(16), default="acres")  # acres | hectares

    planting_date: Mapped[date] = mapped_column(Date)
    planting_method: Mapped[str | None] = mapped_column(String(32), nullable=True)  # seed|seedling|cutting|grafted
    expected_harvest_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    acquisition_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0)  # seeds/seedlings/land-prep cost
    current_value: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    expected_yield: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    yield_unit: Mapped[str | None] = mapped_column(String(16), nullable=True)  # kg|bags|crates|bunches|tonnes|stems

    status: Mapped[str] = mapped_column(String(24), default="growing", index=True)
    health_status: Mapped[str] = mapped_column(String(32), default="healthy")

    source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    supplier: Mapped[str | None] = mapped_column(String(128), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    events: Mapped[list["CropEvent"]] = relationship(
        back_populates="planting", cascade="all, delete-orphan",
        order_by="CropEvent.event_at", lazy="selectin",
    )
    harvests: Mapped[list["HarvestRecord"]] = relationship(
        back_populates="planting", cascade="all, delete-orphan",
        order_by="HarvestRecord.harvested_at", lazy="selectin",
    )


class CropEvent(Base, UUIDPKMixin):
    """Immutable lifecycle timeline entry - the crop equivalent of AnimalEvent
    (planted, fertilized, sprayed, pruned, harvested, milestone:*)."""
    __tablename__ = "crop_events"

    planting_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("crop_plantings.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    planting: Mapped["CropPlanting"] = relationship(back_populates="events")


class HarvestRecord(Base, UUIDPKMixin):
    """A single harvest event's yield - the crop equivalent of WeightRecord.
    A perennial planting accumulates many of these over its productive life
    (e.g. tea plucked every ~2 weeks); an annual crop typically has one."""
    __tablename__ = "harvest_records"

    planting_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("crop_plantings.id"), index=True)
    quantity: Mapped[float] = mapped_column(Numeric(12, 2))
    unit: Mapped[str] = mapped_column(String(16))  # kg|bags|crates|bunches|tonnes|stems
    quality_grade: Mapped[str | None] = mapped_column(String(32), nullable=True)
    harvested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    planting: Mapped["CropPlanting"] = relationship(back_populates="harvests")
