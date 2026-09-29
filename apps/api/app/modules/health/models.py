import uuid
from datetime import date, datetime, timezone

from sqlalchemy import String, Numeric, Date, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, UUIDPKMixin

# Spec §5 (Animal Health Service): vaccinations, treatments, deworming,
# examinations, injuries, lab results, vet visits.
RECORD_TYPES = (
    "vaccination", "treatment", "deworming", "examination",
    "injury", "lab_result", "vet_visit", "prescription",
)


class HealthRecord(Base, UUIDPKMixin):
    """Append-only, like AnimalEvent/WeightRecord/Movement - a veterinary record
    is a historical fact; corrections are made by adding a new record, not
    editing history (spec §77: 'traceable historically')."""
    __tablename__ = "health_records"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    animal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("animals.id"), index=True)

    record_type: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    diagnosis: Mapped[str | None] = mapped_column(String(255), nullable=True)
    medication: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dosage: Mapped[str | None] = mapped_column(String(128), nullable=True)
    administered_by: Mapped[str | None] = mapped_column(String(255), nullable=True)  # vet/staff name (free text)
    cost: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)

    performed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    follow_up_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    follow_up_completed: Mapped[bool] = mapped_column(default=False)

    extra: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    recorded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
