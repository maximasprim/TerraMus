"""Crop sales (made outside the web shop), per-planting costs, and the profit that follows from them.

Money rules, in one place:

* Web sales are NOT stored here. They already exist as order items linked to the planting; this module
  only reads them. Sales made off the web (to a trader, a co-operative, at the market) are `CropSale` rows.
* Everything that reaches the finance ledger is keyed to what it records (reference_type + reference_id),
  checked first, and backed by a partial unique index (migration 0037). The ledger is append-only, so a
  duplicate could never be removed - it must be impossible, not merely unlikely.
* A wrong entry is VOIDED, never edited or deleted: the row stays (flagged, with a reason) and the ledger
  gets a reversing entry dated on the void date, so history stays honest and the books net out.
* Imports are idempotent: every row gets a deterministic key, so importing the same sheet twice adds nothing.
"""
from __future__ import annotations

import csv
import hashlib
import io
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.commerce.models import Listing, Order, OrderItem
from app.modules.crops import economics_schemas as s
from app.modules.crops.models import (
    INACTIVE_PLANTING_STATUSES, INPUT_COST_CATEGORIES, LABOUR_COST_CATEGORIES,
    CropCost, CropPlanting, CropSale, HarvestRecord,
)
from app.modules.customers.models import Customer
from app.modules.finance.models import FinanceTransaction
from app.modules.receivables.models import AccountEntry
from app.modules.cycles.deps import CycleSel, apply_col

ZERO = Decimal("0")
CENT = Decimal("0.01")
ACTIVITY = "crops"
REVENUE_ORDER_STATUSES = ("paid", "processing", "ready_for_fulfillment", "dispatched", "delivered", "completed")
STOCK_RELEASED_STATUSES = ("cancelled", "failed", "refunded")
SALE_REF, SALE_VOID_REF = "crop_sale", "crop_sale_void"
COST_REF, COST_VOID_REF = "crop_cost", "crop_cost_void"
PLANTING_REF = "crop_planting"


def money(v) -> Decimal:
    return Decimal(str(v if v is not None else 0)).quantize(CENT)


