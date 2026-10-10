import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import publish
from app.modules.inventory.models import InventoryItem, StockMovement, IN_TYPES, OUT_TYPES
from app.modules.inventory import schemas


async def create_item(db: AsyncSession, org_id: uuid.UUID, req: schemas.InventoryItemCreate) -> InventoryItem:
    item = InventoryItem(organization_id=org_id, **req.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def get_item(db: AsyncSession, org_id: uuid.UUID, item_id: uuid.UUID) -> InventoryItem:
    result = await db.execute(
        select(InventoryItem).where(InventoryItem.id == item_id, InventoryItem.organization_id == org_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Inventory item not found")
    return item


async def current_stock(db: AsyncSession, item_id: uuid.UUID) -> Decimal:
    result = await db.execute(
        select(func.coalesce(func.sum(StockMovement.quantity), 0)).where(StockMovement.item_id == item_id)
    )
    return Decimal(result.scalar_one())


async def _fifo_layers_remaining(
    db: AsyncSession, item_id: uuid.UUID, as_of_moved_at: datetime | None = None,
) -> list[list[Decimal]]:
    """Spec §14: 'Support inventory valuation' - walks the whole ledger for
    this item exactly once, oldest first, netting every outbound movement
    against the still-unconsumed inbound layers it actually drew down
    (first-in-first-out), and returns whatever's left. This never mutates
    or re-derives anything on old StockMovement rows - the ledger itself
    stays exactly as append-only as spec §14 already requires; FIFO layers
    are computed fresh from that immutable history every time they're
    needed, the same way current_stock() is a SUM rather than a stored
    counter.

    `adjustment` movements are treated as a same-direction layer/consumption
    by their sign (positive = an inbound layer at the given unit_cost if
    one was supplied, negative = draws down existing layers like any other
    outbound movement) - spec's own framing of adjustment as "the caller
    supplies the signed delta directly" doesn't specify a costing model
    beyond that, so this is the most consistent reading available.
    """
    query = select(StockMovement).where(StockMovement.item_id == item_id).order_by(
        StockMovement.moved_at, StockMovement.created_at,
    )
    if as_of_moved_at is not None:
        query = query.where(StockMovement.moved_at <= as_of_moved_at)
    result = await db.execute(query)

    layers: list[list[Decimal]] = []  # each: [remaining_qty, unit_cost]
    for m in result.scalars():
        qty = Decimal(str(m.quantity))
        if qty > 0:
            if m.unit_cost is not None:
                layers.append([qty, Decimal(str(m.unit_cost))])
            # a priced-less inbound movement (unit_cost never supplied, e.g.
            # an old opening_balance) adds no layer - there's no cost basis
            # to draw from, so it's correctly invisible to valuation rather
            # than silently costed at 0.
        elif qty < 0:
            to_consume = -qty
            for layer in layers:
                if to_consume <= 0:
                    break
                take = min(layer[0], to_consume)
                layer[0] -= take
                to_consume -= take
            # If to_consume remains > 0 (more was taken out than has a
            # known cost basis - e.g. stock existed before any priced
            # purchase was ever recorded), it's simply not chargeable
            # against anything; excess is dropped rather than going negative.
    return [layer for layer in layers if layer[0] > 0]


async def fifo_unit_cost_for_consumption(
    db: AsyncSession, item_id: uuid.UUID, quantity: Decimal, as_of_moved_at: datetime,
) -> Decimal | None:
    """The blended (weighted-average across whichever layers get drawn down)
    unit cost of consuming `quantity` units right now, oldest-purchased
    stock first. Returns None when there's no priced layer to draw from at
    all - the caller then leaves unit_cost unset, exactly as it already did
    before this session, rather than inventing a number."""
    layers = await _fifo_layers_remaining(db, item_id, as_of_moved_at)
    if not layers:
        return None

    remaining = Decimal(str(quantity))
    total_cost = Decimal("0")
    total_taken = Decimal("0")
    for qty, cost in layers:
        if remaining <= 0:
            break
        take = min(qty, remaining)
        total_cost += take * cost
        total_taken += take
        remaining -= take

    if total_taken == 0:
        return None
    # Quantized to 2dp, not more: this return value gets stored directly
    # into StockMovement.unit_cost, a NUMERIC(12,2) column - Postgres would
    # silently round anything with more scale on insert anyway, so this
    # matches what actually gets persisted rather than reporting a false
    # precision that a re-read from the DB would never actually show.
    return (total_cost / total_taken).quantize(Decimal("0.01"))


async def item_valuation(db: AsyncSession, item_id: uuid.UUID) -> tuple[Decimal, Decimal | None]:
    """Returns (quantity_with_known_cost, total_value). Note this can be
    less than current_stock()'s quantity when some stock on hand has no
    priced layer behind it (see _fifo_layers_remaining's opening_balance
    note) - reported separately rather than silently averaged in, since a
    farm auditing "what is my feed worth" needs to know the difference
    between "worth zero" and "we don't actually know."""
    layers = await _fifo_layers_remaining(db, item_id)
    if not layers:
        return Decimal("0"), None
    quantity = sum((qty for qty, _ in layers), Decimal("0"))
    value = sum((qty * cost for qty, cost in layers), Decimal("0")).quantize(Decimal("0.01"))
    return quantity, value


async def valuation_report(db: AsyncSession, org_id: uuid.UUID) -> list[schemas.ValuationRow]:
    result = await db.execute(select(InventoryItem).where(InventoryItem.organization_id == org_id))
    items = result.scalars().all()
    rows = []
    for item in items:
        total_stock = await current_stock(db, item.id)
        priced_qty, value = await item_valuation(db, item.id)
        avg_unit_cost = (value / priced_qty).quantize(Decimal("0.0001")) if value is not None and priced_qty > 0 else None
        rows.append(schemas.ValuationRow(
            item_id=item.id, item_name=item.name, unit=item.unit,
            quantity_on_hand=Decimal(total_stock).quantize(Decimal("0.01")),
            priced_quantity=Decimal(priced_qty).quantize(Decimal("0.01")),
            avg_unit_cost=avg_unit_cost,
            total_value=Decimal(value if value is not None else 0).quantize(Decimal("0.01")),
        ))
    return rows


async def list_items(db: AsyncSession, org_id: uuid.UUID) -> list[schemas.InventoryItemOut]:
    result = await db.execute(select(InventoryItem).where(InventoryItem.organization_id == org_id))
    items = result.scalars().all()
    out = []
    for item in items:
        stock = await current_stock(db, item.id)
        out.append(schemas.InventoryItemOut(
            id=item.id, organization_id=item.organization_id, farm_id=item.farm_id,
            name=item.name, category=item.category, unit=item.unit,
            reorder_level=item.reorder_level, allow_negative_stock=item.allow_negative_stock,
            notes=item.notes, current_stock=stock,
        ))
    return out


async def record_movement(
    db: AsyncSession, org_id: uuid.UUID, item_id: uuid.UUID,
    user_id: uuid.UUID, req: schemas.StockMovementCreate,
) -> StockMovement:
    item = await get_item(db, org_id, item_id)

    if req.movement_type == "adjustment":
        signed_qty = req.quantity  # caller supplies the signed delta explicitly
    else:
        magnitude = abs(req.quantity)
        if req.movement_type in IN_TYPES:
            signed_qty = magnitude
        elif req.movement_type in OUT_TYPES:
            signed_qty = -magnitude
        else:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown movement type '{req.movement_type}'")

    if signed_qty < 0 and not item.allow_negative_stock:
        # Spec §52.11 - "Negative inventory should be prevented unless explicitly configured."
        balance = await current_stock(db, item_id)
        if balance + signed_qty < 0:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Insufficient stock for '{item.name}': balance {balance}, requested change {signed_qty}",
            )

    effective_unit_cost = req.unit_cost
    moved_at = req.moved_at or datetime.now(timezone.utc)
    if effective_unit_cost is None and req.movement_type in OUT_TYPES:
        # Spec §14 "inventory valuation" gap this session closes: previously
        # an outbound movement with no explicit unit_cost was simply priced
        # at nothing, undercounting real spend and leaving nothing for
        # valuation to sum. FIFO-priced from whatever purchase layers are
        # actually on hand as of this movement's own timestamp - an explicit
        # unit_cost from the caller (e.g. an actual invoiced cost) still
        # always wins over this estimate.
        effective_unit_cost = await fifo_unit_cost_for_consumption(db, item_id, magnitude, moved_at)

    movement = StockMovement(
        organization_id=org_id, item_id=item_id,
        movement_type=req.movement_type, quantity=signed_qty,
        unit_cost=effective_unit_cost, batch_number=req.batch_number, expiry_date=req.expiry_date,
        animal_id=req.animal_id, reference=req.reference, notes=req.notes,
        performed_by=user_id, moved_at=moved_at,
    )
    db.add(movement)
    await db.commit()
    await db.refresh(movement)

    new_balance = await current_stock(db, item_id)
    if new_balance <= item.reorder_level:
        await publish("InventoryLow", {
            "organization_id": str(org_id), "item_id": str(item_id),
            "item_name": item.name, "current_stock": str(new_balance), "reorder_level": str(item.reorder_level),
        })
    if req.expiry_date:
        await publish("InventoryExpiring", {
            "organization_id": str(org_id), "item_id": str(item_id), "expiry_date": str(req.expiry_date),
        })

    # Spec §23 - feed/medicine/etc. consumption is real farm spend and belongs
    # in the finance ledger, not just the inventory ledger. Only fires for
    # outbound movements with a known unit_cost (purchases/opening balances
    # are asset acquisitions, not expenses, until consumed) - "known" now
    # includes the FIFO-estimated cost above, not only an explicitly-supplied
    # one, closing the gap where an unpriced consumption silently generated
    # no expense at all.
    if req.movement_type in ("consumption", "wastage", "expired") and effective_unit_cost is not None:
        await publish("InventorySpend", {
            "organization_id": str(org_id), "item_id": str(item_id), "item_name": item.name,
            "item_category": item.category, "movement_type": req.movement_type,
            "cost": str(abs(signed_qty) * effective_unit_cost), "animal_id": str(req.animal_id) if req.animal_id else None,
        })

    return movement


async def list_movements(db: AsyncSession, org_id: uuid.UUID, item_id: uuid.UUID) -> list[StockMovement]:
    await get_item(db, org_id, item_id)
    result = await db.execute(
        select(StockMovement)
        .where(StockMovement.organization_id == org_id, StockMovement.item_id == item_id)
        .order_by(StockMovement.moved_at.desc())
    )
    return list(result.scalars().all())


async def low_stock_items(db: AsyncSession, org_id: uuid.UUID) -> list[schemas.LowStockItem]:
    result = await db.execute(select(InventoryItem).where(InventoryItem.organization_id == org_id))
    items = result.scalars().all()
    low: list[schemas.LowStockItem] = []
    for item in items:
        stock = await current_stock(db, item.id)
        if stock <= item.reorder_level:
            low.append(schemas.LowStockItem(
                item_id=item.id, name=item.name, category=item.category,
                unit=item.unit, current_stock=stock, reorder_level=item.reorder_level,
            ))
    return low


async def feed_cost_for_animal(db: AsyncSession, org_id: uuid.UUID, animal_id: uuid.UUID) -> Decimal:
    """Spec §13 - 'Generate feed cost per animal.' Sums cost of OUT movements
    (consumption) tagged with this animal_id; feeds into the profitability
    calculation (livestock §25) once wired together."""
    result = await db.execute(
        select(func.coalesce(func.sum(-StockMovement.quantity * StockMovement.unit_cost), 0))
        .where(
            StockMovement.organization_id == org_id,
            StockMovement.animal_id == animal_id,
            StockMovement.movement_type == "consumption",
            StockMovement.unit_cost.is_not(None),
        )
    )
    return Decimal(result.scalar_one())
