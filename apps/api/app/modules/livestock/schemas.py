import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.livestock.catalog import SPECIES_CODES
from app.modules.livestock.models import ANIMAL_STATUSES

VALID_SPECIES = SPECIES_CODES
VALID_SEX = ("male", "female")
VALID_ACQUISITION_METHODS = ("purchased", "born_on_farm", "transferred_in", "gifted")
_SPECIES_PATTERN = "^(" + "|".join(VALID_SPECIES) + ")$"


class AnimalCreate(BaseModel):
    farm_id: uuid.UUID
    location_id: uuid.UUID | None = None
    dam_id: uuid.UUID | None = None
    sire_id: uuid.UUID | None = None
    animal_number: str = Field(min_length=1, max_length=64)
    ear_tag: str | None = None
    rfid: str | None = None
    species: str = Field(pattern=_SPECIES_PATTERN)
    breed: str | None = None
    category: str | None = None
    sex: str = Field(pattern="^(male|female)$")
    name: str | None = None
    date_of_birth: date | None = None
    estimated_birth_date: bool = False
    acquisition_date: date
    acquisition_method: str = Field(pattern="^(purchased|born_on_farm|transferred_in|gifted)$")
    acquisition_cost: Decimal = Decimal("0")
    current_value: Decimal | None = None
    expected_sale_price: Decimal | None = None
    current_weight: Decimal | None = None
    target_weight: Decimal | None = None
    source: str | None = None
    previous_owner: str | None = None
    supplier: str | None = None
    notes: str | None = None


class AnimalUpdate(BaseModel):
    location_id: uuid.UUID | None = None
    ear_tag: str | None = None
    rfid: str | None = None
    breed: str | None = None
    category: str | None = None
    name: str | None = None
    current_value: Decimal | None = None
    expected_sale_price: Decimal | None = None
    target_weight: Decimal | None = None
    health_status: str | None = None
    reproductive_status: str | None = None
    notes: str | None = None


class StatusChangeRequest(BaseModel):
    status: str = Field(pattern="^(" + "|".join(ANIMAL_STATUSES) + ")$")
    reason: str | None = None


class AnimalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    organization_id: uuid.UUID
    farm_id: uuid.UUID
    location_id: uuid.UUID | None
    dam_id: uuid.UUID | None
    sire_id: uuid.UUID | None
    animal_number: str
    ear_tag: str | None
    rfid: str | None
    species: str
    breed: str | None
    category: str | None
    sex: str
    name: str | None
    date_of_birth: date | None
    estimated_birth_date: bool
    acquisition_date: date
    acquisition_method: str
    acquisition_cost: Decimal
    current_value: Decimal | None
    expected_sale_price: Decimal | None
    current_weight: Decimal | None
    target_weight: Decimal | None
    status: str
    health_status: str
    reproductive_status: str | None
    source: str | None
    previous_owner: str | None
    supplier: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class AnimalEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    event_type: str
    event_at: datetime
    data: dict | None
    recorded_by: uuid.UUID | None
    created_at: datetime


class WeightRecordCreate(BaseModel):
    weight_kg: Decimal = Field(gt=0)
    recorded_at: datetime | None = None
    notes: str | None = None


class WeightRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    weight_kg: Decimal
    recorded_at: datetime
    recorded_by: uuid.UUID | None
    notes: str | None
    # Computed at read-time by the service (not a DB column) - average daily gain
    # since the previous weight record (spec §8).
    average_daily_gain: Decimal | None = None


class MovementCreate(BaseModel):
    to_location_id: uuid.UUID
    moved_at: datetime | None = None
    reason: str | None = None
    notes: str | None = None


class MovementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    from_location_id: uuid.UUID | None
    to_location_id: uuid.UUID
    moved_at: datetime
    reason: str | None
    authorized_by: uuid.UUID | None
    notes: str | None


class AnimalProfitability(BaseModel):
    """Spec §8/§25 - partial in Phase 2: only acquisition cost is tracked directly
    on the animal so far. Feed/health/transport cost aggregation is wired in once
    the Feed/Inventory (Ph3) and Health (Ph2b) services exist; those fields are
    zeroed here as explicit placeholders rather than silently omitted."""
    animal_id: uuid.UUID
    acquisition_cost: Decimal
    feed_cost: Decimal = Decimal("0")
    health_cost: Decimal = Decimal("0")
    transport_cost: Decimal = Decimal("0")
    other_cost: Decimal = Decimal("0")
    total_investment: Decimal
    expected_sale_price: Decimal | None
    expected_profit: Decimal | None
    current_value: Decimal | None
