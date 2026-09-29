import uuid
from datetime import date

from sqlalchemy import String, Text, Date, Numeric, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, UUIDPKMixin, TimestampMixin

# Spec §15 examples: tractors, vehicles, pumps, generators, milking equipment,
# water systems, buildings, fences, tools, machinery. Kept as a free-text-ish
# category rather than a rigid enum so a farm can log something the spec
# didn't anticipate without a schema change - same trade-off livestock.species
# already makes for the same reason.
ASSET_TYPES = (
    "tractor", "vehicle", "pump", "generator", "milking_equipment",
    "water_system", "building", "fence", "tool", "machinery", "other",
)
ASSET_CONDITIONS = ("excellent", "good", "fair", "poor", "out_of_service")
ASSET_STATUSES = ("in_use", "in_storage", "under_maintenance", "disposed")
MAINTENANCE_TYPES = ("service", "repair", "inspection")


class Asset(Base, UUIDPKMixin, TimestampMixin):
    """Spec §15 farm asset/equipment record."""
    __tablename__ = "assets"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    asset_number: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(255))
    asset_type: Mapped[str] = mapped_column(String(32), index=True)
    serial_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="in_use", index=True)
    condition: Mapped[str] = mapped_column(String(16), default="good")

    acquisition_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    acquisition_cost: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    # Depreciation inputs - spec §15's "depreciation" is computed at read time
    # from these (see service.depreciated_value), not stored as a value that
    # would silently drift out of date. Nullable: a farm that doesn't want to
    # track depreciation for a given asset (e.g. a fence) just leaves these
    # unset and current_value falls back to acquisition_cost.
    useful_life_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salvage_value: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)

    warranty_expiry: Mapped[date | None] = mapped_column(Date, nullable=True)
    assigned_farm_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("farms.id"), nullable=True)
    assigned_location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id"), nullable=True
    )
    # Optional tie-in to Phase 12's Procurement module: an asset bought
    # through a tracked supplier can point back at it, the same optional-link
    # pattern as employees.Employee.user_id.
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    maintenance_records: Mapped[list["AssetMaintenanceRecord"]] = relationship(
        back_populates="asset", cascade="all, delete-orphan", lazy="selectin",
        order_by="AssetMaintenanceRecord.maintenance_date.desc()",
    )


class AssetMaintenanceRecord(Base, UUIDPKMixin, TimestampMixin):
    """Spec §15: "maintenance, servicing, repair costs" - an immutable log,
    not a field that gets overwritten (same "don't just store current state"
    principle spec §7 states explicitly for livestock and applies here too)."""
    __tablename__ = "asset_maintenance_records"

    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("assets.id"), index=True)
    maintenance_type: Mapped[str] = mapped_column(String(16))
    maintenance_date: Mapped[date] = mapped_column(Date, index=True)
    description: Mapped[str] = mapped_column(String(255))
    cost: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    performed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    next_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    asset: Mapped["Asset"] = relationship(back_populates="maintenance_records")


class AssetCounter(Base):
    """Per-org gap-free asset numbering - same pattern as every other counter
    in this codebase (finance.InvoiceCounter, procurement.PurchaseOrderCounter,
    employees.EmployeeCounter)."""
    __tablename__ = "asset_counters"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    next_number: Mapped[int] = mapped_column(Integer, default=1)
