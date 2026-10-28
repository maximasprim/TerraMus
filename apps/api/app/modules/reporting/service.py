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


_ZERO = Decimal("0")
_CENT = Decimal("0.01")


def _d(value) -> Decimal:
    """Feedlot metrics are floats; money in this module is Decimal. Round once, here."""
    return Decimal(str(value or 0)).quantize(_CENT)


def _opt_d(value) -> Decimal | None:
    return None if value is None else Decimal(str(value)).quantize(_CENT)


async def _feedlot_rows(db: AsyncSession, org_id: uuid.UUID) -> dict[str, dict]:
    """Per-animal costs/revenue the feedlot module already computes (landed cost per
    head, standard feed, allocated overhead, exit amount). Sales made outside the web
    shop - typed in manually or imported from the worksheet - only exist there.
    Imported lazily so reporting never creates an import cycle with feedlot."""
    from app.modules.feedlot import service as feedlot_service
    data = await feedlot_service.profitability(db, org_id)
    return {row["animal_id"]: row for row in data["animals"]}


async def _animal_profitability_detail(
    db: AsyncSession, org_id: uuid.UUID, animal: Animal, feedlot_row: dict | None = None,
) -> schemas.AnimalProfitabilityDetail:
    logged_feed = await feed_cost_for_animal(db, org_id, animal.id)
    health_cost = await get_total_health_cost_for_animal(db, org_id, animal.id)
    acquisition_cost = Decimal(animal.acquisition_cost)
    feed_cost = logged_feed
    overhead_cost = _ZERO

    fr = feedlot_row
    if fr is not None:
        # Same figures the Feedlot page shows, so the two screens can never disagree.
        landed = _d(fr.get("landed_cost"))
        if landed > 0:
            acquisition_cost = landed
        modelled_feed = _d(fr.get("feed_cost"))
        # Standard ration cost when a ration plan exists; otherwise fall back to feed
        # actually logged against the animal. Never both - that would double count.
        feed_cost = modelled_feed if modelled_feed > 0 else logged_feed
        overhead_cost = _d(fr.get("ops_cost"))

    total_investment = acquisition_cost + feed_cost + health_cost + overhead_cost

    sale_price = await _actual_sale_price(db, org_id, animal.id)
    expected = Decimal(animal.expected_sale_price) if animal.expected_sale_price is not None else None
    sale_channel: str | None = None
    outcome = "active"
    estimate_source: str | None = None
    profit: Decimal | None = None
    is_actual = False

    fr_status = fr.get("status") if fr else None
    if sale_price is not None:                                    # existing behaviour: a paid web order
        sale_channel, outcome = "web", "sold"
        profit, is_actual = sale_price - total_investment, True
    elif fr_status == "sold":                                     # sold outside the web, recorded in feedlot
        outcome = "sold"
        revenue = _d(fr.get("revenue"))
        if revenue > 0:
            sale_channel, sale_price = "feedlot", revenue
            profit, is_actual = revenue - total_investment, True
        else:                                                     # sold, but no price/amount was ever recorded
            sale_channel, estimate_source = "feedlot", "sale_price_missing"
    elif fr_status in ("culled", "died"):                         # no revenue: the whole cost is a realised loss
        outcome = fr_status
        sale_channel = "feedlot"
        profit, is_actual = -total_investment, True
    elif expected is not None:                                    # existing behaviour
        profit, estimate_source = expected - total_investment, "expected_sale_price"
    elif fr is not None and fr.get("projected_revenue") is not None:
        expected = _d(fr["projected_revenue"])                    # latest weight x reference price/kg
        profit, estimate_source = expected - total_investment, "feedlot_projection"

    kwargs: dict = {}
    if fr is not None:
        kwargs = dict(
            intake_batch=fr.get("intake_batch"), sale_batch=fr.get("sale_batch"),
            exit_date=date.fromisoformat(fr["end_date"]) if (outcome != "active" and fr.get("end_date")) else None,
            entry_weight_kg=_opt_d(fr.get("entry_weight")), end_weight_kg=_opt_d(fr.get("end_weight")),
            weight_gain_kg=_opt_d(fr.get("overall_gain")), days_on_farm=fr.get("days_on_farm"),
            avg_daily_gain_kg=_opt_d(fr.get("adg")), breakeven_price_per_kg=_opt_d(fr.get("breakeven_price_per_kg")),
        )
        if sale_price is not None and fr.get("end_weight"):
            kwargs["price_per_kg"] = (sale_price / Decimal(str(fr["end_weight"]))).quantize(_CENT)

    return schemas.AnimalProfitabilityDetail(
        animal_id=animal.id, animal_number=animal.animal_number, species=animal.species, status=animal.status,
        acquisition_cost=acquisition_cost, feed_cost=feed_cost, health_cost=health_cost,
        total_investment=total_investment, sale_price=sale_price, expected_sale_price=expected,
        profit=profit, is_actual=is_actual, overhead_cost=overhead_cost, sale_channel=sale_channel,
        outcome=outcome, estimate_source=estimate_source, **kwargs,
    )


