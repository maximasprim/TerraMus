"""Chart-ready analytics for one organization (GET /reports/analytics).

Design notes
  * Every figure is a grouped aggregate computed in the database and scoped to
    the organization - no per-row Python loops, so cost doesn't grow with data.
  * Money agrees with the existing dashboard cards: income/expense come from the
    same finance ledger (finance_transactions) the cards use.
  * Months are calendar months in the *organization's* timezone, so a sale made
    at 23:30 on the 31st lands in the right month for a Kenyan farm.
  * Series are zero-filled over the whole window; nothing is silently skipped.
"""
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.timeseries import key_of, month_keys, month_start
from app.modules.commerce.models import Order
from app.modules.crops.models import INACTIVE_PLANTING_STATUSES, CropPlanting, HarvestRecord
from app.modules.dairy.models import MilkProductionRecord
from app.modules.finance.models import FinanceTransaction
from app.modules.health.models import HealthRecord
from app.modules.identity.models import Organization
from app.modules.inventory.models import InventoryItem, StockMovement
from app.modules.livestock.models import INACTIVE_STATUSES, Animal
from app.modules.payments.models import Payment
from app.modules.reporting import analytics_schemas as s

# Same set of order statuses the profitability report treats as "a real sale".
REVENUE_ORDER_STATUSES = ("paid", "processing", "ready_for_fulfillment", "dispatched", "delivered", "completed")
ZERO = Decimal("0")
TWO_PLACES = Decimal("0.01")
MILK_WINDOW_DAYS = 30


def _money(value) -> Decimal:
    return Decimal(value or 0).quantize(TWO_PLACES)


async def resolve_timezone(db: AsyncSession, org_id: uuid.UUID) -> tuple[str, date]:
    """The org's timezone (falling back to the platform default, then UTC) and
    today's date there. Names are validated against Postgres' own tz table, so a
    bad value in the DB can never produce an error."""
    configured = (await db.execute(select(Organization.timezone).where(Organization.id == org_id))).scalar_one_or_none()
    for candidate in (configured, get_settings().DEFAULT_TIMEZONE, "UTC"):
        if not candidate:
            continue
        known = (await db.execute(
            text("SELECT 1 FROM pg_timezone_names WHERE name = :n LIMIT 1"), {"n": candidate}
        )).scalar_one_or_none()
        if known:
            today = (await db.execute(
                text("SELECT CAST(timezone(CAST(:tz AS text), now()) AS date)"), {"tz": candidate}
            )).scalar_one()
            return candidate, today
    return "UTC", date.today()


def _local_ym(column, tz: str):
    """(year, month) of a timestamptz column as seen in `tz`."""
    local = func.timezone(tz, column)
    return func.extract("year", local), func.extract("month", local)


def _local_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    """Naive local datetimes [start 00:00, end+1day 00:00) for comparing against timezone(tz, col)."""
    return datetime(start.year, start.month, start.day), datetime(end.year, end.month, end.day) + timedelta(days=1)


def _ranked(mapping: dict[str, Decimal]) -> list[s.LabelAmount]:
    return [s.LabelAmount(key=k, amount=_money(v)) for k, v in sorted(mapping.items(), key=lambda kv: kv[1], reverse=True)]


# --- sections ---------------------------------------------------------------

async def _finance(db, org_id, keys: list[str], start: date, end: date) -> s.FinanceAnalytics:
    year = func.extract("year", FinanceTransaction.transaction_date)
    month = func.extract("month", FinanceTransaction.transaction_date)
    rows = (await db.execute(
        select(year, month, FinanceTransaction.transaction_type, FinanceTransaction.category, func.sum(FinanceTransaction.amount))
        .where(
            FinanceTransaction.organization_id == org_id,
            FinanceTransaction.transaction_date >= start,
            FinanceTransaction.transaction_date <= end,
        )
        .group_by(year, month, FinanceTransaction.transaction_type, FinanceTransaction.category)
    )).all()

    income = {k: ZERO for k in keys}
    expense = {k: ZERO for k in keys}
    income_cat: dict[str, Decimal] = {}
    expense_cat: dict[str, Decimal] = {}
    for y, m, kind, category, total in rows:
        key, amount = key_of(y, m), Decimal(total)
        if kind == "income":
            income[key] += amount
            income_cat[category] = income_cat.get(category, ZERO) + amount
        else:
            expense[key] += amount
            expense_cat[category] = expense_cat.get(category, ZERO) + amount

    total_income, total_expense = sum(income.values(), ZERO), sum(expense.values(), ZERO)
    return s.FinanceAnalytics(
        monthly=[s.MonthlyFinance(month=k, income=_money(income[k]), expense=_money(expense[k]), net=_money(income[k] - expense[k])) for k in keys],
        total_income=_money(total_income), total_expense=_money(total_expense), net=_money(total_income - total_expense),
        income_by_category=_ranked(income_cat), expense_by_category=_ranked(expense_cat),
    )


