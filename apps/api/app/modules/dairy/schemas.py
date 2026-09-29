import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class LactationCycleCreate(BaseModel):
    start_date: date


class LactationCycleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    animal_id: uuid.UUID
    start_date: date
    end_date: date | None
    is_active: bool


class DryOffRequest(BaseModel):
    end_date: date


class MilkRecordCreate(BaseModel):
    production_date: date
    session: str = Field(pattern="^(morning|midday|evening)$")
    quantity_liters: Decimal = Field(ge=0)
    rejected: bool = False
    rejection_reason: str | None = None


class MilkRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    animal_id: uuid.UUID
    lactation_cycle_id: uuid.UUID | None
    production_date: date
    session: str
    quantity_liters: Decimal
    rejected: bool
    rejection_reason: str | None
    recorded_by: uuid.UUID | None
    created_at: datetime


class HerdMilkSummary(BaseModel):
    date: date
    total_liters: Decimal
    average_per_cow: Decimal
    cows_milked: int
    top_producers: list[dict]