def _totals(details: list[schemas.AnimalProfitabilityDetail]) -> schemas.ProfitabilityTotals:
    t = schemas.ProfitabilityTotals()
    channels: dict[str, schemas.ProfitabilityChannelTotals] = {}
    for d in details:
        if d.outcome == "sold":
            t.head_sold += 1
        elif d.outcome == "culled":
            t.head_culled += 1
        elif d.outcome == "died":
            t.head_died += 1
        else:
            t.head_active += 1
        if not (d.is_actual and d.profit is not None):
            continue
        revenue = d.sale_price or _ZERO
        t.realised_revenue += revenue
        t.realised_cost += d.total_investment
        t.realised_profit += d.profit
        if d.outcome in ("culled", "died"):
            t.loss_from_culled_died += d.profit          # negative number
        elif d.sale_channel:
            c = channels.setdefault(d.sale_channel, schemas.ProfitabilityChannelTotals(channel=d.sale_channel))
            c.head += 1
            c.revenue += revenue
            c.cost += d.total_investment
            c.profit += d.profit
    t.by_channel = sorted(channels.values(), key=lambda c: c.channel)
    return t


async def profitability_report(db: AsyncSession, org_id: uuid.UUID) -> schemas.ProfitabilityReport:
    """Spec §25 - most/least profitable animals, average profit. Enriches the
    Phase 2 acquisition-only figure with real feed (Ph3) and health (Ph2b)
    costs now that those modules exist, without livestock/service.py needing
    to import them (see architecture.md Phase 6 note on why this lives here).

    Sales made outside the web shop (recorded in the feedlot module, manually or via
    the worksheet import) are folded in per animal; culled/died animals show as losses."""
    animals_result = await db.execute(select(Animal).where(Animal.organization_id == org_id))
    feedlot_rows = await _feedlot_rows(db, org_id)
    details = [
        await _animal_profitability_detail(db, org_id, animal, feedlot_rows.get(str(animal.id)))
        for animal in animals_result.scalars().all()
    ]

    with_profit = [d for d in details if d.profit is not None]
    ranked = sorted(with_profit, key=lambda d: d.profit, reverse=True)
    average = (sum((d.profit for d in with_profit), Decimal("0")) / len(with_profit)) if with_profit else None

    return schemas.ProfitabilityReport(
        start_date=None, end_date=None, animals=details,
        most_profitable=ranked[:5], least_profitable=list(reversed(ranked[-5:])) if ranked else [],
        average_profit=average.quantize(Decimal("0.01")) if average is not None else None,
        totals=_totals(details),
    )


