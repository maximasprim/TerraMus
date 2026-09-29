import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.identity.deps import require_permission
from app.modules.identity.models import User
from app.modules.inventory import schemas, service

router = APIRouter(prefix="/api/v1/inventory", tags=["inventory"])


@router.get("/items", response_model=list[schemas.InventoryItemOut])
async def list_items(
    user: User = Depends(require_permission("inventory.read")),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_items(db, user.organization_id)


@router.post("/items", response_model=schemas.InventoryItemOut, status_code=201)
async def create_item(
    req: schemas.InventoryItemCreate,
    user: User = Depends(require_permission("inventory.adjust")),
    db: AsyncSession = Depends(get_db),
):
    item = await service.create_item(db, user.organization_id, req)
    return schemas.InventoryItemOut(
        id=item.id, organization_id=item.organization_id, farm_id=item.farm_id,
        name=item.name, category=item.category, unit=item.unit,
        reorder_level=item.reorder_level, allow_negative_stock=item.allow_negative_stock,
        notes=item.notes, current_stock=0,
    )


@router.get("/items/{item_id}/movements", response_model=list[schemas.StockMovementOut])
async def list_movements(
    item_id: uuid.UUID,
    user: User = Depends(require_permission("inventory.read")),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_movements(db, user.organization_id, item_id)


@router.post("/items/{item_id}/movements", response_model=schemas.StockMovementOut, status_code=201)
async def record_movement(
    item_id: uuid.UUID,
    req: schemas.StockMovementCreate,
    user: User = Depends(require_permission("inventory.adjust")),
    db: AsyncSession = Depends(get_db),
):
    return await service.record_movement(db, user.organization_id, item_id, user.id, req)


@router.get("/low-stock", response_model=list[schemas.LowStockItem])
async def low_stock(
    user: User = Depends(require_permission("inventory.read")),
    db: AsyncSession = Depends(get_db),
):
    return await service.low_stock_items(db, user.organization_id)


@router.get("/valuation", response_model=list[schemas.ValuationRow])
async def valuation(
    user: User = Depends(require_permission("inventory.read")),
    db: AsyncSession = Depends(get_db),
):
    """Spec §14 'inventory valuation', added this session - FIFO-costed
    (see service._fifo_layers_remaining). Kept as its own endpoint rather
    than folded into GET /items: it walks each item's full movement history
    to compute, which is real per-item work not worth paying on every plain
    item-list call (spec §46 - avoid unnecessary per-request cost)."""
    return await service.valuation_report(db, user.organization_id)