async def _sales(db, org_id, tz: str, keys: list[str], start: date, end: date) -> s.SalesAnalytics:
    lo, hi = _local_bounds(start, end)
    local_created = func.timezone(tz, Order.created_at)
    year, month = _local_ym(Order.created_at, tz)

    revenue_rows = (await db.execute(
        select(year, month, func.count(Order.id), func.coalesce(func.sum(Order.total_amount), 0))
        .where(Order.organization_id == org_id, Order.status.in_(REVENUE_ORDER_STATUSES), local_created >= lo, local_created < hi)
        .group_by(year, month)
    )).all()
    orders = {k: 0 for k in keys}
    revenue = {k: ZERO for k in keys}
    for y, m, count, total in revenue_rows:
        orders[key_of(y, m)] += count
        revenue[key_of(y, m)] += Decimal(total)

    status_rows = (await db.execute(
        select(Order.status, func.count(Order.id))
        .where(Order.organization_id == org_id, local_created >= lo, local_created < hi)
        .group_by(Order.status).order_by(func.count(Order.id).desc())
    )).all()

    local_completed = func.timezone(tz, Payment.completed_at)
    provider_rows = (await db.execute(
        select(Payment.provider, func.coalesce(func.sum(Payment.amount), 0), func.count(Payment.id))
        .where(Payment.organization_id == org_id, Payment.status == "successful", local_completed >= lo, local_completed < hi)
        .group_by(Payment.provider).order_by(func.sum(Payment.amount).desc())
    )).all()

    total_orders, total_revenue = sum(orders.values()), sum(revenue.values(), ZERO)
    return s.SalesAnalytics(
        monthly=[s.MonthlySales(month=k, orders=orders[k], revenue=_money(revenue[k])) for k in keys],
        orders_by_status=[s.LabelCount(key=k, count=c) for k, c in status_rows],
        payments_by_provider=[s.ProviderTotal(key=p, amount=_money(a), count=c) for p, a, c in provider_rows],
        total_orders=total_orders, total_revenue=_money(total_revenue),
        average_order_value=_money(total_revenue / total_orders) if total_orders else ZERO.quantize(TWO_PLACES),
    )


async def _herd(db, org_id) -> s.HerdAnalytics:
    status_rows = (await db.execute(
        select(Animal.status, func.count(Animal.id)).where(Animal.organization_id == org_id)
        .group_by(Animal.status).order_by(func.count(Animal.id).desc())
    )).all()
    species_rows = (await db.execute(
        select(Animal.species, func.count(Animal.id))
        .where(Animal.organization_id == org_id, Animal.status.not_in(INACTIVE_STATUSES))
        .group_by(Animal.species).order_by(func.count(Animal.id).desc())
    )).all()
    total = sum(c for _, c in status_rows)
    active = sum(c for k, c in status_rows if k not in INACTIVE_STATUSES)
    return s.HerdAnalytics(
        total=total, active=active,
        by_species=[s.LabelCount(key=k, count=c) for k, c in species_rows],
        by_status=[s.LabelCount(key=k, count=c) for k, c in status_rows],
    )


async def _dairy(db, org_id, today: date) -> s.DairyAnalytics:
    first = today - timedelta(days=MILK_WINDOW_DAYS - 1)
    rows = (await db.execute(
        select(MilkProductionRecord.production_date, MilkProductionRecord.rejected, func.sum(MilkProductionRecord.quantity_liters))
        .where(MilkProductionRecord.organization_id == org_id, MilkProductionRecord.production_date >= first, MilkProductionRecord.production_date <= today)
        .group_by(MilkProductionRecord.production_date, MilkProductionRecord.rejected)
    )).all()
    per_day = {first + timedelta(days=i): ZERO for i in range(MILK_WINDOW_DAYS)}
    rejected = ZERO
    for day, was_rejected, liters in rows:
        if was_rejected:
            rejected += Decimal(liters)
        else:
            per_day[day] += Decimal(liters)
    total = sum(per_day.values(), ZERO)
    return s.DairyAnalytics(
        daily=[s.DailyMilk(date=d, liters=_money(v)) for d, v in per_day.items()],
        total_liters=_money(total), average_per_day=_money(total / MILK_WINDOW_DAYS), rejected_liters=_money(rejected),
    )


