import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SubscriptionTierOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    monthly_price_kes: float
    max_users: int | None
    max_animals: int | None
    max_crop_plantings: int | None = None

    class Config:
        from_attributes = True


class SubscriptionOut(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    status: str
    current_period_start: datetime
    current_period_end: datetime | None
    cancel_at_period_end: bool
    tier: SubscriptionTierOut

    class Config:
        from_attributes = True


class SubscribeRequest(BaseModel):
    tier_slug: str
    phone_number: str = Field(..., description="M-Pesa phone number, e.g. 254712345678")


class SubscriptionPaymentOut(BaseModel):
    id: uuid.UUID
    status: str
    amount: float
    currency: str
    provider_reference: str
    initiated_at: datetime
    completed_at: datetime | None

    class Config:
        from_attributes = True
