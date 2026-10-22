import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.identity.deps import require_permission
from app.modules.identity.models import User
from app.modules.finance import schemas, service

router = APIRouter(prefix="/api/v1/finance", tags=["finance"])


@router.get("/transactions", response_model=list[schemas.FinanceTransactionOut])
async def list_transactions(
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    transaction_type: str | None = Query(None),
    category: str | None = Query(None),
    farm_id: uuid.UUID | None = Query(None),
    activity: str | None = Query(None),
    user: User = Depends(require_permission("finance.read")),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_transactions(db, user.organization_id, start_date, end_date, transaction_type, category,
                                           farm_id, activity)


@router.post("/transactions", response_model=schemas.FinanceTransactionOut, status_code=201)
async def record_transaction(
    req: schemas.FinanceTransactionCreate,
    user: User = Depends(require_permission("finance.create")),
    db: AsyncSession = Depends(get_db),
):
    return await service.record_transaction(db, user.organization_id, user.id, req, reference_type="manual")


@router.get("/summary", response_model=schemas.FinanceSummary)
async def summary(
    start_date: date = Query(...),
    end_date: date = Query(...),
    user: User = Depends(require_permission("finance.read")),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_summary(db, user.organization_id, start_date, end_date)


@router.get("/orders/{order_id}/invoice", response_model=schemas.InvoiceOut)
async def get_invoice(
    order_id: uuid.UUID,
    user: User = Depends(require_permission("finance.read")),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_invoice_for_order(db, user.organization_id, order_id)


@router.get("/orders/{order_id}/invoice.pdf")
async def get_invoice_pdf(
    order_id: uuid.UUID,
    user: User = Depends(require_permission("finance.read")),
    db: AsyncSession = Depends(get_db),
):
    """Spec §59: 'Generate downloadable PDF.'"""
    from fastapi.responses import Response
    pdf_bytes = await service.render_invoice_pdf_bytes(db, user.organization_id, order_id)
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=invoice_{order_id}.pdf"},
    )


@router.get("/profitability")
async def profitability(
    start_date: date = Query(...),
    end_date: date = Query(...),
    farm_id: uuid.UUID | None = Query(None, description="Limit to one sub-farm"),
    activity: str | None = Query(None, pattern=schemas.ACTIVITY_PATTERN, description="Limit to one activity"),
    user: User = Depends(require_permission("finance.read")),
    db: AsyncSession = Depends(get_db),
):
    """Income, expense and net by activity, sub-farm, category and month."""
    return await service.get_profitability(db, user.organization_id, start_date, end_date, farm_id, activity)
