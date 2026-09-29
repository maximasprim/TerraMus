from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.identity.deps import get_tenant_context, TenantContext
from app.modules.billing import schemas, service

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])
# Unauthenticated on purpose - Safaricom calls this directly, it can't send a
# bearer token. Trust boundary is provider.verify_and_parse_webhook's shared
# secret check (see payments/providers/mpesa.py), identical to how the
# existing /api/v1/payments/webhooks/{provider} route already works.
webhooks_router = APIRouter(prefix="/api/v1/billing/webhooks", tags=["billing"])


@router.get("/tiers", response_model=list[schemas.SubscriptionTierOut])
async def list_tiers(db: AsyncSession = Depends(get_db)):
    return await service.list_tiers(db)


@router.get("/subscription", response_model=schemas.SubscriptionOut)
async def get_my_subscription(
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_or_create_subscription(db, ctx.organization_id)


@router.post("/subscribe", response_model=schemas.SubscriptionPaymentOut)
async def subscribe(
    req: schemas.SubscribeRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    """Kicks off an M-Pesa STK Push to the given phone number for the chosen
    tier's monthly price. Does NOT mark the subscription active - only the
    /webhooks/mpesa callback below can do that, same "never trust
    client-reported payment status" rule as the existing order-payments
    flow (payments/providers/base.py's docstring)."""
    return await service.initiate_subscription_payment(db, ctx.organization_id, req.tier_slug, req.phone_number)


@router.get("/payments", response_model=list[schemas.SubscriptionPaymentOut])
async def list_payments(
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    """Payment history / receipts for the caller's own org."""
    return await service.list_subscription_payments(db, ctx.organization_id)


@router.get("/payments/{payment_id}/receipt.pdf")
async def get_payment_receipt_pdf(
    payment_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
):
    """Same response pattern as finance/router.py's GET .../invoice.pdf."""
    import uuid as _uuid
    from fastapi.responses import Response
    pdf_bytes = await service.render_subscription_receipt_pdf_bytes(db, ctx.organization_id, _uuid.UUID(payment_id))
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=receipt_{payment_id}.pdf"},
    )


@webhooks_router.post("/mpesa")
async def mpesa_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.body()
    return await service.handle_mpesa_webhook(db, dict(request.headers), body)
