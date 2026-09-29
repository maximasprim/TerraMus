import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.billing.models import (
    SubscriptionTier, Subscription, SubscriptionPayment, SubscriptionPaymentWebhookEvent,
)
from app.modules.payments.providers import get_provider

# Seeded idempotently (see ensure_default_tiers) rather than via a migration
# data-seed, so changing a price here doesn't require a new migration - same
# reasoning as identity.service.ensure_permission_catalog for the permission
# catalog. slug is the stable identifier; name/price can change over time.
DEFAULT_TIERS = [
    # (slug, name, monthly_price_kes, max_users, max_animals)
    ("free", "Free", 0, 2, 25),
    ("basic", "Basic", 1500, 5, 150),
    ("pro", "Pro", 4500, 20, 1000),
    ("enterprise", "Enterprise", 15000, None, None),
]


async def ensure_default_tiers(db: AsyncSession) -> dict[str, SubscriptionTier]:
    result = await db.execute(select(SubscriptionTier))
    existing = {t.slug: t for t in result.scalars().all()}
    for slug, name, price, max_users, max_animals in DEFAULT_TIERS:
        if slug not in existing:
            tier = SubscriptionTier(
                slug=slug, name=name, monthly_price_kes=price,
                max_users=max_users, max_animals=max_animals,
            )
            db.add(tier)
            existing[slug] = tier
    await db.flush()
    return existing


async def list_tiers(db: AsyncSession) -> list[SubscriptionTier]:
    result = await db.execute(
        select(SubscriptionTier).where(SubscriptionTier.is_active.is_(True)).order_by(SubscriptionTier.monthly_price_kes)
    )
    return list(result.scalars().all())


async def get_or_create_subscription(db: AsyncSession, org_id: uuid.UUID) -> Subscription:
    """Lazily creates a trialing Free subscription the first time an org's
    billing status is looked at. Kept out of
    identity.service.register_organization entirely - that function's
    existing behavior/signature/transaction is untouched, so nothing that
    already depends on it (including scripts/seed.py) is affected."""
    result = await db.execute(
        select(Subscription).where(Subscription.organization_id == org_id)
    )
    sub = result.scalar_one_or_none()
    if sub:
        return sub

    tiers = await ensure_default_tiers(db)
    free_tier = tiers["free"]
    now = datetime.now(timezone.utc)
    sub = Subscription(
        organization_id=org_id, tier_id=free_tier.id, status="trialing",
        current_period_start=now, current_period_end=now + timedelta(days=30),
    )
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    return sub


async def initiate_subscription_payment(
    db: AsyncSession, org_id: uuid.UUID, tier_slug: str, phone_number: str,
) -> SubscriptionPayment:
    tiers = await ensure_default_tiers(db)
    tier = tiers.get(tier_slug)
    if not tier or not tier.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown or inactive tier '{tier_slug}'")
    if tier.monthly_price_kes <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The free tier does not require payment")

    await check_tier_covers_current_usage(db, org_id, tier)

    subscription = await get_or_create_subscription(db, org_id)

    payment = SubscriptionPayment(
        organization_id=org_id, subscription_id=subscription.id, tier_id=tier.id,
        provider="mpesa", provider_reference="",  # filled in once Daraja responds
        amount=tier.monthly_price_kes, currency="KES",
        status="initiated", initiated_at=datetime.now(timezone.utc),
    )
    db.add(payment)
    await db.flush()

    provider = get_provider("mpesa")
    try:
        result = await provider.initiate_payment(
            Decimal(tier.monthly_price_kes), "KES", f"sub:{org_id}", phone_number,
        )
    except httpx.HTTPError as exc:
        # Same honest-failure handling as payments/service.py._initiate -
        # the sandbox this was built in cannot reach safaricom.co.ke, so this
        # path is exercised for real the first time against live credentials.
        payment.status = "failed"
        payment.payment_metadata = {"error": f"Provider request failed: {exc}"}
        await db.commit()
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"M-Pesa is unreachable: {exc}",
        )

    payment.provider_reference = result.provider_reference
    payment.status = result.status
    payment.payment_metadata = result.raw_response
    await db.commit()
    await db.refresh(payment)
    return payment


