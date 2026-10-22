import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class IntakeBatchBase(BaseModel):
    name: str | None = Field(default=None, max_length=160)
    delivered_on: date
    farm_id: uuid.UUID | None = None
    source: str | None = None
    sex_class: str = Field(default="bull", pattern="^(bull|steer|heifer|mixed)$")
    head_purchased: int = Field(default=0, ge=0)
    purchase_cost: Decimal = Field(default=Decimal("0"), ge=0)
    transport_cost: Decimal = Field(default=Decimal("0"), ge=0)
    other_fees: Decimal = Field(default=Decimal("0"), ge=0)
    handlers_cost: Decimal = Field(default=Decimal("0"), ge=0)
    notes: str | None = None


class IntakeBatchCreate(IntakeBatchBase):
    batch_number: int | None = Field(default=None, ge=1)   # auto-assigned when omitted


class IntakeBatchUpdate(BaseModel):
    name: str | None = None
    delivered_on: date | None = None
    farm_id: uuid.UUID | None = None
    source: str | None = None
    sex_class: str | None = Field(default=None, pattern="^(bull|steer|heifer|mixed)$")
    head_purchased: int | None = Field(default=None, ge=0)
    purchase_cost: Decimal | None = Field(default=None, ge=0)
    transport_cost: Decimal | None = Field(default=None, ge=0)
    other_fees: Decimal | None = Field(default=None, ge=0)
    handlers_cost: Decimal | None = Field(default=None, ge=0)
    notes: str | None = None


class IntakeBatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    batch_number: int
    name: str
    delivered_on: date
    farm_id: uuid.UUID | None
    source: str | None
    sex_class: str
    head_purchased: int
    purchase_cost: Decimal
    transport_cost: Decimal
    other_fees: Decimal
    handlers_cost: Decimal
    notes: str | None
    landed_cost: float
    landed_cost_per_head: float
    head_registered: int = 0
    head_active: int = 0


class SaleBatchCreate(BaseModel):
    batch_number: int | None = Field(default=None, ge=1)
    sold_on: date
    price_per_kg: Decimal | None = Field(default=None, gt=0)
    buyer_name: str | None = None
    customer_id: uuid.UUID | None = None
    notes: str | None = None


class SaleBatchUpdate(BaseModel):
    sold_on: date | None = None
    price_per_kg: Decimal | None = Field(default=None, gt=0)
    buyer_name: str | None = None
    customer_id: uuid.UUID | None = None
    notes: str | None = None


class SaleBatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    batch_number: int
    sold_on: date
    price_per_kg: Decimal | None
    buyer_name: str | None
    customer_id: uuid.UUID | None
    notes: str | None
    head_sold: int = 0
    total_weight_kg: float = 0.0
    total_amount: float = 0.0


class NewAnimalItem(BaseModel):
    animal_number: str = Field(min_length=1, max_length=64)
    entry_weight_kg: Decimal = Field(gt=0, le=2000)
    ear_tag: str | None = None
    rfid: str | None = None
    breed: str | None = None
    notes: str | None = None


class RegisterAnimalsRequest(BaseModel):
    farm_id: uuid.UUID | None = None            # defaults to the batch's farm
    species: str = "cattle"
    category: str | None = None                 # defaults to the batch sex class
    animals: list[NewAnimalItem] = Field(min_length=1, max_length=500)


class LinkExistingItem(BaseModel):
    animal_id: uuid.UUID
    entry_weight_kg: Decimal | None = Field(default=None, gt=0)


class LinkExistingRequest(BaseModel):
    animals: list[LinkExistingItem] = Field(min_length=1, max_length=500)


class WeighEntry(BaseModel):
    animal_number: str | None = None
    animal_id: uuid.UUID | None = None
    weight_kg: Decimal = Field(gt=0, le=2000)

    @model_validator(mode="after")
    def _one_identifier(self):
        if not self.animal_number and not self.animal_id:
            raise ValueError("animal_number or animal_id is required")
        return self


class BulkWeighRequest(BaseModel):
    weighed_on: date
    scale_label: str | None = None
    notes: str | None = None
    farm_id: uuid.UUID | None = None
    overwrite: bool = False
    dry_run: bool = False
    entries: list[WeighEntry] = Field(min_length=1, max_length=1000)


class SaleRequest(BaseModel):
    exit_date: date
    exit_weight_kg: Decimal = Field(gt=0, le=2000)
    price_per_kg: Decimal | None = Field(default=None, gt=0)
    sale_batch_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    salesperson: str | None = None


class CullRequest(BaseModel):
    exit_type: str = Field(pattern="^(culled|died)$")
    exit_date: date
    exit_weight_kg: Decimal | None = Field(default=None, gt=0, le=2000)
    reason: str | None = None


class BatchSaleEntry(BaseModel):
    animal_number: str | None = None
    animal_id: uuid.UUID | None = None
    exit_weight_kg: Decimal = Field(gt=0, le=2000)
    price_per_kg: Decimal | None = Field(default=None, gt=0)
    customer_id: uuid.UUID | None = None
    salesperson: str | None = None

    @model_validator(mode="after")
    def _one_identifier(self):
        if not self.animal_number and not self.animal_id:
            raise ValueError("animal_number or animal_id is required")
        return self


class BatchSaleRequest(BaseModel):
    entries: list[BatchSaleEntry] = Field(min_length=1, max_length=500)


class CostingDocumentCreate(BaseModel):
    kind: str = Field(pattern="^(settings|recipe|enterprise_budget|ration_plan|overhead_pool|land_use)$")
    name: str = Field(min_length=1, max_length=160)
    data: dict[str, Any] = Field(default_factory=dict)


class CostingDocumentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    data: dict[str, Any] | None = None


class CostingDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    kind: str
    name: str
    data: dict[str, Any]
    computed: dict[str, Any] | None = None
    updated_at: datetime
