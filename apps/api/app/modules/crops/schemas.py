import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.crops.catalog import CROP_TYPE_CODES
from app.modules.crops.models import PLANTING_STATUSES

VALID_CROP_TYPES = CROP_TYPE_CODES
_CROP_TYPE_PATTERN = "^(" + "|".join(VALID_CROP_TYPES) + ")$"
VALID_PLANTING_METHODS = ("seed", "seedling", "cutting", "grafted", "tissue_culture")
VALID_AREA_UNITS = ("acres", "hectares")


class CropPlantingCreate(BaseModel):
    farm_id: uuid.UUID
    location_id: uuid.UUID | None = None
    planting_number: str = Field(min_length=1, max_length=64)
    crop_type: str = Field(pattern=_CROP_TYPE_PATTERN)
    variety: str | None = None
    is_perennial: bool = False
    area_size: Decimal | None = None
    area_unit: str = Field(default="acres", pattern="^(acres|hectares)$")
    planting_date: date
    planting_method: str | None = Field(default=None, pattern="^(seed|seedling|cutting|grafted|tissue_culture)$")
    expected_harvest_date: date | None = None
    acquisition_cost: Decimal = Decimal("0")
    current_value: Decimal | None = None
    expected_yield: Decimal | None = None
    yield_unit: str | None = None
    source: str | None = None
    supplier: str | None = None
    notes: str | None = None


class CropPlantingUpdate(BaseModel):
    location_id: uuid.UUID | None = None
    variety: str | None = None
    current_value: Decimal | None = None
    expected_yield: Decimal | None = None
    yield_unit: str | None = None
    expected_harvest_date: date | None = None
    health_status: str | None = None
    notes: str | None = None


class StatusChangeRequest(BaseModel):
    status: str = Field(pattern="^(" + "|".join(PLANTING_STATUSES) + ")$")
    reason: str | None = None


class CropPlantingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    organization_id: uuid.UUID
    farm_id: uuid.UUID
    location_id: uuid.UUID | None
    planting_number: str
    crop_type: str
    variety: str | None
    is_perennial: bool
    area_size: Decimal | None
    area_unit: str
    planting_date: date
    planting_method: str | None
    expected_harvest_date: date | None
    acquisition_cost: Decimal
    current_value: Decimal | None
    expected_yield: Decimal | None
    yield_unit: str | None
    status: str
    health_status: str
    source: str | None
    supplier: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class CropEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    event_type: str
    event_at: datetime
    data: dict | None
    recorded_by: uuid.UUID | None
    created_at: datetime


class HarvestRecordCreate(BaseModel):
    quantity: Decimal = Field(gt=0)
    unit: str = Field(min_length=1, max_length=16)
    quality_grade: str | None = None
    harvested_at: datetime | None = None
    notes: str | None = None


class HarvestRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    quantity: Decimal
    unit: str
    quality_grade: str | None
    harvested_at: datetime
    recorded_by: uuid.UUID | None
    notes: str | None
    # Computed at read-time by the service (not a DB column) - running total
    # harvested to date for this planting, mirroring WeightRecord's ADG field.
    cumulative_yield: Decimal | None = None


class CropPlantingProfitability(BaseModel):
    """Mirrors livestock's AnimalProfitability - partial until Health/Feed/
    Finance cost aggregation is wired in for crops; those components are
    explicit zeros rather than silently omitted."""
    planting_id: uuid.UUID
    acquisition_cost: Decimal
    input_cost: Decimal = Decimal("0")  # fertilizer/agrochemicals - future phase
    labor_cost: Decimal = Decimal("0")
    other_cost: Decimal = Decimal("0")
    total_investment: Decimal
    total_harvested_value: Decimal | None = None
    current_value: Decimal | None
