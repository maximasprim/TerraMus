import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.identity.deps import require_permission
from app.modules.identity.models import User
from app.modules.receivables import schemas, service

router = APIRouter(prefix="/api/v1/receivables", tags=["receivables"])


@router.post("/charges", status_code=201)
async def add_charge(req: schemas.ChargeCreate, user: User = Depends(require_permission("finance.create")), db: AsyncSession = Depends(get_db)):
    e = await service.add_charge(db, user.organization_id, user.id, req)
    return service._entry_out(e)


@router.post("/payments", status_code=201)
async def add_payment(req: schemas.PaymentCreate, user: User = Depends(require_permission("finance.create")), db: AsyncSession = Depends(get_db)):
    return await service.add_payment(db, user.organization_id, user.id, req)


@router.post("/writeoffs", status_code=201)
async def add_writeoff(req: schemas.WriteoffCreate, user: User = Depends(require_permission("finance.create")), db: AsyncSession = Depends(get_db)):
    e = await service.add_writeoff(db, user.organization_id, user.id, req)
    return service._entry_out(e)


@router.get("/customers/{customer_id}/statement")
async def statement(customer_id: uuid.UUID, as_of: date | None = Query(None), user: User = Depends(require_permission("finance.read")),
                    db: AsyncSession = Depends(get_db)):
    return await service.statement(db, user.organization_id, customer_id, as_of)


@router.get("/balances")
async def balances(as_of: date | None = Query(None), user: User = Depends(require_permission("finance.read")), db: AsyncSession = Depends(get_db)):
    return await service.balances(db, user.organization_id, as_of)


@router.get("/sales-by-salesperson")
async def sales_by_salesperson(start_date: date = Query(...), end_date: date = Query(...),
                               user: User = Depends(require_permission("finance.read")), db: AsyncSession = Depends(get_db)):
    return await service.sales_by_salesperson(db, user.organization_id, start_date, end_date)
