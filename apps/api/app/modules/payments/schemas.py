import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class InitiatePaymentRequest(BaseModel):
    order_id: uuid.UUID
    phone_or_token: str = Field(description="Phone number for M-Pesa, or a payment-method token for Stripe")


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    order_id: uuid.UUID
    provider: str
    provider_reference: str
    amount: Decimal
    currency: str
    status: str
    initiated_at: datetime
    completed_at: datetime | None
