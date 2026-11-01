import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

COST_CATEGORY_PATTERN = (
    "^(seed|fertilizer|chemicals|labour|fuel|transport|equipment|maintenance|lease|insurance|utilities|other_expense)$"
)


class CropSaleCreate(BaseModel):
    sale_date: date
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    unit: str | None = Field(default=None, max_length=16)         # defaults to the unit the harvests were recorded in
    unit_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    amount: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)   # the total; give this OR the price
    customer_id: uuid.UUID | None = None                          # set = sold on credit (charged to their account)
    buyer_name: str | None = Field(default=None, max_length=128)  # free text when the buyer is not a saved customer
    notes: str | None = Field(default=None, max_length=255)
    post_to_finance: bool = True

    @model_validator(mode="after")
    def _price_or_amount(self):
        if self.unit_price is None and self.amount is None:
            raise ValueError("Give the unit price or the total amount")
        return self


class CropCostCreate(BaseModel):
    cost_date: date
    category: str = Field(pattern=COST_CATEGORY_PATTERN)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    description: str | None = Field(default=None, max_length=255)
    post_to_finance: bool = True


class VoidRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=255)


class CropSaleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    planting_id: uuid.UUID
    sale_date: date
    quantity: Decimal
    unit: str
    unit_price: Decimal
    amount: Decimal
    customer_id: uuid.UUID | None
    buyer_name: str | None
    notes: str | None
    source: str
    voided_at: datetime | None
    void_reason: str | None
    created_at: datetime
    in_finance: bool = False          # filled in by the service: is it in the ledger?


class CropCostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    planting_id: uuid.UUID
    cost_date: date
    category: str
    amount: Decimal
    description: str | None
    source: str
    voided_at: datetime | None
    void_reason: str | None
    created_at: datetime
    in_finance: bool = False


class CropSaleResult(BaseModel):
    sale: CropSaleOut
    ledger: str                        # income_posted | charged_to_customer_account | not_posted
    stock_warning: str | None = None   # sold more than the recorded harvests: record the missing harvest


class WebSaleLine(BaseModel):
    order_id: uuid.UUID
    date: date
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal
    status: str


class PlantingEconomics(BaseModel):
    planting_id: uuid.UUID
    planting_number: str
    crop_type: str
    variety: str | None = None
    status: str
    is_closed: bool                    # harvested / failed / archived: the cycle is over
    unit: str | None = None
    acquisition_cost: Decimal
    input_cost: Decimal                # seed + fertiliser + chemicals recorded as costs
    labour_cost: Decimal
    other_cost: Decimal
    total_investment: Decimal
    revenue_web: Decimal
    revenue_direct: Decimal
    total_revenue: Decimal
    profit: Decimal                    # realised so far: revenue - investment (a growing crop shows its cost until it sells)
    quantity_harvested: Decimal
    quantity_sold_web: Decimal
    quantity_sold_direct: Decimal
    stock_on_hand: Decimal
    listed_price: Decimal | None = None       # price on the planting's web listing, if any
    stock_value: Decimal | None = None        # stock_on_hand x listed_price: an estimate, never counted as profit
    avg_price_per_unit: Decimal | None = None
    cost_per_unit: Decimal | None = None


class CropEconomicsTotals(BaseModel):
    plantings: int = 0
    total_investment: Decimal = Decimal("0")
    revenue_web: Decimal = Decimal("0")
    revenue_direct: Decimal = Decimal("0")
    total_revenue: Decimal = Decimal("0")
    profit: Decimal = Decimal("0")
    closed_plantings: int = 0
    closed_profit: Decimal = Decimal("0")      # profit of finished cycles only: the cleaner number


class CropEconomicsReport(BaseModel):
    plantings: list[PlantingEconomics]
    totals: CropEconomicsTotals


class PlantingBreakdown(BaseModel):
    summary: PlantingEconomics
    costs: list[CropCostOut]           # includes voided ones, flagged, so the history is visible
    direct_sales: list[CropSaleOut]
    web_sales: list[WebSaleLine]


class CropImportResult(BaseModel):
    ok: bool
    dry_run: bool
    kind: str                          # sales | costs
    rows: int = 0
    created: int = 0
    already_imported: int = 0          # rows seen before (same import key): skipped, never doubled
    posted_to_finance: int = 0
    errors: list[dict] = []
    warnings: list[dict] = []
