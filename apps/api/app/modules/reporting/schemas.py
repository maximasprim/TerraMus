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

    # --- Added so sales made OUTSIDE the web shop (recorded in the feedlot module,
    # manually or via worksheet import) show up here too. All optional with
    # defaults: existing consumers that ignore them keep working unchanged.
    overhead_cost: Decimal = Decimal("0")   # allocated feedlot overhead (operations cost); 0 for non-feedlot animals
    sale_channel: str | None = None          # "web" | "feedlot" - where the actual sale was recorded
    outcome: str = "active"                  # "sold" | "culled" | "died" | "active"
    estimate_source: str | None = None       # why a figure is an estimate: "expected_sale_price" | "feedlot_projection"
    intake_batch: int | None = None
    sale_batch: int | None = None
    exit_date: date | None = None
    entry_weight_kg: Decimal | None = None
    end_weight_kg: Decimal | None = None     # sale / exit weight, or latest weight while still on the farm
    weight_gain_kg: Decimal | None = None
    days_on_farm: int | None = None
    avg_daily_gain_kg: Decimal | None = None
    price_per_kg: Decimal | None = None
    breakeven_price_per_kg: Decimal | None = None


class ProfitabilityChannelTotals(BaseModel):
    """Realised (actual) money in vs. out for one sales channel."""
    channel: str                       # "web" | "feedlot"
    head: int = 0
    revenue: Decimal = Decimal("0")
    cost: Decimal = Decimal("0")
    profit: Decimal = Decimal("0")


class ProfitabilityTotals(BaseModel):
    head_sold: int = 0
    head_culled: int = 0
    head_died: int = 0
    head_active: int = 0
    realised_revenue: Decimal = Decimal("0")
    realised_cost: Decimal = Decimal("0")        # includes the cost of culled/died animals (a loss)
    realised_profit: Decimal = Decimal("0")
    loss_from_culled_died: Decimal = Decimal("0")
    by_channel: list[ProfitabilityChannelTotals] = []


class ProfitabilityReport(BaseModel):
    start_date: date | None
    end_date: date | None
    animals: list[AnimalProfitabilityDetail]
    most_profitable: list[AnimalProfitabilityDetail]
    least_profitable: list[AnimalProfitabilityDetail]
    average_profit: Decimal | None
    totals: ProfitabilityTotals | None = None


class ProfitLine(BaseModel):
    category: str                      # "purchase" | "feed" | "health" | "overhead" | "sale" | "no_revenue"
    label: str
    amount: Decimal
    note: str | None = None


class WeightInterval(BaseModel):
    start: str
    end: str
    days: int
    gain_kg: Decimal
    adg_kg: Decimal | None = None


class AnimalProfitabilityBreakdown(BaseModel):
    """Everything that went into one animal, and what came back (or was lost)."""
    summary: AnimalProfitabilityDetail
    costs: list[ProfitLine]            # what was used
    returns: list[ProfitLine]          # what was gotten back (empty/zero revenue line for culled/died)
    total_cost: Decimal
    total_return: Decimal
    net: Decimal | None                # None while the animal is still on the farm with nothing to project
    net_is_actual: bool
    reason: str | None = None          # cull / death reason when recorded
    weight_history: list[WeightInterval] = []
