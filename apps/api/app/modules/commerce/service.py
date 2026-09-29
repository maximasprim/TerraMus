import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import publish
from app.modules.livestock.models import Animal
from app.modules.livestock.service import get_animal
from app.modules.livestock import schemas as livestock_schemas
from app.modules.livestock.service import change_status as change_animal_status
from app.modules.crops.models import CropPlanting, HarvestRecord
from app.modules.crops.service import get_planting as get_crop_planting
from app.modules.customers.service import get_customer
from app.modules.commerce.models import Listing, Reservation, Order, OrderItem, OrderStatusEvent
from app.modules.commerce import schemas

# Spec §19 order lifecycle - explicit allowed-transition table, same pattern as
# the animal status machine in livestock/service.py.
_ORDER_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"payment_pending", "cancelled"},
    "payment_pending": {"paid", "cancelled", "failed"},
    "paid": {"processing", "refunded", "partially_refunded"},
    "processing": {"ready_for_fulfillment", "refunded"},
    "ready_for_fulfillment": {"dispatched"},
    "dispatched": {"delivered"},
    "delivered": {"completed", "partially_refunded"},
    "completed": set(),
    "cancelled": set(),
    "refunded": set(),
    "partially_refunded": set(),
    "failed": set(),
}


def _generate_listing_slug(animal) -> str:
    """Spec §45 - SEO-friendly URL: /livestock/dairy-cattle/holstein-cow-001.
    Includes a short id suffix to guarantee uniqueness even if two animals
    share species+breed+number-like names (unlikely given animal_number's own
    per-org uniqueness, but slugs additionally strip characters that could
    collide after normalization)."""
    import re
    parts = [animal.species]
    if animal.breed:
        parts.append(animal.breed)
    parts.append(animal.animal_number)
    raw = "-".join(parts).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    return f"{slug}-{uuid.uuid4().hex[:6]}"


def _generate_crop_listing_slug(planting: CropPlanting) -> str:
    """Same shape as _generate_listing_slug above, for crop produce -
    e.g. /crop-produce/tea/purple-napier-pl-0042-a1b2c3 (crop_type first,
    like species does for animals, so /crop-produce/tea can browse every
    tea listing the same way /livestock/cattle already can for animals)."""
    import re
    parts = [planting.crop_type]
    if planting.variety:
        parts.append(planting.variety)
    parts.append(planting.planting_number)
    raw = "-".join(parts).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    return f"{slug}-{uuid.uuid4().hex[:6]}"


async def _lock_animal_for_update(db: AsyncSession, org_id: uuid.UUID, animal_id: uuid.UUID) -> Animal:
    """Row-level lock (spec §18/§30/§52.2 - 'use database transactions and
    appropriate locking' to prevent two customers buying the same animal).
    Must be called inside the request's transaction, before the status check."""
    result = await db.execute(
        select(Animal)
        .where(Animal.id == animal_id, Animal.organization_id == org_id)
        .with_for_update()
    )
    animal = result.scalar_one_or_none()
    if not animal:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Animal {animal_id} not found")
    return animal


async def _lock_crop_planting_for_update(db: AsyncSession, org_id: uuid.UUID, planting_id: uuid.UUID) -> CropPlanting:
    """Crop produce has no single row that represents 'is this taken yet'
    the way an animal's own status does - availability is a computed
    aggregate (harvested so far minus already-ordered). Locking the
    CropPlanting row itself serializes concurrent orders against the same
    planting, which is exactly what's needed here: only one transaction at a
    time gets to read-then-write the aggregate for a given planting."""
    result = await db.execute(
        select(CropPlanting)
        .where(CropPlanting.id == planting_id, CropPlanting.organization_id == org_id)
        .with_for_update()
    )
    planting = result.scalar_one_or_none()
    if not planting:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Crop planting {planting_id} not found")
    return planting


