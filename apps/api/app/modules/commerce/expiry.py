"""Automatic expiry of abandoned *guest* orders.

Why this exists: a guest order reserves inventory the moment it's placed -
an animal is flipped to `reserved` and its listing deactivated; crop stock is
committed. Without expiry, anyone (or any bot) could place unpaid orders and
hold the whole catalogue hostage indefinitely. Staff-created orders
(`created_by` set) are never touched - only orders placed with no staff user.

Timing is configurable via settings (0 disables a rule):
  GUEST_ORDER_TTL_MINUTES      unpaid `pending` orders
  PAYMENT_PENDING_TTL_HOURS    `payment_pending` orders whose payment never completed
"""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.commerce import schemas
from app.modules.commerce.models import Listing, Order
from app.modules.commerce.service import change_order_status
from app.modules.livestock.models import Animal

logger = logging.getLogger("app.orders")

BATCH_SIZE = 200
_RELIST_TOLERANCE = timedelta(minutes=1)


async def _relist_animals(db: AsyncSession, order: Order, order_created_at: datetime) -> None:
    """Cancelling an order frees the animal (reserved -> for_sale) but, by
    design, doesn't reactivate its listing (staff normally re-list by hand,
    since the old price/photos may be stale). For an *expired guest hold* that
    would defeat the point - the animal would stay off the storefront - so we
    put the listing that this order deactivated back online. Only when the
    animal is genuinely for_sale again and has no other active listing."""
    for item in order.items:
        if item.animal_id is None:
            continue
        animal = await db.get(Animal, item.animal_id)
        if animal is None or animal.status != "for_sale":
            continue
        active = await db.execute(
            select(Listing.id).where(Listing.animal_id == item.animal_id, Listing.is_active.is_(True))
        )
        if active.first() is not None:
            continue
        candidate = await db.execute(
            select(Listing)
            .where(
                Listing.organization_id == order.organization_id,
                Listing.animal_id == item.animal_id,
                Listing.updated_at >= order_created_at - _RELIST_TOLERANCE,
            )
            .order_by(Listing.updated_at.desc())
            .limit(1)
        )
        listing = candidate.scalar_one_or_none()
        if listing is not None:
            listing.is_active = True
    await db.commit()


async def expire_stale_guest_orders(db: AsyncSession, now: datetime | None = None) -> int:
    """Cancels stale guest orders across all organizations; returns how many
    were cancelled. Safe to run concurrently on several replicas: a second
    runner sees the order already cancelled, the transition is rejected, and
    it just moves on."""
    settings = get_settings()
    now = now or datetime.now(timezone.utc)

    rules = []
    if settings.GUEST_ORDER_TTL_MINUTES > 0:
        rules.append(and_(
            Order.status == "pending",
            Order.created_at < now - timedelta(minutes=settings.GUEST_ORDER_TTL_MINUTES),
        ))
    if settings.PAYMENT_PENDING_TTL_HOURS > 0:
        # updated_at moves when payment is initiated (pending -> payment_pending)
        rules.append(and_(
            Order.status == "payment_pending",
            Order.updated_at < now - timedelta(hours=settings.PAYMENT_PENDING_TTL_HOURS),
        ))
    if not rules:
        return 0

    rows = (await db.execute(
        select(Order.id, Order.organization_id, Order.created_at)
        .where(Order.created_by.is_(None), or_(*rules))
        .order_by(Order.created_at)
        .limit(BATCH_SIZE)
    )).all()

    cancelled = 0
    for order_id, org_id, created_at in rows:
        try:
            order = await change_order_status(
                db, org_id, order_id, None,
                schemas.OrderStatusChange(status="cancelled", reason="Unpaid order expired automatically"),
            )
        except HTTPException:
            await db.rollback()  # already moved on (paid/cancelled elsewhere) - not an error
            continue
        await _relist_animals(db, order, created_at)
        cancelled += 1
    if cancelled:
        logger.info("expired %d stale guest order(s)", cancelled)
    return cancelled
