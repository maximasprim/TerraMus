import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

ASSET_TYPE_PATTERN = "^(tractor|vehicle|pump|generator|milking_equipment|water_system|building|fence|tool|machinery|other)$"
ASSET_CONDITION_PATTERN = "^(excellent|good|fair|poor|out_of_service)$"
ASSET_STATUS_PATTERN = "^(in_use|in_storage|under_maintenance|disposed)$"
MAINTENANCE_TYPE_PATTERN = "^(service|repair|inspection)$"


class AssetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    asset_type: str = Field(pattern=ASSET_TYPE_PATTERN)
    serial_number: str | None = None
    condition: str = Field(default="good", pattern=ASSET_CONDITION_PATTERN)
    acquisition_date: date | None = None
    acquisition_cost: Decimal | None = Field(default=None, ge=0)
    useful_life_years: int | None = Field(default=None, gt=0)
    salvage_value: Decimal | None = Field(default=None, ge=0)
    warranty_expiry: date | None = None
    assigned_farm_id: uuid.UUID | None = None
    assigned_location_id: uuid.UUID | None = None
    supplier_id: uuid.UUID | None = None
    notes: str | None = None


class AssetUpdate(BaseModel):
    name: str | None = None
    serial_number: str | None = None
    condition: str | None = Field(default=None, pattern=ASSET_CONDITION_PATTERN)
    status: str | None = Field(default=None, pattern=ASSET_STATUS_PATTERN)
    useful_life_years: int | None = Field(default=None, gt=0)
    salvage_value: Decimal | None = Field(default=None, ge=0)
    warranty_expiry: date | None = None
    assigned_farm_id: uuid.UUID | None = None
    assigned_location_id: uuid.UUID | None = None
    supplier_id: uuid.UUID | None = None
    notes: str | None = None


class MaintenanceRecordCreate(BaseModel):
    maintenance_type: str = Field(pattern=MAINTENANCE_TYPE_PATTERN)
    maintenance_date: date
    description: str = Field(min_length=1, max_length=255)
    cost: Decimal | None = Field(default=None, ge=0)
    performed_by: str | None = None
    next_due_date: date | None = None


class MaintenanceRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    asset_id: uuid.UUID
    maintenance_type: str
    maintenance_date: date
    description: str
    cost: Decimal | None
    performed_by: str | None
    next_due_date: date | None


class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    organization_id: uuid.UUID
    asset_number: str
    name: str
    asset_type: str
    serial_number: str | None
    status: str
    condition: str
    acquisition_date: date | None
    acquisition_cost: Decimal | None
    useful_life_years: int | None
    salvage_value: Decimal | None
    warranty_expiry: date | None
    assigned_farm_id: uuid.UUID | None
    assigned_location_id: uuid.UUID | None
    supplier_id: uuid.UUID | None
    notes: str | None
    created_at: datetime
    current_value: Decimal | None  # spec §15 "depreciation" - derived, see service.depreciated_value
    total_maintenance_cost: Decimal  # spec §15 "repair costs" rolled up


class AssetDetailOut(AssetOut):
    maintenance_records: list[MaintenanceRecordOut]