async def animal_profitability_breakdown(
    db: AsyncSession, org_id: uuid.UUID, animal_id: uuid.UUID,
) -> schemas.AnimalProfitabilityBreakdown | None:
    """One animal, line by line: what was used (purchase, feed, health, overhead) and what
    came back (sale) or was lost (culled/died). None if the animal isn't in this org."""
    animal = (await db.execute(
        select(Animal).where(Animal.organization_id == org_id, Animal.id == animal_id)
    )).scalar_one_or_none()
    if animal is None:
        return None

    fr = (await _feedlot_rows(db, org_id)).get(str(animal.id))
    d = await _animal_profitability_detail(db, org_id, animal, fr)

    exit_row = sale_batch = None
    if fr is not None:
        from app.modules.feedlot.models import FeedlotExit, SaleBatch
        exit_row = (await db.execute(
            select(FeedlotExit).where(FeedlotExit.organization_id == org_id, FeedlotExit.animal_id == animal.id)
        )).scalar_one_or_none()
        if exit_row is not None and exit_row.sale_batch_id is not None:
            sale_batch = (await db.execute(
                select(SaleBatch).where(SaleBatch.organization_id == org_id, SaleBatch.id == exit_row.sale_batch_id)
            )).scalar_one_or_none()

    costs = [schemas.ProfitLine(
        category="purchase", label="Purchase & intake", amount=d.acquisition_cost,
        note=(f"Intake batch {d.intake_batch}: purchase + transport + fees + handlers, averaged per head"
              if d.intake_batch is not None else "Acquisition cost on the animal record"))]
    modelled = fr is not None and _d(fr.get("feed_cost")) > 0
    costs.append(schemas.ProfitLine(
        category="feed", label="Feed", amount=d.feed_cost,
        note=("Ration plan x days on farm" if modelled else "Feed logged against this animal")))
    costs.append(schemas.ProfitLine(category="health", label="Health & treatment", amount=d.health_cost,
                                    note="Recorded treatments, vaccinations and vet visits"))
    if fr is not None:
        costs.append(schemas.ProfitLine(
            category="overhead", label="Operations overhead", amount=d.overhead_cost,
            note=f"Overhead pool allocated over {d.days_on_farm} day(s) on the farm" if d.days_on_farm else None))

    returns: list[schemas.ProfitLine] = []
    reason = exit_row.reason if exit_row is not None else None
    if d.outcome == "sold" and d.sale_price is not None:
        note = "Paid web order" if d.sale_channel == "web" else None
        if d.sale_channel == "feedlot" and exit_row is not None:
            bits = []
            if exit_row.exit_weight_kg is not None and exit_row.price_per_kg is not None:
                bits.append(f"{float(exit_row.exit_weight_kg):g} kg x KES {float(exit_row.price_per_kg):g}/kg")
            bits.append(f"sold {exit_row.exit_date.isoformat()}")
            if sale_batch is not None:
                bits.append(f"sale batch {sale_batch.batch_number}")
            note = ", ".join(bits)
        returns.append(schemas.ProfitLine(category="sale", label="Sale", amount=d.sale_price, note=note))
    elif d.outcome == "sold":
        returns.append(schemas.ProfitLine(
            category="no_revenue", label="Sold - no price recorded", amount=_ZERO,
            note="Set the sale batch's price per kg to realise this sale"))
    elif d.outcome in ("culled", "died"):
        returns.append(schemas.ProfitLine(
            category="no_revenue", label=f"No revenue - {d.outcome}", amount=_ZERO,
            note=reason or "The full cost of this animal is a loss"))
    elif d.expected_sale_price is not None:
        returns.append(schemas.ProfitLine(
            category="projected_sale", label="Projected sale (not yet sold)", amount=d.expected_sale_price,
            note=("Latest weight x reference price per kg" if d.estimate_source == "feedlot_projection"
                  else "Expected sale price on the animal record")))

    total_cost = sum((c.amount for c in costs), _ZERO)
    total_return = sum((r.amount for r in returns), _ZERO)
    history = [
        schemas.WeightInterval(start=iv["from"], end=iv["to"], days=iv["days"],
                               gain_kg=_d(iv["gain"]), adg_kg=_opt_d(iv.get("adg")))
        for iv in (fr.get("intervals") or [])
    ] if fr is not None else []

    return schemas.AnimalProfitabilityBreakdown(
        summary=d, costs=costs, returns=returns, total_cost=total_cost, total_return=total_return,
        net=d.profit, net_is_actual=d.is_actual, reason=reason, weight_history=history,
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