async def get_available_crop_quantity(db: AsyncSession, org_id: uuid.UUID, planting_id: uuid.UUID) -> Decimal:
    """Available stock = everything harvested so far, minus everything
    already committed to a non-cancelled/non-failed/non-refunded order. This
    is a ledger, not a stored counter - matching the append-only philosophy
    used everywhere else in this codebase (harvest_records, order_status_events):
    the truth is always derivable from history, nothing is silently
    decremented in place."""
    harvested_result = await db.execute(
        select(func.coalesce(func.sum(HarvestRecord.quantity), 0)).where(HarvestRecord.planting_id == planting_id)
    )
    harvested = Decimal(harvested_result.scalar_one())

    committed_result = await db.execute(
        select(func.coalesce(func.sum(OrderItem.quantity), 0))
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            OrderItem.crop_planting_id == planting_id,
            Order.organization_id == org_id,
            Order.status.notin_(("cancelled", "failed", "refunded")),
        )
    )
    committed = Decimal(committed_result.scalar_one())
    return harvested - committed


async def list_low_stock_crop_listings(db: AsyncSession, org_id: uuid.UUID) -> list[dict]:
    """Crop-produce listings with a low_stock_threshold set, whose current
    available quantity has fallen at or below it. Mirrors inventory's
    reorder_level concept, but since crop stock is a computed ledger rather
    than a stored counter (see get_available_crop_quantity's docstring),
    this recomputes availability per candidate listing rather than a simple
    indexed WHERE clause."""
    result = await db.execute(
        select(Listing, CropPlanting).join(CropPlanting, CropPlanting.id == Listing.crop_planting_id).where(
            Listing.organization_id == org_id,
            Listing.is_active.is_(True),
            Listing.low_stock_threshold.isnot(None),
        )
    )
    low_stock = []
    for listing, planting in result.all():
        available = await get_available_crop_quantity(db, org_id, planting.id)
        if available <= listing.low_stock_threshold:
            low_stock.append({
                "listing_id": listing.id, "listing_title": listing.title, "slug": listing.slug,
                "planting_id": planting.id, "planting_number": planting.planting_number,
                "crop_type": planting.crop_type, "available": available,
                "threshold": listing.low_stock_threshold, "unit": listing.unit,
            })
    return low_stock


# ---------------------------------------------------------------- Listings --

async def create_listing(db: AsyncSession, org_id: uuid.UUID, req: schemas.ListingCreate) -> Listing:
    if req.animal_id is not None:
        animal = await get_animal(db, req.animal_id, org_id)
        if animal.status != "for_sale":
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Animal must be 'for_sale' to list (currently '{animal.status}')",
            )

        existing = await db.execute(
            select(Listing).where(Listing.animal_id == req.animal_id, Listing.is_active.is_(True))
        )
        if existing.scalar_one_or_none():
            # Application-level check for a clean error message; the DB partial
            # unique index (migration 0006) is the actual source of truth and
            # closes the race window between this check and the insert below.
            raise HTTPException(status.HTTP_409_CONFLICT, "This animal already has an active listing")

        listing = Listing(organization_id=org_id, slug=_generate_listing_slug(animal), **req.model_dump())

    else:
        assert req.crop_planting_id is not None  # guaranteed by ListingCreate's XOR validator
        if not req.unit:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "A crop-produce listing requires a unit (kg, bags, crates…)")
        planting = await get_crop_planting(db, req.crop_planting_id, org_id)
        available = await get_available_crop_quantity(db, org_id, req.crop_planting_id)
        if available <= 0:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "This planting has no harvested stock available to list yet - record a harvest first",
            )

        existing = await db.execute(
            select(Listing).where(Listing.crop_planting_id == req.crop_planting_id, Listing.is_active.is_(True))
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status.HTTP_409_CONFLICT, "This planting already has an active listing")

        listing = Listing(organization_id=org_id, slug=_generate_crop_listing_slug(planting), **req.model_dump())

    db.add(listing)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "This item already has an active listing")
    await db.refresh(listing)
    return listing


async def list_listings(db: AsyncSession, org_id: uuid.UUID, filters: schemas.ListingFilter) -> list[Listing]:
    query = select(Listing).where(Listing.organization_id == org_id, Listing.is_active.is_(True))
    if filters.min_price is not None:
        query = query.where(Listing.price >= filters.min_price)
    if filters.max_price is not None:
        query = query.where(Listing.price <= filters.max_price)
    if filters.featured_only:
        query = query.where(Listing.featured.is_(True))
    if filters.species:
        query = query.join(Animal, Animal.id == Listing.animal_id).where(Animal.species == filters.species)
    if filters.crop_type:
        query = query.join(CropPlanting, CropPlanting.id == Listing.crop_planting_id).where(
            CropPlanting.crop_type == filters.crop_type
        )
    result = await db.execute(query.order_by(Listing.featured.desc(), Listing.created_at.desc()))
    return list(result.scalars().all())


