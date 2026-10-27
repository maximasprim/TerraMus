import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

ACTIVITY_FODDER = "fodder"


class ProductCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    category: str = Field(default="hay", pattern="^(hay|silage|haylage|straw|green_chop|other)$")
    unit_label: str = Field(default="bale", min_length=1, max_length=16)
    kg_per_unit: Decimal = Field(default=Decimal("1"), gt=0, le=100000)
    dry_matter_pct: Decimal | None = Field(default=None, ge=0, le=100)
    reorder_days: int = Field(default=14, ge=0, le=365)
    notes: str | None = None


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    unit_label: str | None = Field(default=None, min_length=1, max_length=16)
    kg_per_unit: Decimal | None = Field(default=None, gt=0, le=100000)
    dry_matter_pct: Decimal | None = Field(default=None, ge=0, le=100)
    reorder_days: int | None = Field(default=None, ge=0, le=365)
    is_active: bool | None = None
    notes: str | None = None


class PriceCreate(BaseModel):
    effective_from: date
    price_per_kg: Decimal = Field(gt=0, le=100000)
    source: str | None = Field(default=None, max_length=120)


class PlotCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    acres: Decimal = Field(gt=0, le=100000)
    farm_id: uuid.UUID | None = None
    irrigated: bool = False
    crop: str | None = Field(default=None, max_length=80)
    established_on: date | None = None
    notes: str | None = None


class PlotUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    acres: Decimal | None = Field(default=None, gt=0, le=100000)
    irrigated: bool | None = None
    crop: str | None = None
    status: str | None = Field(default=None, pattern="^(active|resting|retired)$")
    notes: str | None = None


class CycleCreate(BaseModel):
    plot_id: uuid.UUID
    product_id: uuid.UUID
    label: str = Field(min_length=2, max_length=120)
    start_date: date
    acres: Decimal | None = Field(default=None, gt=0)          # defaults to the whole plot
    budget_name: str | None = Field(default=None, max_length=160)
    notes: str | None = None


class CycleClose(BaseModel):
    end_date: date


class CostCreate(BaseModel):
    cost_date: date
    category: str = Field(pattern="^(seed|fertilizer|chemicals|labour|fuel|machinery_hire|irrigation|transport|packaging|other)$")
    amount: Decimal = Field(gt=0, le=100_000_000)
    description: str | None = Field(default=None, max_length=255)
    post_to_finance: bool = True


class HarvestCreate(BaseModel):
    harvest_date: date
    quantity: Decimal = Field(gt=0, le=10_000_000)             # in the product's unit
    kg: Decimal | None = Field(default=None, gt=0)             # actual weight, if weighed (else quantity x kg per unit)
    quality: str | None = Field(default=None, pattern="^(good|fair|poor)$")
    notes: str | None = Field(default=None, max_length=255)


class InvestmentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    cost: Decimal = Field(gt=0, le=1_000_000_000)
    salvage_value: Decimal = Field(default=Decimal("0"), ge=0)
    in_service_on: date
    life_years: Decimal = Field(gt=0, le=100)
    plot_id: uuid.UUID | None = None                           # empty = shared by every plot
    notes: str | None = None

    @model_validator(mode="after")
    def _salvage(self):
        if self.salvage_value > self.cost:
            raise ValueError("salvage_value cannot exceed the cost")
        return self


class InvestmentDispose(BaseModel):
    disposed_on: date


class MovementCreate(BaseModel):
    product_id: uuid.UUID
    movement_date: date
    movement_type: str = Field(pattern="^(purchase|issue|sale|loss|count)$")
    kg: Decimal | None = Field(default=None, gt=0)
    units: Decimal | None = Field(default=None, gt=0)          # alternative to kg: bales, tonnes ...
    value: Decimal | None = Field(default=None, ge=0)          # purchase cost / sale proceeds (total)
    destination_type: str | None = Field(default=None, pattern="^(feedlot|group|animals|other)$")
    destination_id: uuid.UUID | None = None
    destination_label: str | None = Field(default=None, max_length=120)
    customer_id: uuid.UUID | None = None                       # a sale on credit
    reason: str | None = Field(default=None, max_length=255)
    post_to_finance: bool = True

    @model_validator(mode="after")
    def _rules(self):
        if self.kg is None and self.units is None:
            raise ValueError("give the quantity as kg or as units")
        if self.movement_type in ("purchase", "sale") and not self.value:
            raise ValueError(f"a {self.movement_type} needs its value (KES, total)")
        return self
