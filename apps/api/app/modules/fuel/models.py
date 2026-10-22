import uuid
from datetime import date, datetime, timezone

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UUIDPKMixin


class FuelLog(Base, UUIDPKMixin):
    __tablename__ = "fuel_logs"
    __table_args__ = (CheckConstraint("litres > 0 and cost >= 0", name="valid_amounts"),)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("assets.id"), index=True)
    farm_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("farms.id"), nullable=True)
    log_date: Mapped[date] = mapped_column(Date, index=True)
    litres: Mapped[float] = mapped_column(Numeric(8, 2))
    cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    meter_reading: Mapped[float | None] = mapped_column(Numeric(12, 1), nullable=True)     # hours or km
    purpose: Mapped[str | None] = mapped_column(String(120), nullable=True)
    activity: Mapped[str | None] = mapped_column(String(24), nullable=True)
    driver: Mapped[str | None] = mapped_column(String(120), nullable=True)
    finance_transaction_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
