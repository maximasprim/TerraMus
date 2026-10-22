import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator


class GroupCreate(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=2, max_length=160)
    species: str = Field(pattern="^(poultry|rabbits|fish|pigs|other)$")
    purpose: str | None = Field(default=None, max_length=24)        # layers, broilers, growout, breeding ...
    breed: str | None = None
    source: str | None = None
    farm_id: uuid.UUID | None = None
    start_date: date
    initial_count: int = Field(gt=0, le=1_000_000)
    acquisition_cost: Decimal = Field(default=Decimal("0"), ge=0)
    notes: str | None = None


class RecordCreate(BaseModel):
    record_date: date
    record_type: str = Field(pattern="^(mortality|cull|production|feed|weight_sample|sale|addition)$")
    quantity: Decimal = Field(ge=0)
    unit: str | None = Field(default=None, max_length=16)           # head | eggs | trays | kg | kits ...
    value: Decimal | None = Field(default=None, ge=0)               # KES: sale proceeds or feed cost
    avg_weight_kg: Decimal | None = Field(default=None, gt=0, le=500)
    product: str | None = Field(default=None, pattern="^(live|meat|eggs|fish|kits|manure|other)$")
    customer_id: uuid.UUID | None = None                            # sale on credit when set
    notes: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def _rules(self):
        t = self.record_type
        if t in ("mortality", "cull", "addition") and (self.quantity != self.quantity.to_integral_value() or self.quantity <= 0):
            raise ValueError(f"{t} quantity must be a whole number of animals greater than 0")
        if t == "weight_sample" and (self.avg_weight_kg is None or self.quantity <= 0):
            raise ValueError("weight_sample needs avg_weight_kg and quantity (number weighed)")
        if t == "sale" and (not self.value or self.value <= 0 or self.quantity <= 0):
            raise ValueError("a sale needs quantity and value (KES) greater than 0")
        return self


class GroupClose(BaseModel):
    closed_on: date
    notes: str | None = None
