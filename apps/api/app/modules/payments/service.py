import uuid
from datetime import datetime, timezone
from decimal import Decimal

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import publish
from app.core.phone import normalise_ke_msisdn
from app.modules.payments.models import Payment, PaymentWebhookEvent
from app.modules.payments import schemas
from app.modules.payments.providers import get_provider
from app.modules.commerce.service import get_order, change_order_status
from app.modules.commerce import schemas as commerce_schemas


async def _initiate(
    db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID,
    provider_name: str, req: schemas.InitiatePaymentRequest,
) -> Payment:
    order = await get_order(db, org_id, req.order_id)
    if order.status not in ("pending", "payment_pending"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot initiate payment for an order in status '{order.status}'",
        )
    if provider_name == "mpesa":
        # Customers type 0712 345 678 / +254 712 345 678; Daraja only accepts 2547XXXXXXXX.
        try:
            req = req.model_copy(update={"phone_or_token": normalise_ke_msisdn(req.phone_or_token)})
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    payment = Payment(
        organization_id=org_id, order_id=order.id, provider=provider_name,
        provider_reference="",  # filled in once the provider responds
        amount=order.total_amount, currency="KES",
        status="initiated", initiated_at=datetime.now(timezone.utc),
    )
    db.add(payment)
    await db.flush()

    provider = get_provider(provider_name)
    try:
        result = await provider.initiate_payment(
            Decimal(order.total_amount), payment.currency, str(order.id), req.phone_or_token,
        )
    except httpx.HTTPError as exc:
        # Real-world failure mode for mpesa/stripe in this environment: the
        # provider's API is genuinely unreachable (see providers/mpesa.py and
        # stripe_provider.py docstrings). Surface this honestly rather than
        # silently marking the payment failed as if the provider rejected it.
        payment.status = "failed"
        payment.payment_metadata = {"error": f"Provider request failed: {exc}"}
        await db.commit()
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"Payment provider '{provider_name}' is unreachable: {exc}",
        )

    payment.provider_reference = result.provider_reference
    payment.status = result.status
    payment.payment_metadata = result.raw_response

    if order.status == "pending":
        await change_order_status(
            db, org_id, order.id, user_id,
            commerce_schemas.OrderStatusChange(status="payment_pending", reason=f"{provider_name} payment initiated"),
        )
    await db.commit()
    await db.refresh(payment)

    await publish("PaymentInitiated", {
        "organization_id": str(org_id), "payment_id": str(payment.id), "provider": provider_name,
    })
    return payment


async def initiate_mpesa_payment(
    db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID, req: schemas.InitiatePaymentRequest,
) -> Payment:
    return await _initiate(db, org_id, user_id, "mpesa", req)


async def initiate_stripe_payment(
    db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID, req: schemas.InitiatePaymentRequest,
) -> Payment:
    return await _initiate(db, org_id, user_id, "stripe", req)


async def initiate_mock_payment(
    db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID, req: schemas.InitiatePaymentRequest,
) -> Payment:
    """Not part of the public spec's provider list - exists so the full
    payment→webhook→paid flow can be exercised in dev/tests without real
    credentials (spec §51)."""
    return await _initiate(db, org_id, user_id, "mock", req)


async def handle_webhook(db: AsyncSession, provider_name: str, headers: dict[str, str], body: bytes) -> dict:
    provider = get_provider(provider_name)
    try:
        result = provider.verify_and_parse_webhook(headers, body)
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Webhook verification failed: {exc}")

    # Idempotency: a duplicate (provider, event_id) insert is rejected by the
    # DB unique constraint - this is the actual source of truth, not the
    # application-level check, which only exists for a clean early return.
    existing = await db.execute(
        select(PaymentWebhookEvent).where(
            PaymentWebhookEvent.provider == provider_name, PaymentWebhookEvent.event_id == result.event_id,
        )
    )
    if existing.scalar_one_or_none():
        return {"status": "already_processed", "event_id": result.event_id}

    payment_result = await db.execute(
        select(Payment).where(Payment.provider == provider_name, Payment.provider_reference == result.provider_reference)
    )
    payment = payment_result.scalar_one_or_none()

    event = PaymentWebhookEvent(
        payment_id=payment.id if payment else None,
        provider=provider_name, event_id=result.event_id,
        status=result.status, raw_payload=result.raw_payload,
    )
    db.add(event)

    try:
        await db.flush()
    except IntegrityError:
        # Race: two identical callbacks arrived concurrently and both passed
        # the SELECT check above before either committed. The unique
        # constraint catches it here instead.
        await db.rollback()
        return {"status": "already_processed", "event_id": result.event_id}

    if not payment:
        await db.commit()
        return {"status": "received", "note": "no matching payment found for this reference"}

    payment.status = result.status
    if result.status in ("successful", "failed"):
        payment.completed_at = datetime.now(timezone.utc)

    if result.status == "successful":
        await change_order_status(
            db, payment.organization_id, payment.order_id, None,
            commerce_schemas.OrderStatusChange(status="paid", reason=f"{provider_name} payment confirmed"),
        )
        await publish("PaymentSucceeded", {
            "organization_id": str(payment.organization_id), "payment_id": str(payment.id),
            "order_id": str(payment.order_id), "amount": str(payment.amount),
        })
    elif result.status == "failed":
        await publish("PaymentFailed", {
            "organization_id": str(payment.organization_id), "payment_id": str(payment.id),
        })

    await db.commit()
    return {"status": "processed", "payment_status": payment.status}


async def get_payment(db: AsyncSession, org_id: uuid.UUID, payment_id: uuid.UUID) -> Payment:
    result = await db.execute(select(Payment).where(Payment.id == payment_id, Payment.organization_id == org_id))
    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    return payment


async def list_payments_for_order(db: AsyncSession, org_id: uuid.UUID, order_id: uuid.UUID) -> list[Payment]:
    await get_order(db, org_id, order_id)
    result = await db.execute(
        select(Payment).where(Payment.organization_id == org_id, Payment.order_id == order_id)
        .order_by(Payment.initiated_at.desc())
    )
    return list(result.scalars().all())
