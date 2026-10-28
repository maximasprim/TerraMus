"""Response shapes for GET /reports/analytics - everything the tenant dashboard
and reports page chart. Money is Decimal (serialised as a string, like the rest
of the API); the frontend converts with Number()."""
from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class LabelCount(BaseModel):
    key: str
    count: int


class LabelAmount(BaseModel):
    key: str
    amount: Decimal


class MonthlyFinance(BaseModel):
    month: str  # YYYY-MM
    income: Decimal
    expense: Decimal
    net: Decimal


class FinanceAnalytics(BaseModel):
    monthly: list[MonthlyFinance]
    total_income: Decimal
    total_expense: Decimal
    net: Decimal
    income_by_category: list[LabelAmount]
    expense_by_category: list[LabelAmount]


class MonthlySales(BaseModel):
    month: str
    orders: int
    revenue: Decimal            # paid web orders (unchanged meaning)
    # Animals sold outside the web shop and recorded in the feedlot (typed in or imported).
    feedlot_head: int = 0
    feedlot_revenue: Decimal = Decimal("0")
    # Bulls bought into the feedlot that month (by delivery date): the money going out against the sales above.
    feedlot_purchase_head: int = 0
    feedlot_purchases: Decimal = Decimal("0")


class ProviderTotal(BaseModel):
    key: str
    amount: Decimal
    count: int


class SalesAnalytics(BaseModel):
    monthly: list[MonthlySales]
    orders_by_status: list[LabelCount]
    payments_by_provider: list[ProviderTotal]
    total_orders: int  # revenue-bearing orders in the window
    total_revenue: Decimal      # web orders only (unchanged meaning)
    average_order_value: Decimal
    feedlot_head: int = 0
    feedlot_revenue: Decimal = Decimal("0")
    combined_revenue: Decimal = Decimal("0")   # web orders + feedlot sales
    feedlot_purchase_head: int = 0
    feedlot_purchases: Decimal = Decimal("0")  # landed cost of bulls delivered in the window


class HerdAnalytics(BaseModel):
    total: int
    active: int
    by_species: list[LabelCount]  # active herd only
    by_status: list[LabelCount]   # every animal


class DailyMilk(BaseModel):
    date: date
    liters: Decimal


class DairyAnalytics(BaseModel):
    daily: list[DailyMilk]  # last 30 days, zero-filled
    total_liters: Decimal
    average_per_day: Decimal
    rejected_liters: Decimal


class CropTypeStat(BaseModel):
    key: str
    plantings: int
    area: Decimal


class HarvestUnitTotal(BaseModel):
    unit: str
    quantity: Decimal
    records: int


class MonthlyCount(BaseModel):
    month: str
    count: int


class CropAnalytics(BaseModel):
    total: int
    active: int
    by_status: list[LabelCount]
    by_type: list[CropTypeStat]  # active plantings only
    harvest_by_unit: list[HarvestUnitTotal]  # units differ, so they are never summed together
    harvests_monthly: list[MonthlyCount]


class InventoryCategoryStat(BaseModel):
    key: str
    items: int
    value: Decimal


class InventoryAnalytics(BaseModel):
    total_items: int
    total_value: Decimal
    by_category: list[InventoryCategoryStat]


class MonthlyAmount(BaseModel):
    month: str
    amount: Decimal


class HealthAnalytics(BaseModel):
    total_records: int
    total_cost: Decimal
    by_type: list[LabelCount]
    cost_monthly: list[MonthlyAmount]


class AnalyticsReport(BaseModel):
    start_date: date
    end_date: date
    months: int
    timezone: str
    finance: FinanceAnalytics
    sales: SalesAnalytics
    herd: HerdAnalytics
    dairy: DairyAnalytics
    crops: CropAnalytics
    inventory: InventoryAnalytics
    health: HealthAnalytics
