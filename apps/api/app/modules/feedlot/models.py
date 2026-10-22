import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin, UUIDPKMixin

SEX_CLASSES = ("bull", "steer", "heifer", "mixed")
EXIT_TYPES = ("sold", "culled", "died")
COSTING_KINDS = ("settings", "recipe", "enterprise_budget", "ration_plan", "overhead_pool", "land_use")


class IntakeBatch(Base, UUIDPKMixin, TimestampMixin):
    """A cohort of animals received together (worksheet 'BATCH n'). Carries the
    landed purchase cost that is averaged across its head (worksheet ' PROFITABILITY ')."""
    __tablename__ = "intake_batches"
    __table_args__ = (UniqueConstraint("organization_id", "batch_number"),
                      CheckConstraint("sex_class in ('bull','steer','heifer','mixed')", name="valid_sex_class"))

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    farm_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("farms.id"), nullable=True)
    batch_number: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(160))
    delivered_on: Mapped[date] = mapped_column(Date)
    source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    sex_class: Mapped[str] = mapped_column(String(16), default="bull")
    head_purchased: Mapped[int] = mapped_column(Integer, default=0)
    purchase_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    transport_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    other_fees: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    handlers_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def landed_cost(self) -> float:
        return float(self.purchase_cost or 0) + float(self.transport_cost or 0) + float(self.other_fees or 0) + float(self.handlers_cost or 0)

    @property
    def landed_cost_per_head(self) -> float:
        return round(self.landed_cost / self.head_purchased, 2) if self.head_purchased else 0.0


class SaleBatch(Base, UUIDPKMixin, TimestampMixin):
    """A dispatch day (worksheet 'Sales weight Batch n'). Not the same as an intake
    batch: one sale batch mixes bulls from several intake batches."""
    __tablename__ = "sale_batches"
    __table_args__ = (UniqueConstraint("organization_id", "batch_number"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    batch_number: Mapped[int] = mapped_column(Integer)
    sold_on: Mapped[date] = mapped_column(Date)
    price_per_kg: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    buyer_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class FeedlotAnimal(Base, UUIDPKMixin):
    """Links an existing Animal to its intake batch without touching the animals table."""
    __tablename__ = "feedlot_animals"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    animal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("animals.id"), unique=True)
    intake_batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("intake_batches.id"), index=True)
    received_on: Mapped[date] = mapped_column(Date)
    entry_weight_kg: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    legacy_tag: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FeedlotExit(Base, UUIDPKMixin):
    """How an animal left the feedlot: sold, culled or died. Culls/deaths carry no
    revenue so their purchase + feed + overhead cost shows up as a loss."""
    __tablename__ = "feedlot_exits"
    __table_args__ = (CheckConstraint("exit_type in ('sold','culled','died')", name="valid_exit_type"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    animal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("animals.id"), unique=True)
    exit_type: Mapped[str] = mapped_column(String(16))
    exit_date: Mapped[date] = mapped_column(Date)
    sale_batch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sale_batches.id"), nullable=True, index=True)
    exit_weight_kg: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    price_per_kg: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True)
    salesperson: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class WeighSession(Base, UUIDPKMixin):
    """Metadata for one weigh day (which scale, how many head)."""
    __tablename__ = "weigh_sessions"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    farm_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("farms.id"), nullable=True)
    weighed_on: Mapped[date] = mapped_column(Date, index=True)
    scale_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    head_count: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class CostingDocument(Base, UUIDPKMixin, TimestampMixin):
    """Configuration-style costing documents stored as JSON: feed recipes, fodder
    enterprise budgets, ration plans, overhead pools, land use, feedlot settings."""
    __tablename__ = "costing_documents"
    __table_args__ = (UniqueConstraint("organization_id", "kind", "name"),
                      CheckConstraint("kind in ('settings','recipe','enterprise_budget','ration_plan','overhead_pool','land_use')", name="valid_kind"))

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    name: Mapped[str] = mapped_column(String(160))
    data: Mapped[dict] = mapped_column(JSONB, default=dict)