async def handle_mpesa_webhook(db: AsyncSession, headers: dict[str, str], body: bytes) -> dict:
    """Identical idempotency + verification pattern to
    payments.service.handle_webhook - see that function's comments for the
    full reasoning. Kept as a separate handler (rather than branching inside
    the existing one) because it resolves against SubscriptionPayment /
    Subscription, not Payment / Order, and mixing the two would mean every
    reader of payments/service.py now has to hold both flows in their head."""
    provider = get_provider("mpesa")
    try:
        result = provider.verify_and_parse_webhook(headers, body)
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Webhook verification failed: {exc}")

    existing = await db.execute(
        select(SubscriptionPaymentWebhookEvent).where(
            SubscriptionPaymentWebhookEvent.provider == "mpesa",
            SubscriptionPaymentWebhookEvent.event_id == result.event_id,
        )
    )
    if existing.scalar_one_or_none():
        return {"status": "already_processed", "event_id": result.event_id}

    payment_result = await db.execute(
        select(SubscriptionPayment).where(
            SubscriptionPayment.provider == "mpesa",
            SubscriptionPayment.provider_reference == result.provider_reference,
        )
    )
    payment = payment_result.scalar_one_or_none()

    event = SubscriptionPaymentWebhookEvent(
        payment_id=payment.id if payment else None,
        provider="mpesa", event_id=result.event_id,
        status=result.status, raw_payload=result.raw_payload,
    )
    db.add(event)

    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        return {"status": "already_processed", "event_id": result.event_id}

    if not payment:
        await db.commit()
        return {"status": "received", "note": "no matching subscription payment found for this reference"}

    payment.status = result.status
    if result.status in ("successful", "failed"):
        payment.completed_at = datetime.now(timezone.utc)

    if result.status == "successful":
        sub_result = await db.execute(select(Subscription).where(Subscription.id == payment.subscription_id))
        subscription = sub_result.scalar_one()
        subscription.tier_id = payment.tier_id
        subscription.status = "active"
        now = datetime.now(timezone.utc)
        subscription.current_period_start = now
        subscription.current_period_end = now + timedelta(days=30)

    await db.commit()

    # Notify the org via the existing notifications module - reuses
    # notify_users_with_permission exactly as the rest of the app does
    # (finance/handlers.py, notifications/handlers.py), fanning out to
    # everyone with 'finance.read' in that org rather than inventing a new
    # notification path for billing specifically.
    if result.status in ("successful", "failed"):
        from app.modules.notifications.service import notify_users_with_permission
        tier_result = await db.execute(select(SubscriptionTier).where(SubscriptionTier.id == payment.tier_id))
        tier = tier_result.scalar_one()
        if result.status == "successful":
            title, body = "Subscription payment successful", f"Your subscription is now active on the '{tier.name}' plan."
        else:
            title, body = "Subscription payment failed", f"Your payment for the '{tier.name}' plan did not go through. Please try again."
        await notify_users_with_permission(
            db, payment.organization_id, "finance.read", category="billing",
            title=title, body=body, related_entity_type="subscription_payment", related_entity_id=payment.id,
        )

    return {"status": "processed", "payment_status": payment.status}


async def expire_overdue_subscriptions(db: AsyncSession) -> dict:
    """Guarded by a Postgres advisory lock (pg_try_advisory_lock) so this
    is actually safe to run from multiple replicas at once, not just
    "harmless because it's idempotent" -- with more than one API instance
    running the lifespan loop from HOW_TO_APPLY.md, without this lock two
    replicas could both read the same overdue subscriptions and both write
    to them in the same window; the lock means only one replica's call
    actually does the work per invocation, and the others return
    immediately with skipped=True. No new infrastructure (Redis, Celery
    beat, a leader-election sidecar) -- Postgres itself, which every
    replica already has a connection to, is the lock.

    The lock key (a fixed arbitrary int64) must be identical across every
    caller of this function for the mutual exclusion to mean anything; it
    is NOT organization-scoped -- this locks the entire lifecycle sweep,
    not per-org, since the sweep itself is a single query across all orgs.
    """
    LOCK_KEY = 8_851_402_017  # arbitrary, fixed -- must never change once deployed

    got_lock = (await db.execute(select(func.pg_try_advisory_lock(LOCK_KEY)))).scalar_one()
    if not got_lock:
        return {"marked_past_due": 0, "marked_cancelled": 0, "skipped": True}

    try:
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(Subscription).where(
                Subscription.status.in_(("trialing", "active")),
                Subscription.current_period_end.is_not(None),
                Subscription.current_period_end < now,
            )
        )
        overdue = list(result.scalars().all())

        marked_past_due = 0
        marked_cancelled = 0
        for sub in overdue:
            if sub.cancel_at_period_end:
                sub.status = "cancelled"
                marked_cancelled += 1
            else:
                sub.status = "past_due"
                marked_past_due += 1

        await db.commit()
        return {"marked_past_due": marked_past_due, "marked_cancelled": marked_cancelled, "skipped": False}
    finally:
        await db.execute(select(func.pg_advisory_unlock(LOCK_KEY)))


