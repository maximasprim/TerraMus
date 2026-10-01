import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class DashboardSummary(BaseModel):
    """Spec §24/§68 - the top-card set a farm manager should understand
    within 10 seconds of opening the dashboard."""
    total_animals: int
    active_animals: int
    herd_value: Decimal
    animals_for_sale: int
    animals_reserved: int
    animals_sold: int
    todays_milk_liters: Decimal
    inventory_value: Decimal
    monthly_revenue: Decimal
    monthly_expenses: Decimal
    estimated_monthly_profit: Decimal
    low_stock_item_count: int
    vaccinations_due_count: int
    # Crop figures. dashboard_summary() has always computed these, but without
    # declared fields Pydantic silently dropped them from the response, so the
    # dashboard showed "undefined"/"NaN". Defaults keep any other constructor safe.
    total_crop_plantings: int = 0
    active_crop_plantings: int = 0
    crop_planting_value: Decimal = Decimal("0")
    low_stock_crop_listing_count: int = 0


class AnimalProfitabilityDetail(BaseModel):
    animal_id: uuid.UUID
    animal_number: str
    species: str
    status: str
    acquisition_cost: Decimal
    feed_cost: Decimal
    health_cost: Decimal
    total_investment: Decimal
    sale_price: Decimal | None  # actual, from a completed order item - None if not yet sold
    expected_sale_price: Decimal | None
    profit: Decimal | None  # actual profit if sold, else expected profit
    is_actual: bool  # True if `profit` reflects a real sale, False if it's an estimate


class ProfitabilityReport(BaseModel):
    start_date: date | None
    end_date: date | None
    animals: list[AnimalProfitabilityDetail]
    most_profitable: list[AnimalProfitabilityDetail]
    least_profitable: list[AnimalProfitabilityDetail]
    average_profit: Decimal | None