async def get_listing(db: AsyncSession, org_id: uuid.UUID, listing_id: uuid.UUID) -> Listing:
    result = await db.execute(select(Listing).where(Listing.id == listing_id, Listing.organization_id == org_id))
    listing = result.scalar_one_or_none()
    if not listing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Listing not found")
    return listing


async def deactivate_listing(db: AsyncSession, org_id: uuid.UUID, listing_id: uuid.UUID) -> Listing:
    listing = await get_listing(db, org_id, listing_id)
    listing.is_active = False
    await db.commit()
    await db.refresh(listing)
    return listing


async def update_listing(db: AsyncSession, org_id: uuid.UUID, listing_id: uuid.UUID, req: schemas.ListingUpdate) -> Listing:
    """Was a real gap since Phase 4/7 - the only way to change a listing's
    price or description was deactivate + recreate, losing the original
    slug (spec §45 SEO URLs) and featured flag in the process."""
    listing = await get_listing(db, org_id, listing_id)
    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(listing, field, value)
    await db.commit()
    await db.refresh(listing)
    return listing


async def _deactivate_active_listing_for_animal(db: AsyncSession, org_id: uuid.UUID, animal_id: uuid.UUID) -> None:
    """Spec §17 - a listing must reflect real availability. Called whenever an
    animal leaves 'for_sale' via reservation or order, so the public catalog
    (modules/public) never shows a stale 'for sale' listing for an animal
    that's actually reserved or sold. Deliberately does NOT auto-reactivate on
    cancellation - staff re-list explicitly, since the old title/price/photos
    may no longer be accurate by then."""
    result = await db.execute(
        select(Listing).where(
            Listing.organization_id == org_id, Listing.animal_id == animal_id, Listing.is_active.is_(True),
        )
    )
    listing = result.scalar_one_or_none()
    if listing:
        listing.is_active = False


# ------------------------------------------------------------ Reservations --

async def create_reservation(
    db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID, req: schemas.ReservationCreate,
) -> Reservation:
    await get_customer(db, org_id, req.customer_id)  # tenant + existence check

    # Lock the animal row FIRST, then check status - closes the race window
    # where two concurrent requests both read 'for_sale' before either writes.
    animal = await _lock_animal_for_update(db, org_id, req.animal_id)
    if animal.status != "for_sale":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Animal is not available to reserve (status: '{animal.status}')",
        )

    reservation = Reservation(
        organization_id=org_id, animal_id=req.animal_id, customer_id=req.customer_id,
        reservation_date=req.reservation_date, expiry_date=req.expiry_date,
        deposit_amount=req.deposit_amount, notes=req.notes, created_by=user_id, status="active",
    )
    db.add(reservation)

    await change_animal_status(
        db, animal, livestock_schemas.StatusChangeRequest(status="reserved", reason="Reservation created"), user_id,
    )
    await _deactivate_active_listing_for_animal(db, org_id, req.animal_id)
    await db.commit()
    await db.refresh(reservation)
    return reservation


async def get_reservation(db: AsyncSession, org_id: uuid.UUID, reservation_id: uuid.UUID) -> Reservation:
    result = await db.execute(
        select(Reservation).where(Reservation.id == reservation_id, Reservation.organization_id == org_id)
    )
    reservation = result.scalar_one_or_none()
    if not reservation:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Reservation not found")
    return reservation


async def list_reservations(db: AsyncSession, org_id: uuid.UUID, status_filter: str | None = None) -> list[Reservation]:
    """No list endpoint existed before - create/get-one/cancel/expire-stale
    all did, but nothing let staff see reservations as a set. Added
    alongside the admin UI that needs it."""
    query = select(Reservation).where(Reservation.organization_id == org_id)
    if status_filter:
        query = query.where(Reservation.status == status_filter)
    result = await db.execute(query.order_by(Reservation.created_at.desc()))
    return list(result.scalars().all())


