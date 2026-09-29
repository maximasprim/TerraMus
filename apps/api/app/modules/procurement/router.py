import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.identity.deps import require_permission
from app.modules.identity.models import User
from app.modules.procurement import schemas, service

router = APIRouter(prefix="/api/v1/procurement", tags=["procurement"])


# ---- Suppliers -------------------------------------------------------------

@router.get("/suppliers", response_model=list[schemas.SupplierOut])
async def list_suppliers(
    is_active: bool | None = Query(None),
    search: str | None = Query(None),
    user: User = Depends(require_permission("procurement.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_suppliers(db, user.organization_id, is_active, search)


@router.post("/suppliers", response_model=schemas.SupplierOut, status_code=201)
async def create_supplier(
    req: schemas.SupplierCreate,
    user: User = Depends(require_permission("procurement.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.create_supplier(db, user.organization_id, req)


@router.get("/suppliers/{supplier_id}", response_model=schemas.SupplierOut)
async def get_supplier(
    supplier_id: uuid.UUID,
    user: User = Depends(require_permission("procurement.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_supplier(db, user.organization_id, supplier_id)


@router.patch("/suppliers/{supplier_id}", response_model=schemas.SupplierOut)
async def update_supplier(
    supplier_id: uuid.UUID,
    req: schemas.SupplierUpdate,
    user: User = Depends(require_permission("procurement.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.update_supplier(db, user.organization_id, supplier_id, req)


# ---- Purchase orders --------------------------------------------------------

@router.get("/purchase-orders", response_model=list[schemas.PurchaseOrderOut])
async def list_purchase_orders(
    status: str | None = Query(None),
    supplier_id: uuid.UUID | None = Query(None),
    user: User = Depends(require_permission("procurement.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_purchase_orders(db, user.organization_id, status, supplier_id)


@router.post("/purchase-orders", response_model=schemas.PurchaseOrderOut, status_code=201)
async def create_purchase_order(
    req: schemas.PurchaseOrderCreate,
    user: User = Depends(require_permission("procurement.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.create_purchase_order(db, user.organization_id, user.id, req)


@router.get("/purchase-orders/{po_id}", response_model=schemas.PurchaseOrderDetailOut)
async def get_purchase_order(
    po_id: uuid.UUID,
    user: User = Depends(require_permission("procurement.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_purchase_order_detail(db, user.organization_id, po_id)


@router.patch("/purchase-orders/{po_id}/status", response_model=schemas.PurchaseOrderOut)
async def update_purchase_order_status(
    po_id: uuid.UUID,
    req: schemas.PurchaseOrderStatusUpdate,
    user: User = Depends(require_permission("procurement.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.update_status(db, user.organization_id, po_id, user.id, req)