async def check_animal_limit(db: AsyncSession, org_id: uuid.UUID) -> None:
    """Raises 402 if the org's subscription tier caps max_animals and it's
    already at/over that cap. Called from livestock.service.create_animal
    (see HOW_TO_APPLY.md for the one-line patch). See check_user_limit
    below for the max_users equivalent."""
    from app.modules.livestock.models import Animal, INACTIVE_STATUSES

    subscription = await get_or_create_subscription(db, org_id)
    tier_result = await db.execute(select(SubscriptionTier).where(SubscriptionTier.id == subscription.tier_id))
    tier = tier_result.scalar_one()
    if tier.max_animals is None:
        return  # unlimited on this tier

    count_result = await db.execute(
        select(func.count(Animal.id)).where(
            Animal.organization_id == org_id, Animal.status.notin_(INACTIVE_STATUSES),
        )
    )
    current_count = count_result.scalar_one()
    if current_count >= tier.max_animals:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            f"Your '{tier.name}' plan allows up to {tier.max_animals} animals. "
            f"Upgrade your subscription to add more.",
        )


async def check_user_limit(db: AsyncSession, org_id: uuid.UUID) -> None:
    """Raises 402 if the org's subscription tier caps max_users and it's
    already at/over that cap. Called from identity's POST /api/v1/users
    handler (see HOW_TO_APPLY.md for the patch) - that endpoint already
    exists in this codebase (identity/router.py's users_router,
    schemas.CreateUserRequest) for adding a teammate to an org; this just
    adds the tier check it was missing."""
    from app.modules.identity.models import User

    subscription = await get_or_create_subscription(db, org_id)
    tier_result = await db.execute(select(SubscriptionTier).where(SubscriptionTier.id == subscription.tier_id))
    tier = tier_result.scalar_one()
    if tier.max_users is None:
        return  # unlimited on this tier

    count_result = await db.execute(select(func.count(User.id)).where(User.organization_id == org_id))
    current_count = count_result.scalar_one()
    if current_count >= tier.max_users:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            f"Your '{tier.name}' plan allows up to {tier.max_users} users. "
            f"Upgrade your subscription to add more.",
        )


async def check_tier_covers_current_usage(db: AsyncSession, org_id: uuid.UUID, target_tier: SubscriptionTier) -> None:
    """Called from initiate_subscription_payment before letting an org pay
    to switch to a tier (upgrade OR downgrade) - blocks a downgrade that
    would immediately leave the org over the new tier's limits, e.g. an org
    with 200 animals paying to move to a 25-animal tier. Deliberately
    blocks rather than silently truncating/archiving anything: there's no
    reasonable automatic choice of *which* 175 animals or users to drop."""
    from app.modules.identity.models import User
    from app.modules.livestock.models import Animal, INACTIVE_STATUSES

    if target_tier.max_users is not None:
        user_count = (await db.execute(
            select(func.count(User.id)).where(User.organization_id == org_id)
        )).scalar_one()
        if user_count > target_tier.max_users:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"You currently have {user_count} users, which is more than the "
                f"'{target_tier.name}' plan's limit of {target_tier.max_users}. "
                f"Remove users before downgrading.",
            )

    if target_tier.max_animals is not None:
        animal_count = (await db.execute(
            select(func.count(Animal.id)).where(
                Animal.organization_id == org_id, Animal.status.notin_(INACTIVE_STATUSES),
            )
        )).scalar_one()
        if animal_count > target_tier.max_animals:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"You currently have {animal_count} animals, which is more than the "
                f"'{target_tier.name}' plan's limit of {target_tier.max_animals}. "
                f"Archive animals before downgrading.",
            )


async def list_subscription_payments(db: AsyncSession, org_id: uuid.UUID) -> list[SubscriptionPayment]:
    """Tenant-facing payment history / receipts. Deliberately NOT a
    generated PDF (unlike finance.pdf's order invoices) - this returns the
    payment ledger rows directly; each has amount/currency/provider_
    reference/timestamps, which is what "a receipt" actually needs here.
    A PDF version would follow finance/pdf.py's pattern if wanted later."""
    result = await db.execute(
        select(SubscriptionPayment)
        .where(SubscriptionPayment.organization_id == org_id)
        .order_by(SubscriptionPayment.initiated_at.desc())
    )
    return list(result.scalars().all())


async def render_subscription_receipt_pdf_bytes(db: AsyncSession, org_id: uuid.UUID, payment_id: uuid.UUID) -> bytes:
    """Same split as finance.service.render_invoice_pdf_bytes: gathers
    exactly what billing/pdf.py's pure renderer needs, org-scoped, and
    hands off - see that module's docstring for the same "not run in this
    sandbox" caveat."""
    from app.modules.identity.models import Organization
    from app.modules.billing.pdf import render_subscription_receipt_pdf

    payment_result = await db.execute(
        select(SubscriptionPayment).where(
            SubscriptionPayment.id == payment_id, SubscriptionPayment.organization_id == org_id,
        )
    )
    payment = payment_result.scalar_one_or_none()
    if not payment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")

    tier_result = await db.execute(select(SubscriptionTier).where(SubscriptionTier.id == payment.tier_id))
    tier = tier_result.scalar_one()

    org_result = await db.execute(select(Organization).where(Organization.id == org_id))
    organization = org_result.scalar_one()

    return render_subscription_receipt_pdf(payment, tier, organization)
