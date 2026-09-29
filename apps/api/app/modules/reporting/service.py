import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.livestock.service import get_herd_summary
from app.modules.livestock.models import Animal, INACTIVE_STATUSES
from app.modules.dairy.service import herd_summary as dairy_herd_summary
from app.modules.crops.service import get_crop_summary
from app.modules.commerce.service import list_low_stock_crop_listings
from app.modules.inventory.service import low_stock_items, current_stock, feed_cost_for_animal
from app.modules.inventory.models import InventoryItem, StockMovement
from app.modules.health.service import list_due_follow_ups, get_total_health_cost_for_animal
from app.modules.finance.service import get_summary as finance_summary
from app.modules.commerce.models import Order, OrderItem
from app.modules.reporting import schemas


async def _inventory_value(db: AsyncSession, org_id: uuid.UUID) -> Decimal:
    """Approximation: current_stock * most recent purchase unit_cost per item.
    A real cost-accounting method (FIFO/weighted-average) is future work -
    this is explicitly a rough valuation for the dashboard card, not a
    financial-statement-grade figure."""
    items_result = await db.execute(select(InventoryItem).where(InventoryItem.organization_id == org_id))
    total = Decimal("0")
    for item in items_result.scalars().all():
        stock = await current_stock(db, item.id)
        if stock <= 0:
            continue
        last_cost_result = await db.execute(
            select(StockMovement.unit_cost)
            .where(StockMovement.item_id == item.id, StockMovement.unit_cost.is_not(None))
            .order_by(StockMovement.moved_at.desc())
            .limit(1)
        )
        unit_cost = last_cost_result.scalar_one_or_none()
        if unit_cost:
            total += stock * Decimal(unit_cost)
    return total


async def dashboard_summary(db: AsyncSession, org_id: uuid.UUID) -> schemas.DashboardSummary:
    herd = await get_herd_summary(db, org_id)
    milk = await dairy_herd_summary(db, org_id, date.today())
    crops = await get_crop_summary(db, org_id)
    low_stock_crop_listings = await list_low_stock_crop_listings(db, org_id)
    inventory_value = await _inventory_value(db, org_id)
    low_stock = await low_stock_items(db, org_id)
    due_follow_ups = await list_due_follow_ups(db, org_id, within_days=14)

    month_start = date.today().replace(day=1)
    finance = await finance_summary(db, org_id, month_start, date.today())

    return schemas.DashboardSummary(
        total_animals=herd["total_animals"],
        active_animals=herd["active_animals"],
        herd_value=Decimal(herd["herd_value"]),
        animals_for_sale=herd["for_sale"],
        animals_reserved=herd["reserved"],
        animals_sold=herd["sold"],
        todays_milk_liters=milk.total_liters,
        inventory_value=inventory_value,
        monthly_revenue=finance.total_income,
        monthly_expenses=finance.total_expense,
        estimated_monthly_profit=finance.net_income,
        low_stock_item_count=len(low_stock),
        vaccinations_due_count=len(due_follow_ups),
        total_crop_plantings=crops["total_plantings"],
        active_crop_plantings=crops["active_plantings"],
        crop_planting_value=Decimal(crops["total_planting_value"]),
        low_stock_crop_listing_count=len(low_stock_crop_listings),
    )


async def _actual_sale_price(db: AsyncSession, org_id: uuid.UUID, animal_id: uuid.UUID) -> Decimal | None:
    result = await db.execute(
        select(OrderItem.price)
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            Order.organization_id == org_id, OrderItem.animal_id == animal_id,
            Order.status.in_(("paid", "processing", "ready_for_fulfillment", "dispatched", "delivered", "completed")),
        )
        .limit(1)
    )
    price = result.scalar_one_or_none()
    return Decimal(price) if price is not None else None


async def _animal_profitability_detail(db: AsyncSession, org_id: uuid.UUID, animal: Animal) -> schemas.AnimalProfitabilityDetail:
    feed_cost = await feed_cost_for_animal(db, org_id, animal.id)
    health_cost = await get_total_health_cost_for_animal(db, org_id, animal.id)
    acquisition_cost = Decimal(animal.acquisition_cost)
    total_investment = acquisition_cost + feed_cost + health_cost

    sale_price = await _actual_sale_price(db, org_id, animal.id)
    if sale_price is not None:
        profit, is_actual = sale_price - total_investment, True
    elif animal.expected_sale_price is not None:
        profit, is_actual = Decimal(animal.expected_sale_price) - total_investment, False
    else:
        profit, is_actual = None, False

    return schemas.AnimalProfitabilityDetail(
        animal_id=animal.id, animal_number=animal.animal_number, species=animal.species, status=animal.status,
        acquisition_cost=acquisition_cost, feed_cost=feed_cost, health_cost=health_cost,
        total_investment=total_investment, sale_price=sale_price, expected_sale_price=animal.expected_sale_price,
        profit=profit, is_actual=is_actual,
    )


async def profitability_report(db: AsyncSession, org_id: uuid.UUID) -> schemas.ProfitabilityReport:
    """Spec §25 - most/least profitable animals, average profit. Enriches the
    Phase 2 acquisition-only figure with real feed (Ph3) and health (Ph2b)
    costs now that those modules exist, without livestock/service.py needing
    to import them (see architecture.md Phase 6 note on why this lives here)."""
    animals_result = await db.execute(select(Animal).where(Animal.organization_id == org_id))
    details = [
        await _animal_profitability_detail(db, org_id, animal)
        for animal in animals_result.scalars().all()
    ]

    with_profit = [d for d in details if d.profit is not None]
    ranked = sorted(with_profit, key=lambda d: d.profit, reverse=True)
    average = (sum((d.profit for d in with_profit), Decimal("0")) / len(with_profit)) if with_profit else None

    return schemas.ProfitabilityReport(
        start_date=None, end_date=None, animals=details,
        most_profitable=ranked[:5], least_profitable=list(reversed(ranked[-5:])) if ranked else [],
        average_profit=average.quantize(Decimal("0.01")) if average is not None else None,
    )


async def render_livestock_report_pdf(db: AsyncSession, org_id: uuid.UUID) -> bytes:
    """Spec §44 PDF export - same underlying data as export_livestock_csv,
    rendered as a table via reportlab instead of written as CSV rows. Kept
    in this module (not a separate pdf.py like finance's) since, unlike an
    invoice, there's no reusable non-DB rendering function worth splitting
    out yet - this is currently the only PDF report reporting/ produces."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    import io

    result = await db.execute(select(Animal).where(Animal.organization_id == org_id))
    animals = list(result.scalars().all())

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4),
        topMargin=15 * mm, bottomMargin=15 * mm, leftMargin=15 * mm, rightMargin=15 * mm,
    )
    styles = getSampleStyleSheet()
    story = [Paragraph("Livestock Report", styles["Title"]), Spacer(1, 4 * mm)]

    header = ["Animal #", "Species", "Breed", "Sex", "Status", "Weight", "Acq. Cost", "Value"]
    rows = [header]
    for a in animals:
        rows.append([
            a.animal_number, a.species, a.breed or "-", a.sex, a.status,
            str(a.current_weight or "-"), f"{a.acquisition_cost:,.2f}", f"{(a.current_value or 0):,.2f}",
        ])

    table = Table(rows, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1b4332")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f0")]),
    ]))
    story.append(table)
    doc.build(story)
    return buffer.getvalue()
