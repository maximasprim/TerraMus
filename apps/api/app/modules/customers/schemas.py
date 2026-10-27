import uuid
from datetime import datetime

from app.core.emailnorm import NormalizedEmail
from pydantic import BaseModel, ConfigDict, Field

CUSTOMER_TYPE_PATTERN = "^(individual|butcher|hotel|restaurant|institution|livestock_trader|wholesaler|farm|corporate)$"


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    phone: str | None = None
    email: NormalizedEmail | None = None
    location: str | None = None
    customer_type: str = Field(default="individual", pattern=CUSTOMER_TYPE_PATTERN)
    notes: str | None = None


class CustomerUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    email: NormalizedEmail | None = None
    location: str | None = None
    customer_type: str | None = Field(default=None, pattern=CUSTOMER_TYPE_PATTERN)
    notes: str | None = None


class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    phone: str | None
    email: str | None
    location: str | None
    customer_type: str
    notes: str | None
    created_at: datetime
