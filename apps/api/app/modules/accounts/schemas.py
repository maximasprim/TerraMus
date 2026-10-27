import uuid
from datetime import datetime
from decimal import Decimal

from app.core.emailnorm import NormalizedEmail
from pydantic import BaseModel, ConfigDict, Field


class CustomerRegisterRequest(BaseModel):
    """Spec §69: 'Allow account creation after purchase.' Deliberately no
    organization_id field - the org is the {org_slug} in the URL, exactly
    like every other endpoint in modules/public (never trust a client-
    supplied tenant id, spec §52.13)."""
    full_name: str = Field(min_length=1, max_length=255)
    email: NormalizedEmail
    phone: str | None = None
    password: str = Field(min_length=8, max_length=128)


class MyAccountOut(BaseModel):
    """Merges the login identity (identity.User) with the CRM profile
    (customers.Customer) it's linked to - a customer thinks of these as one
    profile, even though this codebase deliberately keeps them as two tables
    (see identity.models.User.customer_id docstring)."""
    model_config = ConfigDict(from_attributes=True)
    user_id: uuid.UUID
    customer_id: uuid.UUID
    full_name: str
    email: str
    phone: str | None
    location: str | None
    customer_type: str
    created_at: datetime


class MyOrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    animal_id: uuid.UUID
    price: Decimal


class MyOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    status: str
    total_amount: Decimal
    delivery_option: str | None
    created_at: datetime
    items: list[MyOrderItemOut]


class MyInvoiceOut(BaseModel):
    """Spec §16 lists 'payments, invoices' alongside order history as
    things a customer can access - this was a documented gap from Phase 15
    ('order status/items only'), closed this session."""
    model_config = ConfigDict(from_attributes=True)
    invoice_number: str
    subtotal: Decimal
    tax_amount: Decimal
    total: Decimal
    issued_at: datetime


class MyPaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    provider: str
    amount: Decimal
    status: str
    initiated_at: datetime
    completed_at: datetime | None


class MyOrderDetailOut(MyOrderOut):
    invoice: MyInvoiceOut | None
    payments: list[MyPaymentOut]
