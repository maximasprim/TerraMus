import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

RECORD_TYPE_PATTERN = "^(vaccination|treatment|deworming|examination|injury|lab_result|vet_visit|prescription)$"


class HealthRecordCreate(BaseModel):
    record_type: str = Field(pattern=RECORD_TYPE_PATTERN)
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    diagnosis: str | None = None
    medication: str | None = None
    dosage: str | None = None
    administered_by: str | None = None
    cost: Decimal | None = None
    performed_at: datetime | None = None
    follow_up_date: date | None = None


class HealthRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    animal_id: uuid.UUID
    record_type: str
    title: str
    description: str | None
    diagnosis: str | None
    medication: str | None
    dosage: str | None
    administered_by: str | None
    cost: Decimal | None
    performed_at: datetime
    follow_up_date: date | None
    follow_up_completed: bool
    recorded_by: uuid.UUID | None
    created_at: datetime


class FollowUpCompleteRequest(BaseModel):
    notes: str | None = None


class DueFollowUpOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    animal_id: uuid.UUID
    record_type: str
    title: str
    follow_up_date: date
    is_overdue: bool
