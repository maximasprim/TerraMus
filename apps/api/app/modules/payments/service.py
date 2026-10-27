import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import ROUND_CEILING, Decimal

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
from app.modules.payments.providers.base import WebhookResult
from app.modules.commerce.service import get_order, change_order_status
from app.modules.commerce import schemas as commerce_schemas

logger = logging.getLogger("payments")


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
    except ValueError as exc:
        # e.g. amount below KES 1, or an unusable callback secret: a problem on our side, reported as such
        payment.status = "failed"
        payment.payment_metadata = {"error": str(exc)}
        await db.commit()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE if "DARAJA" in str(exc) else status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc),
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


_SETTLED = ("successful", "refunded", "partially_refunded")


async def _notify_staff(db: AsyncSession, payment: Payment, title: str, body: str) -> None:
    """Best effort: a failed notification must never undo or hide the payment record itself."""
    try:
        from app.modules.notifications.service import notify_users_with_permission
        await notify_users_with_permission(db, payment.organization_id, "payments.manage", "payments", title, body,
                                           related_entity_type="payment", related_entity_id=payment.id)
    except Exception:  # noqa: BLE001
        logger.exception("could not notify staff about payment %s", payment.id)


async def _apply_result(db: AsyncSession, provider_name: str, payment: Payment, result: WebhookResult, source: str,
                        event: PaymentWebhookEvent | None = None) -> dict:
    """Move a payment forward from a provider result (a callback or a status query). Shared so both paths obey
    the same rules. Money is never lost: anything that cannot be applied cleanly becomes 'needs_review'."""
    event_copy = (event.event_id, event.status, event.raw_payload) if event is not None else None
    note = {"source": source, "detail": result.detail}
    if result.receipt: note["receipt"] = result.receipt
    if result.amount is not None: note["paid_amount"] = str(result.amount)
    if result.payer: note["payer"] = result.payer
    meta = dict(payment.payment_metadata or {})

    if payment.status in _SETTLED:
        # A late or repeated message must never undo a payment we already settled.
        await db.commit()
        return {"status": "ignored", "reason": f"payment already {payment.status}", "payment_status": payment.status}

    if result.status == "failed":
        payment.status, payment.completed_at = "failed", datetime.now(timezone.utc)
        meta["settlement"] = note; payment.payment_metadata = meta
        await publish("PaymentFailed", {"organization_id": str(payment.organization_id), "payment_id": str(payment.id)})
        await db.commit()
        return {"status": "processed", "payment_status": "failed"}
    if result.status != "successful":
        payment.status = result.status
        await db.commit()
        return {"status": "processed", "payment_status": payment.status}

    problems: list[str] = []
    expected = Decimal(payment.amount)
    if result.amount is not None and not (expected <= result.amount <= expected.to_integral_value(rounding=ROUND_CEILING)):
        # We ask for the order total rounded up to whole shillings; anything else is not what we requested.
        problems.append(f"amount_mismatch: order total {expected}, M-Pesa reports {result.amount}")
    if result.receipt:
        dup = await db.execute(select(Payment.id).where(
            Payment.id != payment.id, Payment.provider == provider_name,
            Payment.payment_metadata["settlement"]["receipt"].astext == result.receipt,
        ).limit(1))
        if dup.first():
            problems.append(f"duplicate_receipt: {result.receipt} is already recorded against another payment")
    pid = payment.id
    if not problems:
        # Provisionally settled: change_order_status commits, so the payment and the order become final together.
        payment.status, payment.completed_at = "successful", datetime.now(timezone.utc)
        meta["settlement"] = note
        payment.payment_metadata = meta
        try:
            await change_order_status(db, payment.organization_id, payment.order_id, None,
                                      commerce_schemas.OrderStatusChange(status="paid", reason=f"{provider_name} payment confirmed"))
        except HTTPException as exc:       # cancelled/expired meanwhile, or already paid: refused before anything changed
            await db.rollback()
            problems.append(f"order_not_payable: {exc.detail}")
            payment = (await db.execute(select(Payment).where(Payment.id == pid))).scalar_one()
            if event_copy:                  # the rollback also discarded the idempotency record: put it back
                db.add(PaymentWebhookEvent(payment_id=pid, provider=provider_name, event_id=event_copy[0],
                                           status=event_copy[1], raw_payload=event_copy[2]))
            meta = dict(payment.payment_metadata or {})
        else:
            await publish("PaymentSucceeded", {"organization_id": str(payment.organization_id), "payment_id": str(pid),
                                               "order_id": str(payment.order_id), "amount": str(payment.amount)})
            return {"status": "processed", "payment_status": "successful"}

    payment.status, payment.completed_at = "needs_review", datetime.now(timezone.utc)
    note["problems"] = problems
    meta["settlement"] = note
    payment.payment_metadata = meta
    await db.commit()
    await publish("PaymentNeedsReview", {"organization_id": str(payment.organization_id), "payment_id": str(pid)})
    await _notify_staff(db, payment, "Payment needs review",
                        f"Order {payment.order_id}: money may have been received but the order could not be marked paid. "
                        + "; ".join(problems) + ". Refund the customer or reinstate the order.")
    return {"status": "needs_review", "payment_status": "needs_review", "problems": problems}


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

    return await _apply_result(db, provider_name, payment, result, "callback", event)


async def reconcile_pending(db: AsyncSession, provider_name: str = "mpesa", min_age_minutes: int = 3,
                            max_age_hours: int = 24, limit: int = 100) -> dict:
    """Ask the provider about prompts whose callback never arrived (network blip, our server was down, a dropped
    request). Without this a customer who paid stays 'payment pending' forever. Safe to run repeatedly."""
    provider = get_provider(provider_name)
    if not hasattr(provider, "query_status"):
        return {"checked": 0, "settled": 0, "failed": 0, "still_pending": 0}
    now = datetime.now(timezone.utc)
    rows = (await db.execute(select(Payment).where(
        Payment.provider == provider_name, Payment.status.in_(("initiated", "pending")), Payment.provider_reference != "",
        Payment.initiated_at <= now - timedelta(minutes=min_age_minutes), Payment.initiated_at >= now - timedelta(hours=max_age_hours),
    ).order_by(Payment.initiated_at).limit(limit))).scalars().all()
    ids = [p.id for p in rows]
    out = {"checked": 0, "settled": 0, "failed": 0, "still_pending": 0}
    for pid in ids:
        payment = (await db.execute(select(Payment).where(Payment.id == pid))).scalar_one()
        if payment.status not in ("initiated", "pending"):
            continue                           # a callback arrived while we were working through the list
        out["checked"] += 1
        try:
            result = await provider.query_status(payment.provider_reference)
        except Exception:  # noqa: BLE001 - one unreachable lookup must not stop the others
            logger.exception("status query failed for payment %s", pid)
            out["still_pending"] += 1
            continue
        if result is None:
            out["still_pending"] += 1
            continue
        outcome = await _apply_result(db, provider_name, payment, result, "status_query")
        out["settled" if outcome.get("payment_status") in ("successful", "needs_review") else "failed"] += 1
    return out


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