async def cancel_reservation(
    db: AsyncSession, org_id: uuid.UUID, reservation_id: uuid.UUID, user_id: uuid.UUID,
) -> Reservation:
    reservation = await get_reservation(db, org_id, reservation_id)
    if reservation.status != "active":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Reservation is already '{reservation.status}'")

    animal = await _lock_animal_for_update(db, org_id, reservation.animal_id)
    reservation.status = "cancelled"
    if animal.status == "reserved":  # only release if nothing else changed it (e.g. already sold via order)
        await change_animal_status(
            db, animal, livestock_schemas.StatusChangeRequest(status="for_sale", reason="Reservation cancelled"),
            user_id,
        )
    await db.commit()
    await db.refresh(reservation)
    return reservation


async def expire_stale_reservations(db: AsyncSession, org_id: uuid.UUID) -> list[uuid.UUID]:
    """Spec §18 - 'If reservation expires, automatically release the animal.'
    In the absence of a scheduler (Phase 6 Notifications territory), this is
    invoked lazily; a real deployment would call it from a periodic job."""
    today = date.today()
    result = await db.execute(
        select(Reservation).where(
            Reservation.organization_id == org_id,
            Reservation.status == "active",
            Reservation.expiry_date < today,
        )
    )
    expired_ids: list[uuid.UUID] = []
    for reservation in result.scalars().all():
        animal = await _lock_animal_for_update(db, org_id, reservation.animal_id)
        reservation.status = "expired"
        if animal.status == "reserved":
            await change_animal_status(
                db, animal,
                livestock_schemas.StatusChangeRequest(status="for_sale", reason="Reservation expired"),
                None,
            )
        expired_ids.append(reservation.id)
        await publish("ReservationExpired", {"organization_id": str(org_id), "reservation_id": str(reservation.id)})
    await db.commit()
    return expired_ids


# ------------------------------------------------------------------ Orders --

async def create_order(db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID, req: schemas.OrderCreate) -> Order:
    await get_customer(db, org_id, req.customer_id)

    animal_items = [item for item in req.items if item.animal_id is not None]
    crop_items = [item for item in req.items if item.crop_planting_id is not None]

    animal_ids = [item.animal_id for item in animal_items]
    if len(animal_ids) != len(set(animal_ids)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Duplicate animal in the same order")
    crop_planting_ids = [item.crop_planting_id for item in crop_items]
    if len(crop_planting_ids) != len(set(crop_planting_ids)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Duplicate crop planting in the same order - combine into one line with a larger quantity instead")

    locked_animals: dict[uuid.UUID, Animal] = {}
    # Lock in a stable order (sorted by id) to avoid deadlocks between two
    # concurrent multi-item orders that share animals in different sequences.
    for animal_id in sorted(animal_ids, key=str):
        animal = await _lock_animal_for_update(db, org_id, animal_id)
        if animal.status == "for_sale":
            pass  # available - will be reserved below
        elif animal.status == "reserved":
            active_res = await db.execute(
                select(Reservation).where(
                    Reservation.animal_id == animal_id, Reservation.status == "active",
                )
            )
            res = active_res.scalar_one_or_none()
            if not res or res.customer_id != req.customer_id:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    f"Animal {animal_id} is reserved by a different customer",
                )
        else:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Animal {animal_id} is not available for order (status: '{animal.status}')",
            )
        locked_animals[animal_id] = animal

    # Crop produce has no exclusive "reserved" state to check - just enough
    # available stock, checked against the lock acquired below so two
    # concurrent orders against the same planting can't both succeed on
    # quantities that only fit once.
    for item in crop_items:
        planting = await _lock_crop_planting_for_update(db, org_id, item.crop_planting_id)
        available = await get_available_crop_quantity(db, org_id, item.crop_planting_id)
        if item.quantity > available:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Only {available} available for planting {planting.planting_number} ({planting.crop_type}), requested {item.quantity}",
            )

    total = sum((item.price * item.quantity for item in req.items), Decimal("0"))
    order = Order(
        organization_id=org_id, customer_id=req.customer_id, status="pending",
        delivery_option=req.delivery_option, delivery_address=req.delivery_address,
        notes=req.notes, total_amount=total, created_by=user_id,
    )
    db.add(order)
    await db.flush()

    for item in req.items:
        db.add(OrderItem(
            order_id=order.id, animal_id=item.animal_id, crop_planting_id=item.crop_planting_id,
            quantity=item.quantity, price=item.price,
        ))

    db.add(OrderStatusEvent(order_id=order.id, from_status=None, to_status="pending", changed_by=user_id))

    for animal_id, animal in locked_animals.items():
        if animal.status == "for_sale":
            await change_animal_status(
                db, animal,
                livestock_schemas.StatusChangeRequest(status="reserved", reason=f"Order {order.id}"),
                user_id,
            )
            await _deactivate_active_listing_for_animal(db, org_id, animal_id)

    # Crop listings are deliberately NOT deactivated here, unlike an animal's
    # listing above - a planting keeps selling against its remaining stock
    # (get_available_crop_quantity already accounts for this order's items
    # the moment they're committed), so the listing should stay active for
    # the next buyer until stock actually runs out or staff deactivate it.

    await db.commit()
    await db.refresh(order)
    await publish("OrderCreated", {
        "organization_id": str(org_id), "order_id": str(order.id), "customer_id": str(req.customer_id),
    })
    return order


