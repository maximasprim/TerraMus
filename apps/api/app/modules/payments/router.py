import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.identity.deps import require_permission
from app.modules.identity.models import User
from app.modules.payments import schemas, service

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])
webhooks_router = APIRouter(prefix="/api/v1/payments/webhooks", tags=["payments"])


@router.post("/mpesa", response_model=schemas.PaymentOut, status_code=201)
async def initiate_mpesa(
    req: schemas.InitiatePaymentRequest,
    user: User = Depends(require_permission("payments.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.initiate_mpesa_payment(db, user.organization_id, user.id, req)


@router.post("/stripe", response_model=schemas.PaymentOut, status_code=201)
async def initiate_stripe(
    req: schemas.InitiatePaymentRequest,
    user: User = Depends(require_permission("payments.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.initiate_stripe_payment(db, user.organization_id, user.id, req)


@router.post("/mock", response_model=schemas.PaymentOut, status_code=201)
async def initiate_mock(
    req: schemas.InitiatePaymentRequest,
    user: User = Depends(require_permission("payments.manage")),
    db: AsyncSession = Depends(get_db),
):
    """Dev/test-only provider - see providers/mock.py. Still requires
    payments.manage like the real providers, since it's reachable in prod
    builds too unless explicitly disabled at the deployment/config level."""
    return await service.initiate_mock_payment(db, user.organization_id, user.id, req)


@router.get("/{payment_id}", response_model=schemas.PaymentOut)
async def get_payment(
    payment_id: uuid.UUID,
    user: User = Depends(require_permission("payments.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_payment(db, user.organization_id, payment_id)


# Webhook endpoints are intentionally NOT behind require_permission - the
# provider calls these directly, with no user session. Authenticity comes
# from the provider's own signature/shared-secret scheme (see providers/*.py),
# verified inside service.handle_webhook, not from our JWT auth.
@webhooks_router.post("/mpesa")
async def mpesa_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.body()
    return await service.handle_webhook(db, "mpesa", dict(request.headers), body)


@webhooks_router.post("/stripe")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.body()
    return await service.handle_webhook(db, "stripe", dict(request.headers), body)


@webhooks_router.post("/mock")
async def mock_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.body()
    return await service.handle_webhook(db, "mock", dict(request.headers), body)
