import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BreedingRecordCreate(BaseModel):
    dam_id: uuid.UUID
    sire_id: uuid.UUID | None = None
    sire_external: str | None = None
    method: str = Field(pattern="^(natural|artificial_insemination)$")
    mating_date: date
    expected_delivery_date: date | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _one_sire_source(self):
        if self.sire_id and self.sire_external:
            raise ValueError("Provide either sire_id (on-farm) or sire_external, not both")
        return self


class PregnancyCheckCreate(BaseModel):
    check_date: date
    result: str = Field(pattern="^(confirmed|not_pregnant|inconclusive)$")
    notes: str | None = None


class PregnancyCheckOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    check_date: date
    result: str
    notes: str | None
    performed_by: uuid.UUID | None
    created_at: datetime


class DeliveryRecord(BaseModel):
    actual_delivery_date: date
    offspring_count: int = Field(ge=0)
    create_offspring_animals: bool = True
    offspring_sex: list[str] | None = None  # one entry per offspring, e.g. ["female","male"]
    notes: str | None = None


class BreedingRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    dam_id: uuid.UUID
    sire_id: uuid.UUID | None
    sire_external: str | None
    method: str
    mating_date: date
    expected_delivery_date: date | None
    pregnancy_status: str
    actual_delivery_date: date | None
    offspring_count: int | None
    notes: str | None
    created_at: datetime
    pregnancy_checks: list[PregnancyCheckOut] = []