def _404(what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found")


# --------------------------------------------------------------------------- stock

async def _harvest_units(db: AsyncSession, planting_id: uuid.UUID) -> list[str]:
    rows = (await db.execute(
        select(HarvestRecord.unit, func.count(HarvestRecord.id)).where(HarvestRecord.planting_id == planting_id)
        .group_by(HarvestRecord.unit).order_by(func.count(HarvestRecord.id).desc()))).all()
    return [r[0] for r in rows]


async def _stock_numbers(db: AsyncSession, org_id: uuid.UUID, planting_id: uuid.UUID) -> dict[str, Decimal]:
    harvested = Decimal((await db.execute(select(func.coalesce(func.sum(HarvestRecord.quantity), 0))
                                          .where(HarvestRecord.planting_id == planting_id))).scalar_one())
    web = Decimal((await db.execute(
        select(func.coalesce(func.sum(OrderItem.quantity), 0)).join(Order, Order.id == OrderItem.order_id)
        .where(OrderItem.crop_planting_id == planting_id, Order.organization_id == org_id,
               Order.status.notin_(STOCK_RELEASED_STATUSES)))).scalar_one())
    direct = Decimal((await db.execute(
        select(func.coalesce(func.sum(CropSale.quantity), 0)).where(
            CropSale.planting_id == planting_id, CropSale.organization_id == org_id, CropSale.voided_at.is_(None)))).scalar_one())
    return {"harvested": harvested, "web": web, "direct": direct, "available": harvested - web - direct}


async def _get_planting(db: AsyncSession, org_id: uuid.UUID, planting_id: uuid.UUID) -> CropPlanting:
    p = (await db.execute(select(CropPlanting).where(
        CropPlanting.id == planting_id, CropPlanting.organization_id == org_id))).scalar_one_or_none()
    if p is None:
        raise _404("Crop planting")
    return p


# --------------------------------------------------------------------------- ledger postings (each at most once)

async def _ledger_refs(db: AsyncSession, org_id: uuid.UUID, ref_type: str, ids: list[uuid.UUID]) -> set[uuid.UUID]:
    if not ids:
        return set()
    cash = (await db.execute(select(FinanceTransaction.reference_id).where(
        FinanceTransaction.organization_id == org_id, FinanceTransaction.reference_type == ref_type,
        FinanceTransaction.reference_id.in_(ids)))).scalars().all()
    credit = (await db.execute(select(AccountEntry.reference_id).where(
        AccountEntry.organization_id == org_id, AccountEntry.reference_type == ref_type,
        AccountEntry.entry_type == "charge", AccountEntry.reference_id.in_(ids)))).scalars().all() if ref_type == SALE_REF else []
    return {*cash, *credit}


async def post_sale(db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID | None, sale: CropSale,
                    planting: CropPlanting, recorded: set[uuid.UUID] | None = None) -> str:
    """-> 'income_posted' | 'charged_to_customer_account' | 'already_recorded' | 'no_price'. Does not commit."""
    if sale.amount is None or Decimal(sale.amount) <= 0:
        return "no_price"                                         # a ledger entry of 0 is meaningless
    done = recorded if recorded is not None else await _ledger_refs(db, org_id, SALE_REF, [sale.id])
    if sale.id in done:
        return "already_recorded"
    desc = f"Sale of {Decimal(sale.quantity):g} {sale.unit} {planting.crop_type} ({planting.planting_number})"
    if sale.buyer_name:
        desc += f" to {sale.buyer_name}"
    try:
        async with db.begin_nested():                             # savepoint: a racing duplicate never poisons the batch
            if sale.customer_id:                                  # on credit: income is recorded as the customer pays
                db.add(AccountEntry(organization_id=org_id, customer_id=sale.customer_id, entry_type="charge",
                                    amount=sale.amount, entry_date=sale.sale_date, reference_type=SALE_REF,
                                    reference_id=sale.id, description=desc[:255], farm_id=planting.farm_id,
                                    activity=ACTIVITY, created_by=user_id))
            else:                                                 # cash sale: income now
                db.add(FinanceTransaction(organization_id=org_id, transaction_type="income", category="crop_sale",
                                          amount=sale.amount, transaction_date=sale.sale_date, farm_id=planting.farm_id,
                                          activity=ACTIVITY, description=desc[:255], reference_type=SALE_REF,
                                          reference_id=sale.id, created_by=user_id))
            await db.flush()
    except IntegrityError:
        return "already_recorded"
    if recorded is not None:
        recorded.add(sale.id)
    return "charged_to_customer_account" if sale.customer_id else "income_posted"


async def post_cost(db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID | None, cost: CropCost,
                    planting: CropPlanting, recorded: set[uuid.UUID] | None = None) -> str:
    done = recorded if recorded is not None else await _ledger_refs(db, org_id, COST_REF, [cost.id])
    if cost.id in done:
        return "already_recorded"
    try:
        async with db.begin_nested():
            db.add(FinanceTransaction(
                organization_id=org_id, transaction_type="expense", category=cost.category, amount=cost.amount,
                transaction_date=cost.cost_date, farm_id=planting.farm_id, activity=ACTIVITY,
                description=(f"{cost.description or cost.category} ({planting.planting_number})")[:255],
                reference_type=COST_REF, reference_id=cost.id, created_by=user_id))
            await db.flush()
    except IntegrityError:
        return "already_recorded"
    if recorded is not None:
        recorded.add(cost.id)
    return "posted"


async def post_planting_purchase(db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID | None,
                                 planting: CropPlanting, recorded: set[uuid.UUID]) -> str:
    """Seed / seedlings / land-prep cost entered when the planting was created."""
    if planting.acquisition_cost is None or Decimal(planting.acquisition_cost) <= 0:
        return "no_cost"
    if planting.id in recorded:
        return "already_recorded"
    try:
        async with db.begin_nested():
            db.add(FinanceTransaction(
                organization_id=org_id, transaction_type="expense", category="seed", amount=planting.acquisition_cost,
                transaction_date=planting.planting_date, farm_id=planting.farm_id, activity=ACTIVITY,
                description=f"Planting cost: {planting.crop_type} ({planting.planting_number})",
                reference_type=PLANTING_REF, reference_id=planting.id, created_by=user_id))
            await db.flush()
    except IntegrityError:
        return "already_recorded"
    recorded.add(planting.id)
    return "posted"


async def _reverse(db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID, *, original_ref: str, void_ref: str,
                   record_id: uuid.UUID, kind: str, category: str, amount, farm_id, reason: str, label: str) -> bool:
    """Reverse a ledger entry that exists for this record (a negative entry of the same kind and category,
    dated today). Returns False when there was nothing in the ledger to reverse."""
    original = (await db.execute(select(FinanceTransaction.id).where(
        FinanceTransaction.organization_id == org_id, FinanceTransaction.reference_type == original_ref,
        FinanceTransaction.reference_id == record_id))).scalar_one_or_none()
    if original is None:
        return False
    try:
        async with db.begin_nested():
            db.add(FinanceTransaction(
                organization_id=org_id, transaction_type=kind, category=category, amount=-Decimal(amount),
                transaction_date=date.today(), farm_id=farm_id, activity=ACTIVITY,
                description=f"VOID {label}: {reason}"[:255], reference_type=void_ref, reference_id=record_id,
                created_by=user_id))
            await db.flush()
    except IntegrityError:
        pass                                                      # already reversed
    return True


# --------------------------------------------------------------------------- sales

def _stock_warning(planting: CropPlanting, unit: str, available_after: Decimal) -> str | None:
    if available_after >= 0:
        return None
    return (f"{planting.planting_number}: this sale is {abs(available_after):g} {unit} more than the harvests recorded "
            f"so far. If the produce was harvested, record the missing harvest so stock stays accurate.")


async def _check_customer(db: AsyncSession, org_id: uuid.UUID, customer_id: uuid.UUID | None) -> None:
    if customer_id and not (await db.execute(select(Customer.id).where(
            Customer.id == customer_id, Customer.organization_id == org_id))).first():
        raise _404("Customer")


async def _resolve_unit(db: AsyncSession, planting: CropPlanting, unit: str | None) -> str:
    units = await _harvest_units(db, planting.id)
    if unit is None:
        unit = units[0] if units else planting.yield_unit
        if not unit:
            raise HTTPException(422, "Say which unit this was sold in (kg, bags, crates...): no harvest has been "
                                     "recorded for this planting yet, so there is nothing to default to.")
    elif units and unit not in units:
        raise HTTPException(422, f"Harvests for {planting.planting_number} are recorded in {', '.join(units)}; "
                                 f"record the sale in the same unit (you gave '{unit}').")
    return unit


def _amounts(quantity: Decimal, unit_price: Decimal | None, amount: Decimal | None) -> tuple[Decimal, Decimal]:
    """The total is the truth. Given a price, total = quantity x price; given a total, price = total / quantity."""
    if amount is None:
        amount = money(quantity * unit_price)
    if unit_price is None:
        unit_price = money(amount / quantity)
    return money(unit_price), money(amount)


async def _with_flags(db: AsyncSession, org_id: uuid.UUID, sales: list[CropSale]) -> list[s.CropSaleOut]:
    posted = await _ledger_refs(db, org_id, SALE_REF, [x.id for x in sales])
    return [s.CropSaleOut.model_validate(x).model_copy(update={"in_finance": x.id in posted}) for x in sales]


async def record_sale(db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID, planting_id: uuid.UUID,
                      req: s.CropSaleCreate) -> s.CropSaleResult:
    planting = await _get_planting(db, org_id, planting_id)
    await _check_customer(db, org_id, req.customer_id)
    unit = await _resolve_unit(db, planting, req.unit)
    unit_price, amount = _amounts(Decimal(req.quantity), req.unit_price, req.amount)
    stock = await _stock_numbers(db, org_id, planting.id)

    sale = CropSale(organization_id=org_id, planting_id=planting.id, sale_date=req.sale_date, quantity=req.quantity,
                    unit=unit, unit_price=unit_price, amount=amount, customer_id=req.customer_id,
                    buyer_name=req.buyer_name, notes=req.notes, source="manual", created_by=user_id)
    db.add(sale)
    await db.flush()
    ledger = "not_posted"
    if req.post_to_finance:
        outcome = await post_sale(db, org_id, user_id, sale, planting)
        ledger = outcome if outcome in ("income_posted", "charged_to_customer_account") else "not_posted"
    await db.commit()
    await db.refresh(sale)
    return s.CropSaleResult(sale=(await _with_flags(db, org_id, [sale]))[0], ledger=ledger,
                            stock_warning=_stock_warning(planting, unit, stock["available"] - Decimal(req.quantity)))


async def list_sales(db: AsyncSession, org_id: uuid.UUID, planting_id: uuid.UUID) -> list[s.CropSaleOut]:
    await _get_planting(db, org_id, planting_id)
    rows = (await db.execute(select(CropSale).where(CropSale.organization_id == org_id, CropSale.planting_id == planting_id)
                             .order_by(CropSale.sale_date.desc(), CropSale.created_at.desc()))).scalars().all()
    return await _with_flags(db, org_id, list(rows))


async def void_sale(db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID, sale_id: uuid.UUID, reason: str) -> s.CropSaleOut:
    sale = (await db.execute(select(CropSale).where(CropSale.id == sale_id, CropSale.organization_id == org_id))).scalar_one_or_none()
    if sale is None:
        raise _404("Crop sale")
    if sale.voided_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This sale is already voided")
    planting = await _get_planting(db, org_id, sale.planting_id)
    charged = (await db.execute(select(AccountEntry.id).where(
        AccountEntry.organization_id == org_id, AccountEntry.reference_type == SALE_REF, AccountEntry.reference_id == sale.id,
        AccountEntry.entry_type == "charge"))).first()
    if charged:
        raise HTTPException(status.HTTP_409_CONFLICT, (
            "This sale was charged to a customer's account. Correct it from that customer's account "
            "(Receivables) so their balance stays right, then record the right sale."))
    sale.voided_at, sale.void_reason, sale.voided_by = datetime.now(timezone.utc), reason, user_id
    await _reverse(db, org_id, user_id, original_ref=SALE_REF, void_ref=SALE_VOID_REF, record_id=sale.id, kind="income",
                   category="crop_sale", amount=sale.amount, farm_id=planting.farm_id, reason=reason,
                   label=f"crop sale {planting.planting_number}")
    await db.commit()
    await db.refresh(sale)
    return (await _with_flags(db, org_id, [sale]))[0]


# --------------------------------------------------------------------------- costs

async def _cost_out(db: AsyncSession, org_id: uuid.UUID, costs: list[CropCost]) -> list[s.CropCostOut]:
    posted = await _ledger_refs(db, org_id, COST_REF, [c.id for c in costs])
    return [s.CropCostOut.model_validate(c).model_copy(update={"in_finance": c.id in posted}) for c in costs]


async def record_cost(db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID, planting_id: uuid.UUID,
                      req: s.CropCostCreate) -> s.CropCostOut:
    planting = await _get_planting(db, org_id, planting_id)
    cost = CropCost(organization_id=org_id, planting_id=planting.id, cost_date=req.cost_date, category=req.category,
                    amount=req.amount, description=req.description, source="manual", created_by=user_id)
    db.add(cost)
    await db.flush()
    if req.post_to_finance:
        await post_cost(db, org_id, user_id, cost, planting)
    await db.commit()
    await db.refresh(cost)
    return (await _cost_out(db, org_id, [cost]))[0]


async def list_costs(db: AsyncSession, org_id: uuid.UUID, planting_id: uuid.UUID) -> list[s.CropCostOut]:
    await _get_planting(db, org_id, planting_id)
    rows = (await db.execute(select(CropCost).where(CropCost.organization_id == org_id, CropCost.planting_id == planting_id)
                             .order_by(CropCost.cost_date.desc(), CropCost.created_at.desc()))).scalars().all()
    return await _cost_out(db, org_id, list(rows))


async def void_cost(db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID, cost_id: uuid.UUID, reason: str) -> s.CropCostOut:
    cost = (await db.execute(select(CropCost).where(CropCost.id == cost_id, CropCost.organization_id == org_id))).scalar_one_or_none()
    if cost is None:
        raise _404("Crop cost")
    if cost.voided_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This cost is already voided")
    planting = await _get_planting(db, org_id, cost.planting_id)
    cost.voided_at, cost.void_reason, cost.voided_by = datetime.now(timezone.utc), reason, user_id
    await _reverse(db, org_id, user_id, original_ref=COST_REF, void_ref=COST_VOID_REF, record_id=cost.id, kind="expense",
                   category=cost.category, amount=cost.amount, farm_id=planting.farm_id, reason=reason,
                   label=f"crop cost {planting.planting_number}")
    await db.commit()
    await db.refresh(cost)
    return (await _cost_out(db, org_id, [cost]))[0]


# --------------------------------------------------------------------------- economics (profit per planting)

async def economics_for(db: AsyncSession, org_id: uuid.UUID, plantings: list[CropPlanting]) -> list[s.PlantingEconomics]:
    """One set of grouped queries for any number of plantings (no per-planting round trips)."""
    if not plantings:
        return []
    ids = [p.id for p in plantings]

    cost_rows = (await db.execute(select(CropCost.planting_id, CropCost.category, func.sum(CropCost.amount)).where(
        CropCost.organization_id == org_id, CropCost.planting_id.in_(ids), CropCost.voided_at.is_(None))
        .group_by(CropCost.planting_id, CropCost.category))).all()
    costs: dict[uuid.UUID, dict[str, Decimal]] = defaultdict(lambda: defaultdict(lambda: ZERO))
    for pid, cat, total in cost_rows:
        costs[pid][cat] += Decimal(total)

    direct_rows = (await db.execute(select(CropSale.planting_id, func.sum(CropSale.amount), func.sum(CropSale.quantity)).where(
        CropSale.organization_id == org_id, CropSale.planting_id.in_(ids), CropSale.voided_at.is_(None))
        .group_by(CropSale.planting_id))).all()
    direct = {pid: (Decimal(a), Decimal(q)) for pid, a, q in direct_rows}

    web_rev_rows = (await db.execute(select(OrderItem.crop_planting_id, func.sum(OrderItem.quantity * OrderItem.price),
                                            func.sum(OrderItem.quantity))
        .join(Order, Order.id == OrderItem.order_id).where(
            Order.organization_id == org_id, OrderItem.crop_planting_id.in_(ids), Order.status.in_(REVENUE_ORDER_STATUSES))
        .group_by(OrderItem.crop_planting_id))).all()
    web_rev = {pid: (Decimal(a), Decimal(q)) for pid, a, q in web_rev_rows}

    web_committed_rows = (await db.execute(select(OrderItem.crop_planting_id, func.sum(OrderItem.quantity))
        .join(Order, Order.id == OrderItem.order_id).where(
            Order.organization_id == org_id, OrderItem.crop_planting_id.in_(ids), Order.status.notin_(STOCK_RELEASED_STATUSES))
        .group_by(OrderItem.crop_planting_id))).all()
    web_committed = {pid: Decimal(q) for pid, q in web_committed_rows}

    harvested = {pid: Decimal(q) for pid, q in (await db.execute(
        select(HarvestRecord.planting_id, func.sum(HarvestRecord.quantity)).where(HarvestRecord.planting_id.in_(ids))
        .group_by(HarvestRecord.planting_id))).all()}

    unit_counts: dict[uuid.UUID, Counter] = defaultdict(Counter)
    for pid, unit, n in (await db.execute(select(HarvestRecord.planting_id, HarvestRecord.unit, func.count(HarvestRecord.id))
                                          .where(HarvestRecord.planting_id.in_(ids)).group_by(HarvestRecord.planting_id, HarvestRecord.unit))).all():
        unit_counts[pid][unit] = n

    listed: dict[uuid.UUID, Decimal] = {}
    for pid, price in (await db.execute(select(Listing.crop_planting_id, Listing.price).where(
            Listing.organization_id == org_id, Listing.crop_planting_id.in_(ids), Listing.price.is_not(None))
            .order_by(Listing.created_at))).all():
        listed[pid] = Decimal(price)

    out: list[s.PlantingEconomics] = []
    for p in plantings:
        c = costs.get(p.id, {})
        inputs = sum((v for k, v in c.items() if k in INPUT_COST_CATEGORIES), ZERO)
        labour = sum((v for k, v in c.items() if k in LABOUR_COST_CATEGORIES), ZERO)
        other = sum((v for k, v in c.items() if k not in INPUT_COST_CATEGORIES + LABOUR_COST_CATEGORIES), ZERO)
        acquisition = Decimal(p.acquisition_cost or 0)
        investment = acquisition + inputs + labour + other
        rev_direct, q_direct = direct.get(p.id, (ZERO, ZERO))
        rev_web, q_web = web_rev.get(p.id, (ZERO, ZERO))
        revenue = rev_direct + rev_web
        got = harvested.get(p.id, ZERO)
        on_hand = got - web_committed.get(p.id, ZERO) - q_direct
        unit = (unit_counts[p.id].most_common(1)[0][0] if unit_counts.get(p.id) else p.yield_unit)
        price = listed.get(p.id)
        sold_q = q_web + q_direct
        out.append(s.PlantingEconomics(
            planting_id=p.id, planting_number=p.planting_number, crop_type=p.crop_type, variety=p.variety, status=p.status,
            is_closed=p.status in INACTIVE_PLANTING_STATUSES, unit=unit,
            acquisition_cost=money(acquisition), input_cost=money(inputs), labour_cost=money(labour), other_cost=money(other),
            total_investment=money(investment), revenue_web=money(rev_web), revenue_direct=money(rev_direct),
            total_revenue=money(revenue), profit=money(revenue - investment), quantity_harvested=got,
            quantity_sold_web=q_web, quantity_sold_direct=q_direct, stock_on_hand=on_hand, listed_price=price,
            stock_value=money(on_hand * price) if price is not None and on_hand > 0 else None,
            avg_price_per_unit=money(revenue / sold_q) if sold_q > 0 and revenue > 0 else None,
            cost_per_unit=money(investment / got) if got > 0 and investment > 0 else None))
    return out


async def all_economics(db: AsyncSession, org_id: uuid.UUID, cycle: CycleSel | None = None) -> s.CropEconomicsReport:
    q = apply_col(select(CropPlanting).where(CropPlanting.organization_id == org_id), CropPlanting.production_cycle_id, cycle)
    plantings = (await db.execute(q.order_by(CropPlanting.planting_number))).scalars().all()
    rows = await economics_for(db, org_id, list(plantings))
    t = s.CropEconomicsTotals(plantings=len(rows))
    for r in rows:
        t.total_investment += r.total_investment
        t.revenue_web += r.revenue_web
        t.revenue_direct += r.revenue_direct
        t.total_revenue += r.total_revenue
        t.profit += r.profit
        if r.is_closed:
            t.closed_plantings += 1
            t.closed_profit += r.profit
    return s.CropEconomicsReport(plantings=rows, totals=t)


async def planting_economics(db: AsyncSession, org_id: uuid.UUID, planting_id: uuid.UUID) -> s.PlantingEconomics:
    planting = await _get_planting(db, org_id, planting_id)
    return (await economics_for(db, org_id, [planting]))[0]


async def planting_breakdown(db: AsyncSession, org_id: uuid.UUID, planting_id: uuid.UUID) -> s.PlantingBreakdown:
    planting = await _get_planting(db, org_id, planting_id)
    summary = (await economics_for(db, org_id, [planting]))[0]
    web = (await db.execute(
        select(Order.id, Order.created_at, Order.status, OrderItem.quantity, OrderItem.price)
        .join(OrderItem, OrderItem.order_id == Order.id).where(
            Order.organization_id == org_id, OrderItem.crop_planting_id == planting.id, Order.status.in_(REVENUE_ORDER_STATUSES))
        .order_by(Order.created_at.desc()))).all()
    return s.PlantingBreakdown(
        summary=summary, costs=await list_costs(db, org_id, planting.id), direct_sales=await list_sales(db, org_id, planting.id),
        web_sales=[s.WebSaleLine(order_id=oid, date=created.date(), quantity=Decimal(q), unit_price=Decimal(pr),
                                 amount=money(Decimal(q) * Decimal(pr)), status=st) for oid, created, st, q, pr in web])


# --------------------------------------------------------------------------- spreadsheet import (idempotent)

_ALIASES = {
    "planting_number": ("planting_number", "planting", "plot", "planting_no", "plot_number", "plot_no", "field"),
    "date": ("date", "sale_date", "cost_date", "sold_on", "day"),
    "quantity": ("quantity", "qty", "quantity_sold", "units"),
    "unit": ("unit", "uom"),
    "unit_price": ("unit_price", "price", "price_per_unit", "rate"),
    "amount": ("amount", "total", "total_amount", "cost", "value"),
    "buyer": ("buyer", "buyer_name", "customer", "sold_to"),
    "notes": ("notes", "note", "remarks", "description", "item", "details"),
    "category": ("category", "cost_type", "type"),
}
_CATEGORY_WORDS = {
    "labor": "labour", "wages": "labour", "fertiliser": "fertilizer", "manure": "fertilizer", "pesticide": "chemicals",
    "pesticides": "chemicals", "herbicide": "chemicals", "fungicide": "chemicals", "agrochemicals": "chemicals",
    "seeds": "seed", "seedlings": "seed", "other": "other_expense", "diesel": "fuel", "petrol": "fuel", "rent": "lease",
    "irrigation": "utilities", "water": "utilities", "electricity": "utilities", "repairs": "maintenance", "machinery": "equipment",
}


def _norm_header(h) -> str:
    return str(h or "").strip().lower().replace(" ", "_").replace("-", "_").replace(".", "")


def _read_rows(content: bytes, filename: str) -> list[dict]:
    """First sheet of an .xlsx, or a CSV. -> list of {canonical_field: raw_value} with the sheet row number."""
    raw_rows: list[list] = []
    if filename.lower().endswith((".xlsx", ".xlsm")):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
        raw_rows = [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
    else:
        raw_rows = [list(r) for r in csv.reader(io.StringIO(content.decode("utf-8-sig")))]
    if not raw_rows:
        return []
    header = [_norm_header(h) for h in raw_rows[0]]
    canon: dict[int, str] = {}
    for i, h in enumerate(header):
        for field, names in _ALIASES.items():
            if h in names and field not in canon.values():
                canon[i] = field
                break
    out = []
    for n, r in enumerate(raw_rows[1:], start=2):
        if not any(c not in (None, "") for c in r):
            continue
        out.append({"_row": n, **{canon[i]: (r[i] if i < len(r) else None) for i in canon}})
    return out


def _num(v, field: str) -> Decimal:
    if isinstance(v, (int, float, Decimal)):
        return Decimal(str(v))
    try:
        return Decimal(str(v).replace(",", "").replace("KES", "").replace("Ksh", "").strip())
    except InvalidOperation:
        raise ValueError(f"{field} '{v}' is not a number")


def _date(v) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    t = str(v or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"date '{t}' is not a date (use YYYY-MM-DD or DD/MM/YYYY)")


def _key(kind: str, *parts, occurrence: int) -> str:
    return hashlib.sha1(("|".join([kind, *map(str, parts), str(occurrence)])).encode()).hexdigest()


async def import_rows(db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID, *, kind: str, content: bytes, filename: str,
                      dry_run: bool, post_to_finance: bool) -> s.CropImportResult:
    """All-or-nothing on errors (a half-applied money import is hard to reason about) and idempotent: every row
    has a deterministic key, so importing the same sheet again adds nothing - it just reports 'already imported'."""
    assert kind in ("sales", "costs")
    result = s.CropImportResult(ok=True, dry_run=dry_run, kind=kind)
    try:
        rows = _read_rows(content, filename)
    except Exception as exc:  # noqa: BLE001 - any unreadable file is the user's to fix, not a 500
        result.ok = False
        result.errors.append({"row": 0, "error": f"Could not read the file: {exc}"})
        return result
    result.rows = len(rows)
    plantings = {p.planting_number.lower(): p for p in (await db.execute(
        select(CropPlanting).where(CropPlanting.organization_id == org_id))).scalars()}

    parsed: list[dict] = []
    seen: Counter = Counter()
    for r in rows:
        n = r["_row"]
        try:
            num = str(r.get("planting_number") or "").strip()
            planting = plantings.get(num.lower())
            if not planting:
                raise ValueError(f"planting '{num}' not found (use the planting number as shown in Crops)")
            when = _date(r.get("date"))
            if kind == "sales":
                qty = _num(r.get("quantity"), "quantity")
                if qty <= 0:
                    raise ValueError("quantity must be more than 0")
                price = _num(r["unit_price"], "unit price") if r.get("unit_price") not in (None, "") else None
                amount = _num(r["amount"], "amount") if r.get("amount") not in (None, "") else None
                if price is None and amount is None:
                    raise ValueError("give the unit price or the total amount")
                if (price is not None and price < 0) or (amount is not None and amount < 0):
                    raise ValueError("price/amount cannot be negative")
                unit = await _resolve_unit(db, planting, (str(r["unit"]).strip() or None) if r.get("unit") else None)
                price, amount = _amounts(qty, price, amount)
                buyer = (str(r.get("buyer") or "").strip() or None)
                notes = (str(r.get("notes") or "").strip() or None)
                ident = (planting.planting_number.lower(), when, qty, unit, amount, buyer or "")
                parsed.append({"row": n, "planting": planting, "date": when, "qty": qty, "unit": unit, "price": price,
                               "amount": amount, "buyer": buyer, "notes": notes, "ident": ident})
            else:
                cat = str(r.get("category") or "").strip().lower().replace(" ", "_")
                cat = _CATEGORY_WORDS.get(cat, cat)
                if cat not in INPUT_COST_CATEGORIES + LABOUR_COST_CATEGORIES + (
                        "fuel", "transport", "equipment", "maintenance", "lease", "insurance", "utilities", "other_expense"):
                    raise ValueError(f"category '{cat or r.get('category') or ''}' is not one of seed, fertilizer, chemicals, "
                                     f"labour, fuel, transport, equipment, maintenance, lease, insurance, utilities, other_expense")
                amount = _num(r.get("amount"), "amount")
                if amount <= 0:
                    raise ValueError("amount must be more than 0")
                desc = (str(r.get("notes") or "").strip() or None)
                ident = (planting.planting_number.lower(), when, cat, money(amount), desc or "")
                parsed.append({"row": n, "planting": planting, "date": when, "category": cat, "amount": money(amount),
                               "description": desc, "ident": ident})
        except HTTPException as exc:
            result.errors.append({"row": n, "error": str(exc.detail)})
        except ValueError as exc:
            result.errors.append({"row": n, "error": str(exc)})
    for p in parsed:                                                # identical rows in one file are legitimate: number them
        seen[p["ident"]] += 1
        p["key"] = _key(kind, *p["ident"], occurrence=seen[p["ident"]])
    if result.errors:
        result.ok = False
        return result

    model = CropSale if kind == "sales" else CropCost
    existing = set((await db.execute(select(model.import_key).where(
        model.organization_id == org_id, model.import_key.in_([p["key"] for p in parsed])))).scalars().all()) if parsed else set()
    fresh = [p for p in parsed if p["key"] not in existing]
    result.already_imported = len(parsed) - len(fresh)

    if kind == "sales":                                             # warn (never block) if a sale exceeds recorded harvests
        avail: dict[uuid.UUID, Decimal] = {}
        warned: set[uuid.UUID] = set()
        for p in fresh:
            pid = p["planting"].id
            if pid not in avail:
                avail[pid] = (await _stock_numbers(db, org_id, pid))["available"]
            avail[pid] -= p["qty"]
            if avail[pid] < 0 and pid not in warned:
                warned.add(pid)
                result.warnings.append({"row": p["row"], "warning": _stock_warning(p["planting"], p["unit"], avail[pid])})

    if dry_run:
        result.created = len(fresh)
        result.posted_to_finance = sum(1 for p in fresh if post_to_finance and (p.get("amount") or 0) > 0) if post_to_finance else 0
        return result

    sale_done: set[uuid.UUID] = set()
    cost_done: set[uuid.UUID] = set()
    for p in fresh:
        try:
            async with db.begin_nested():
                if kind == "sales":
                    row = CropSale(organization_id=org_id, planting_id=p["planting"].id, sale_date=p["date"], quantity=p["qty"],
                                   unit=p["unit"], unit_price=p["price"], amount=p["amount"], buyer_name=p["buyer"],
                                   notes=p["notes"], source="import", import_key=p["key"], created_by=user_id)
                else:
                    row = CropCost(organization_id=org_id, planting_id=p["planting"].id, cost_date=p["date"],
                                   category=p["category"], amount=p["amount"], description=p["description"], source="import",
                                   import_key=p["key"], created_by=user_id)
                db.add(row)
                await db.flush()
        except IntegrityError:                                      # another request imported the same row first
            result.already_imported += 1
            continue
        result.created += 1
        if post_to_finance:
            if kind == "sales":
                out = await post_sale(db, org_id, user_id, row, p["planting"], sale_done)
                result.posted_to_finance += out in ("income_posted", "charged_to_customer_account")
            else:
                result.posted_to_finance += await post_cost(db, org_id, user_id, row, p["planting"], cost_done) == "posted"
    await db.commit()
    return result


# --------------------------------------------------------------------------- catch-up for the finance ledger

async def _manual_totals(db: AsyncSession, org_id: uuid.UUID, kind: str) -> dict:
    """Crops entries somebody typed straight into Finance (no link to a planting): the ones that could overlap
    with what we are about to post. The Finance screen stores these with reference_type 'manual'."""
    q = select(func.count(FinanceTransaction.id), func.coalesce(func.sum(FinanceTransaction.amount), 0),
               func.min(FinanceTransaction.transaction_date), func.max(FinanceTransaction.transaction_date)).where(
        FinanceTransaction.organization_id == org_id, FinanceTransaction.transaction_type == kind,
        or_(FinanceTransaction.reference_type.is_(None), FinanceTransaction.reference_type == "manual"))
    q = q.where(FinanceTransaction.category == "crop_sale") if kind == "income" else q.where(FinanceTransaction.activity == ACTIVITY)
    row = (await db.execute(q)).one()
    return {"count": int(row[0]), "total": float(row[1]),
            "first": row[2].isoformat() if row[2] else None, "last": row[3].isoformat() if row[3] else None}


async def reconcile(db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID, *, dry_run: bool = True,
                    confirm_overlap: bool = False) -> dict:
    """Books crop sales, costs and planting purchase costs that exist but never reached Finance. Previews by default,
    posts only what is missing (so it is safe to repeat), and refuses to apply over hand-typed crops entries in
    Finance unless the caller confirms they are different - the one thing the system cannot decide on its own."""
    plantings = {p.id: p for p in (await db.execute(select(CropPlanting).where(CropPlanting.organization_id == org_id))).scalars()}
    sales = list((await db.execute(select(CropSale).where(CropSale.organization_id == org_id, CropSale.voided_at.is_(None))
                                   .order_by(CropSale.sale_date))).scalars())
    costs = list((await db.execute(select(CropCost).where(CropCost.organization_id == org_id, CropCost.voided_at.is_(None))
                                   .order_by(CropCost.cost_date))).scalars())
    sale_done = await _ledger_refs(db, org_id, SALE_REF, [x.id for x in sales])
    cost_done = await _ledger_refs(db, org_id, COST_REF, [x.id for x in costs])
    buy_done = await _ledger_refs(db, org_id, PLANTING_REF, list(plantings))

    todo_sales = [x for x in sales if x.id not in sale_done and Decimal(x.amount) > 0]
    todo_costs = [x for x in costs if x.id not in cost_done]
    todo_buys = [p for p in plantings.values() if p.id not in buy_done and Decimal(p.acquisition_cost or 0) > 0]

    def block(todo, done_ids, rows, amt):
        return {"missing": len(todo), "missing_amount": float(sum((Decimal(amt(x)) for x in todo), ZERO)), "posted": 0,
                "already_recorded": sum(1 for x in rows if x.id in done_ids)}

    result = {
        "dry_run": dry_run,
        "sales": {**block(todo_sales, sale_done, sales, lambda x: x.amount), "no_price": sum(1 for x in sales if Decimal(x.amount) <= 0)},
        "costs": block(todo_costs, cost_done, costs, lambda x: x.amount),
        "plantings": block(todo_buys, buy_done, list(plantings.values()), lambda x: x.acquisition_cost or 0),
        "overlap": {"manual_sales": await _manual_totals(db, org_id, "income"), "manual_costs": await _manual_totals(db, org_id, "expense")},
    }
    sales_overlap = bool(todo_sales) and result["overlap"]["manual_sales"]["count"] > 0
    costs_overlap = bool(todo_costs or todo_buys) and result["overlap"]["manual_costs"]["count"] > 0
    result["needs_confirmation"] = sales_overlap or costs_overlap
    result["sample"] = (
        [{"kind": "sale", "ref": plantings[x.planting_id].planting_number, "date": x.sale_date.isoformat(), "amount": float(x.amount)} for x in todo_sales[:10]]
        + [{"kind": "cost", "ref": plantings[x.planting_id].planting_number, "date": x.cost_date.isoformat(), "amount": float(x.amount)} for x in todo_costs[:10]]
        + [{"kind": "planting cost", "ref": p.planting_number, "date": p.planting_date.isoformat(), "amount": float(p.acquisition_cost)} for p in todo_buys[:10]])
    if dry_run:
        return result

    if result["needs_confirmation"] and not confirm_overlap:
        parts = []
        if sales_overlap:
            m = result["overlap"]["manual_sales"]
            parts.append(f"{m['count']} manually entered crop sale(s) totalling KES {m['total']:,.0f}")
        if costs_overlap:
            m = result["overlap"]["manual_costs"]
            parts.append(f"{m['count']} manually entered crops expense(s) totalling KES {m['total']:,.0f}")
        raise HTTPException(status.HTTP_409_CONFLICT, (
            "Finance already holds " + " and ".join(parts) + ". If they record the same sales or costs, posting these too would "
            "count them twice, and Finance entries cannot be deleted. Review them in Finance first. If they are different, "
            "repeat the request with confirm_overlap=true."))

    for x in todo_sales:
        out = await post_sale(db, org_id, user_id, x, plantings[x.planting_id], sale_done)
        result["sales"]["posted"] += out in ("income_posted", "charged_to_customer_account")
    for x in todo_costs:
        result["costs"]["posted"] += await post_cost(db, org_id, user_id, x, plantings[x.planting_id], cost_done) == "posted"
    for p in todo_buys:
        result["plantings"]["posted"] += await post_planting_purchase(db, org_id, user_id, p, buy_done) == "posted"
    await db.commit()
    result["dry_run"] = False
    return result
