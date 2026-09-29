import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

STATUS_PATTERN = "^(requested|approved|ordered|received|invoiced|paid|rejected|cancelled)$"


class SupplierCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    contact_person: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    address: str | None = None
    tax_pin: str | None = None
    products_supplied: str | None = None
    payment_terms: str | None = None
    notes: str | None = None


class SupplierUpdate(BaseModel):
    name: str | None = None
    contact_person: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    address: str | None = None
    tax_pin: str | None = None
    products_supplied: str | None = None
    payment_terms: str | None = None
    is_active: bool | None = None
    notes: str | None = None


class SupplierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    contact_person: str | None
    phone: str | None
    email: str | None
    address: str | None
    tax_pin: str | None
    products_supplied: str | None
    payment_terms: str | None
    is_active: bool
    notes: str | None
    created_at: datetime


class PurchaseOrderItemCreate(BaseModel):
    inventory_item_id: uuid.UUID | None = None
    description: str = Field(min_length=1, max_length=255)
    quantity: Decimal = Field(gt=0)
    unit_cost: Decimal = Field(ge=0)


class PurchaseOrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    inventory_item_id: uuid.UUID | None
    description: str
    quantity: Decimal
    unit_cost: Decimal


class PurchaseOrderCreate(BaseModel):
    """Creating a PO always starts it at 'requested' (spec §26 lifecycle) -
    there is no way to create one pre-approved, matching the equivalent
    'no fast-path around required states' rule already enforced for orders
    and animal status in commerce/livestock."""
    supplier_id: uuid.UUID
    expected_delivery_date: date | None = None
    notes: str | None = None
    items: list[PurchaseOrderItemCreate] = Field(min_length=1)


class PurchaseOrderStatusUpdate(BaseModel):
    status: str = Field(pattern=STATUS_PATTERN)
    reason: str | None = None


class PurchaseOrderStatusEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    from_status: str | None
    to_status: str
    reason: str | None
    changed_by: uuid.UUID | None
    changed_at: datetime


class PurchaseOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    organization_id: uuid.UUID
    supplier_id: uuid.UUID
    po_number: str
    status: str
    order_date: date | None
    expected_delivery_date: date | None
    notes: str | None
    requested_by: uuid.UUID | None
    approved_by: uuid.UUID | None
    total_amount: Decimal
    items: list[PurchaseOrderItemOut]
    created_at: datetime


class PurchaseOrderDetailOut(PurchaseOrderOut):
    status_history: list[PurchaseOrderStatusEventOut]