async def _crops(db, org_id, tz: str, keys: list[str], start: date, end: date) -> s.CropAnalytics:
    status_rows = (await db.execute(
        select(CropPlanting.status, func.count(CropPlanting.id)).where(CropPlanting.organization_id == org_id)
        .group_by(CropPlanting.status).order_by(func.count(CropPlanting.id).desc())
    )).all()
    type_rows = (await db.execute(
        select(CropPlanting.crop_type, func.count(CropPlanting.id), func.coalesce(func.sum(CropPlanting.area_size), 0))
        .where(CropPlanting.organization_id == org_id, CropPlanting.status.not_in(INACTIVE_PLANTING_STATUSES))
        .group_by(CropPlanting.crop_type).order_by(func.count(CropPlanting.id).desc())
    )).all()

    # HarvestRecord has no organization_id of its own - scope it through its planting.
    lo, hi = _local_bounds(start, end)
    local_harvested = func.timezone(tz, HarvestRecord.harvested_at)
    in_window = (CropPlanting.organization_id == org_id, local_harvested >= lo, local_harvested < hi)
    unit_rows = (await db.execute(
        select(HarvestRecord.unit, func.sum(HarvestRecord.quantity), func.count(HarvestRecord.id))
        .join(CropPlanting, CropPlanting.id == HarvestRecord.planting_id).where(*in_window)
        .group_by(HarvestRecord.unit).order_by(func.count(HarvestRecord.id).desc())
    )).all()
    year, month = _local_ym(HarvestRecord.harvested_at, tz)
    month_rows = (await db.execute(
        select(year, month, func.count(HarvestRecord.id))
        .join(CropPlanting, CropPlanting.id == HarvestRecord.planting_id).where(*in_window).group_by(year, month)
    )).all()
    harvests = {k: 0 for k in keys}
    for y, m, c in month_rows:
        harvests[key_of(y, m)] += c

    total = sum(c for _, c in status_rows)
    active = sum(c for k, c in status_rows if k not in INACTIVE_PLANTING_STATUSES)
    return s.CropAnalytics(
        total=total, active=active,
        by_status=[s.LabelCount(key=k, count=c) for k, c in status_rows],
        by_type=[s.CropTypeStat(key=k, plantings=c, area=_money(a)) for k, c, a in type_rows],
        harvest_by_unit=[s.HarvestUnitTotal(unit=u, quantity=_money(q), records=c) for u, q, c in unit_rows],
        harvests_monthly=[s.MonthlyCount(month=k, count=harvests[k]) for k in keys],
    )


async def _inventory(db, org_id) -> s.InventoryAnalytics:
    """Same valuation rule as the dashboard card (stock x most recent purchase
    cost, ignoring items with no stock or no known cost), computed in two
    grouped queries instead of two queries per item."""
    items = (await db.execute(select(InventoryItem.id, InventoryItem.category).where(InventoryItem.organization_id == org_id))).all()
    stock = dict((await db.execute(
        select(StockMovement.item_id, func.sum(StockMovement.quantity)).where(StockMovement.organization_id == org_id).group_by(StockMovement.item_id)
    )).all())
    last_cost = dict((await db.execute(
        select(StockMovement.item_id, StockMovement.unit_cost)
        .where(StockMovement.organization_id == org_id, StockMovement.unit_cost.is_not(None))
        .distinct(StockMovement.item_id).order_by(StockMovement.item_id, StockMovement.moved_at.desc())
    )).all())

    counts: dict[str, int] = {}
    values: dict[str, Decimal] = {}
    for item_id, category in items:
        counts[category] = counts.get(category, 0) + 1
        qty, cost = Decimal(stock.get(item_id) or 0), last_cost.get(item_id)
        if qty > 0 and cost:
            values[category] = values.get(category, ZERO) + qty * Decimal(cost)
    by_category = sorted(
        (s.InventoryCategoryStat(key=c, items=n, value=_money(values.get(c, ZERO))) for c, n in counts.items()),
        key=lambda x: x.value, reverse=True,
    )
    return s.InventoryAnalytics(total_items=len(items), total_value=_money(sum(values.values(), ZERO)), by_category=by_category)


async def _health(db, org_id, tz: str, keys: list[str], start: date, end: date) -> s.HealthAnalytics:
    lo, hi = _local_bounds(start, end)
    local_performed = func.timezone(tz, HealthRecord.performed_at)
    in_window = (HealthRecord.organization_id == org_id, local_performed >= lo, local_performed < hi)
    type_rows = (await db.execute(
        select(HealthRecord.record_type, func.count(HealthRecord.id)).where(*in_window)
        .group_by(HealthRecord.record_type).order_by(func.count(HealthRecord.id).desc())
    )).all()
    year, month = _local_ym(HealthRecord.performed_at, tz)
    cost_rows = (await db.execute(
        select(year, month, func.coalesce(func.sum(HealthRecord.cost), 0)).where(*in_window).group_by(year, month)
    )).all()
    cost = {k: ZERO for k in keys}
    for y, m, total in cost_rows:
        cost[key_of(y, m)] += Decimal(total)
    return s.HealthAnalytics(
        total_records=sum(c for _, c in type_rows), total_cost=_money(sum(cost.values(), ZERO)),
        by_type=[s.LabelCount(key=k, count=c) for k, c in type_rows],
        cost_monthly=[s.MonthlyAmount(month=k, amount=_money(cost[k])) for k in keys],
    )


# --- entry point ------------------------------------------------------------

async def analytics_report(db: AsyncSession, org_id: uuid.UUID, months: int) -> s.AnalyticsReport:
    tz, today = await resolve_timezone(db, org_id)
    keys = month_keys(today, months)
    start = month_start(keys[0])
    return s.AnalyticsReport(
        start_date=start, end_date=today, months=months, timezone=tz,
        finance=await _finance(db, org_id, keys, start, today),
        sales=await _sales(db, org_id, tz, keys, start, today),
        herd=await _herd(db, org_id),
        dairy=await _dairy(db, org_id, today),
        crops=await _crops(db, org_id, tz, keys, start, today),
        inventory=await _inventory(db, org_id),
        health=await _health(db, org_id, tz, keys, start, today),
    )
