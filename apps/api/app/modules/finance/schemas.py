import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

TRANSACTION_TYPE_PATTERN = "^(income|expense)$"
CATEGORY_PATTERN = (
    "^(livestock_sale|milk_sale|other_revenue|livestock_acquisition|feed|veterinary|"
    "labour|transport|utilities|maintenance|equipment|marketing|payment_processing_fee|other_expense)$"
)


class FinanceTransactionCreate(BaseModel):
    transaction_type: str = Field(pattern=TRANSACTION_TYPE_PATTERN)
    category: str = Field(pattern=CATEGORY_PATTERN)
    amount: Decimal = Field(gt=0)
    transaction_date: date
    description: str | None = None


class FinanceTransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    transaction_type: str
    category: str
    amount: Decimal
    currency: str
    reference_type: str | None
    reference_id: uuid.UUID | None
    description: str | None
    transaction_date: date
    created_by: uuid.UUID | None
    created_at: datetime


class FinanceSummary(BaseModel):
    start_date: date
    end_date: date
    total_income: Decimal
    total_expense: Decimal
    net_income: Decimal
    income_by_category: dict[str, Decimal]
    expense_by_category: dict[str, Decimal]


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    order_id: uuid.UUID
    customer_id: uuid.UUID
    invoice_number: str
    subtotal: Decimal
    tax_amount: Decimal
    total: Decimal
    issued_at: datetime
