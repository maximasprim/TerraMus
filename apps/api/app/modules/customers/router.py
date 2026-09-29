import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.identity.deps import require_permission
from app.modules.identity.models import User
from app.modules.customers import schemas, service

router = APIRouter(prefix="/api/v1/customers", tags=["customers"])


@router.get("", response_model=list[schemas.CustomerOut])
async def list_customers(
    customer_type: str | None = Query(None),
    search: str | None = Query(None),
    user: User = Depends(require_permission("customers.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_customers(db, user.organization_id, customer_type, search)


@router.post("", response_model=schemas.CustomerOut, status_code=201)
async def create_customer(
    req: schemas.CustomerCreate,
    user: User = Depends(require_permission("customers.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.create_customer(db, user.organization_id, req)


@router.get("/{customer_id}", response_model=schemas.CustomerOut)
async def get_customer(
    customer_id: uuid.UUID,
    user: User = Depends(require_permission("customers.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_customer(db, user.organization_id, customer_id)


@router.patch("/{customer_id}", response_model=schemas.CustomerOut)
async def update_customer(
    customer_id: uuid.UUID,
    req: schemas.CustomerUpdate,
    user: User = Depends(require_permission("customers.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.update_customer(db, user.organization_id, customer_id, req)
