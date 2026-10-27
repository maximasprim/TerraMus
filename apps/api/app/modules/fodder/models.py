import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin, UUIDPKMixin

CATEGORIES = ("hay", "silage", "haylage", "straw", "green_chop", "other")
COST_CATEGORIES = ("seed", "fertilizer", "chemicals", "labour", "fuel", "machinery_hire", "irrigation", "transport", "packaging", "other")
MOVEMENT_TYPES = ("harvest", "purchase", "issue", "sale", "loss", "count_adjust")
_now = lambda: datetime.now(timezone.utc)
_uuid = lambda **kw: mapped_column(UUID(as_uuid=True), **kw)


class FodderProduct(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "fodder_products"
    __table_args__ = (UniqueConstraint("organization_id", "name"), CheckConstraint("kg_per_unit > 0", name="positive_unit_weight"),
                      CheckConstraint("category in ('hay','silage','haylage','straw','green_chop','other')", name="valid_category"))
    organization_id: Mapped[uuid.UUID] = _uuid(index=True)
    name: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(16), default="hay")
    unit_label: Mapped[str] = mapped_column(String(16), default="bale")
    kg_per_unit: Mapped[float] = mapped_column(Numeric(10, 3), default=1)
    dry_matter_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    reorder_days: Mapped[int] = mapped_column(Integer, default=14)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class FodderPrice(Base, UUIDPKMixin):
    """What it would cost to BUY this fodder, from a date on (the 'would have bought' price)."""
    __tablename__ = "fodder_prices"
    __table_args__ = (UniqueConstraint("product_id", "effective_from"), CheckConstraint("price_per_kg > 0", name="positive_price"))
    organization_id: Mapped[uuid.UUID] = _uuid(index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fodder_products.id"))
    effective_from: Mapped[date] = mapped_column(Date)
    price_per_kg: Mapped[float] = mapped_column(Numeric(10, 4))
    source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class FodderPlot(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "fodder_plots"
    __table_args__ = (UniqueConstraint("organization_id", "name"), CheckConstraint("acres > 0", name="positive_acres"),
                      CheckConstraint("status in ('active','resting','retired')", name="valid_status"))
    organization_id: Mapped[uuid.UUID] = _uuid(index=True)
    farm_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("farms.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(120))
    acres: Mapped[float] = mapped_column(Numeric(8, 2))
    irrigated: Mapped[bool] = mapped_column(Boolean, default=False)
    crop: Mapped[str | None] = mapped_column(String(80), nullable=True)
    established_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="active")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class FodderCycle(Base, UUIDPKMixin, TimestampMixin):
    """One crop on one plot over one season: the unit that costs and harvests attach to."""
    __tablename__ = "fodder_cycles"
    __table_args__ = (CheckConstraint("acres > 0", name="positive_acres"), CheckConstraint("status in ('open','closed')", name="valid_status"),
                      CheckConstraint("end_date is null or end_date >= start_date", name="valid_dates"))
    organization_id: Mapped[uuid.UUID] = _uuid(index=True)
    plot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fodder_plots.id"), index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fodder_products.id"))
    label: Mapped[str] = mapped_column(String(120))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    acres: Mapped[float] = mapped_column(Numeric(8, 2))
    status: Mapped[str] = mapped_column(String(8), default="open")
    budget_name: Mapped[str | None] = mapped_column(String(160), nullable=True)      # an enterprise budget in Feedlot > Costing, for variance
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class FodderCost(Base, UUIDPKMixin):
    __tablename__ = "fodder_costs"
    __table_args__ = (CheckConstraint("amount > 0", name="positive_amount"),)
    organization_id: Mapped[uuid.UUID] = _uuid(index=True)
    cycle_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fodder_cycles.id"), index=True)
    cost_date: Mapped[date] = mapped_column(Date)
    category: Mapped[str] = mapped_column(String(16))
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    finance_transaction_id: Mapped[uuid.UUID | None] = _uuid(nullable=True)
    created_by: Mapped[uuid.UUID | None] = _uuid(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class FodderInvestment(Base, UUIDPKMixin, TimestampMixin):
    """Establishment or shared assets (land preparation, bunker, baler) amortised straight-line over their life."""
    __tablename__ = "fodder_investments"
    __table_args__ = (CheckConstraint("cost > 0 and salvage_value >= 0 and salvage_value <= cost", name="valid_amounts"),
                      CheckConstraint("life_years > 0", name="positive_life"))
    organization_id: Mapped[uuid.UUID] = _uuid(index=True)
    plot_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("fodder_plots.id"), nullable=True)   # None = shared
    name: Mapped[str] = mapped_column(String(160))
    cost: Mapped[float] = mapped_column(Numeric(12, 2))
    salvage_value: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    in_service_on: Mapped[date] = mapped_column(Date)
    life_years: Mapped[float] = mapped_column(Numeric(5, 2))
    disposed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class FodderHarvest(Base, UUIDPKMixin):
    __tablename__ = "fodder_harvests"
    __table_args__ = (CheckConstraint("quantity > 0 and kg > 0", name="positive_quantity"),
                      CheckConstraint("quality is null or quality in ('good','fair','poor')", name="valid_quality"))
    organization_id: Mapped[uuid.UUID] = _uuid(index=True)
    cycle_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fodder_cycles.id"), index=True)
    harvest_date: Mapped[date] = mapped_column(Date)
    quantity: Mapped[float] = mapped_column(Numeric(12, 2))      # in the product's unit (bales, tonnes ...)
    kg: Mapped[float] = mapped_column(Numeric(14, 2))
    quality: Mapped[str | None] = mapped_column(String(8), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[uuid.UUID | None] = _uuid(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class FodderMovement(Base, UUIDPKMixin):
    """The stock ledger. Quantities are in kg (signed): + in, - out. Never edited: a mistake is corrected by a count."""
    __tablename__ = "fodder_movements"
    __table_args__ = (CheckConstraint("movement_type in ('harvest','purchase','issue','sale','loss','count_adjust')", name="valid_type"),
                      CheckConstraint("kg_delta <> 0", name="nonzero_quantity"))
    organization_id: Mapped[uuid.UUID] = _uuid(index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fodder_products.id"), index=True)
    movement_date: Mapped[date] = mapped_column(Date, index=True)
    movement_type: Mapped[str] = mapped_column(String(12))
    kg_delta: Mapped[float] = mapped_column(Numeric(14, 2))
    value: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)          # purchase cost or sale proceeds
    reference_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    reference_id: Mapped[uuid.UUID | None] = _uuid(nullable=True)
    destination_type: Mapped[str | None] = mapped_column(String(12), nullable=True)
    destination_id: Mapped[uuid.UUID | None] = _uuid(nullable=True)
    destination_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[uuid.UUID | None] = _uuid(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
