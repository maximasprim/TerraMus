import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

CATEGORY_PATTERN = "^(feed|medicine|vaccine|supply|equipment|consumable)$"
MOVEMENT_TYPE_PATTERN = "^(purchase|sale|consumption|transfer|adjustment|wastage|return|expired|opening_balance)$"


class InventoryItemCreate(BaseModel):
    farm_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    category: str = Field(pattern=CATEGORY_PATTERN)
    unit: str = Field(min_length=1, max_length=16)
    reorder_level: Decimal = Decimal("0")
    allow_negative_stock: bool = False
    notes: str | None = None


class InventoryItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    organization_id: uuid.UUID
    farm_id: uuid.UUID | None
    name: str
    category: str
    unit: str
    reorder_level: Decimal
    allow_negative_stock: bool
    notes: str | None
    current_stock: Decimal = Decimal("0")  # computed at read time, not a stored column


class StockMovementCreate(BaseModel):
    movement_type: str = Field(pattern=MOVEMENT_TYPE_PATTERN)
    # For all types except 'adjustment', this is an unsigned magnitude - the
    # service applies the correct sign. For 'adjustment', supply the signed delta.
    quantity: Decimal
    unit_cost: Decimal | None = None
    batch_number: str | None = None
    expiry_date: date | None = None
    animal_id: uuid.UUID | None = None
    reference: str | None = None
    notes: str | None = None
    moved_at: datetime | None = None


class StockMovementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    item_id: uuid.UUID
    movement_type: str
    quantity: Decimal
    unit_cost: Decimal | None
    batch_number: str | None
    expiry_date: date | None
    animal_id: uuid.UUID | None
    reference: str | None
    notes: str | None
    performed_by: uuid.UUID | None
    moved_at: datetime


class LowStockItem(BaseModel):
    item_id: uuid.UUID
    name: str
    category: str
    unit: str
    current_stock: Decimal
    reorder_level: Decimal


class ValuationRow(BaseModel):
    """Spec §14: 'Support inventory valuation' (this session - see
    service._fifo_layers_remaining for the costing model). priced_quantity
    can be less than quantity_on_hand when some stock has no cost basis
    behind it (e.g. an old opening_balance recorded with no unit_cost) -
    reported separately rather than silently blended into the average."""
    item_id: uuid.UUID
    item_name: str
    unit: str
    quantity_on_hand: Decimal
    priced_quantity: Decimal
    avg_unit_cost: Decimal | None
    total_value: Decimal
