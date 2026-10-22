import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

ACTIVITY_PATTERN = "^(livestock|feedlot|dairy|crops|fodder|poultry|fish|rabbits|training|general)$"
REF_PATTERN = "^(feedlot_sale|training_enrolment|crop_sale|fodder_sale|group_sale|order|manual)$"


class ChargeCreate(BaseModel):
    customer_id: uuid.UUID
    amount: Decimal = Field(gt=0)
    entry_date: date
    description: str | None = Field(default=None, max_length=255)
    reference_type: str = Field(default="manual", pattern=REF_PATTERN)
    reference_id: uuid.UUID | None = None
    farm_id: uuid.UUID | None = None
    activity: str | None = Field(default=None, pattern=ACTIVITY_PATTERN)
    salesperson: str | None = None


class PaymentCreate(BaseModel):
    customer_id: uuid.UUID
    amount: Decimal = Field(gt=0)
    entry_date: date
    method: str = Field(default="cash", pattern="^(cash|mpesa|bank|cheque|other)$")
    receipt_ref: str | None = Field(default=None, max_length=64)     # e.g. the M-Pesa confirmation code
    description: str | None = Field(default=None, max_length=255)
    reference_type: str | None = Field(default=None, pattern=REF_PATTERN)   # which sale this pays, if known
    reference_id: uuid.UUID | None = None
    farm_id: uuid.UUID | None = None
    activity: str | None = Field(default=None, pattern=ACTIVITY_PATTERN)


class WriteoffCreate(BaseModel):
    customer_id: uuid.UUID
    amount: Decimal = Field(gt=0)
    entry_date: date
    description: str = Field(min_length=3, max_length=255)    # a reason is mandatory for a write-off
    reference_type: str | None = Field(default=None, pattern=REF_PATTERN)
    reference_id: uuid.UUID | None = None