async def get_order(db: AsyncSession, org_id: uuid.UUID, order_id: uuid.UUID) -> Order:
    result = await db.execute(select(Order).where(Order.id == order_id, Order.organization_id == org_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    return order


async def list_orders(db: AsyncSession, org_id: uuid.UUID, customer_id: uuid.UUID | None = None) -> list[Order]:
    query = select(Order).where(Order.organization_id == org_id)
    if customer_id:
        query = query.where(Order.customer_id == customer_id)
    result = await db.execute(query.order_by(Order.created_at.desc()))
    return list(result.scalars().all())


async def change_order_status(
    db: AsyncSession, org_id: uuid.UUID, order_id: uuid.UUID, user_id: uuid.UUID, req: schemas.OrderStatusChange,
) -> Order:
    order = await get_order(db, org_id, order_id)
    allowed = _ORDER_TRANSITIONS.get(order.status, set())
    if req.status == order.status:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Order is already in that status")
    if req.status not in allowed:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot transition order from '{order.status}' to '{req.status}'",
        )

    previous_status = order.status
    order.status = req.status
    db.add(OrderStatusEvent(
        order_id=order.id, from_status=previous_status, to_status=req.status,
        reason=req.reason, changed_by=user_id,
    ))

    # Spec §52: "Animal sale must create a financial transaction" (Ph5 territory -
    # here we finalize the animal side: reserved -> sold on payment confirmation).
    # Crop-produce items have nothing analogous to finalize here - stock was
    # already committed the moment the order was created (see
    # get_available_crop_quantity), and a crop planting's own lifecycle is
    # managed independently in crops/service.py, not driven by order status.
    if req.status == "paid":
        for item in order.items:
            if item.animal_id is None:
                continue
            animal = await _lock_animal_for_update(db, org_id, item.animal_id)
            if animal.status == "reserved":
                await change_animal_status(
                    db, animal,
                    livestock_schemas.StatusChangeRequest(status="sold", reason=f"Order {order.id} paid"),
                    user_id,
                )
                # Close out any reservation tied to this animal.
                res_result = await db.execute(
                    select(Reservation).where(Reservation.animal_id == item.animal_id, Reservation.status == "active")
                )
                res = res_result.scalar_one_or_none()
                if res:
                    res.status = "completed"

    elif req.status == "cancelled" and previous_status in ("pending", "payment_pending"):
        for item in order.items:
            if item.animal_id is None:
                continue  # crop-produce item - cancelling frees the stock automatically (see get_available_crop_quantity)
            animal = await _lock_animal_for_update(db, org_id, item.animal_id)
            if animal.status == "reserved":
                await change_animal_status(
                    db, animal,
                    livestock_schemas.StatusChangeRequest(status="for_sale", reason=f"Order {order.id} cancelled"),
                    user_id,
                )

    await db.commit()
    await db.refresh(order)

    if req.status == "paid":
        await publish("OrderPaid", {"organization_id": str(org_id), "order_id": str(order.id)})
    elif req.status == "cancelled":
        await publish("OrderCancelled", {"organization_id": str(org_id), "order_id": str(order.id)})
    elif req.status == "completed":
        await publish("OrderCompleted", {"organization_id": str(org_id), "order_id": str(order.id)})

    return order
