import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.identity.deps import require_permission
from app.modules.identity.models import User
from app.modules.bulk_import import schemas, service

router = APIRouter(prefix="/api/v1/bulk-import", tags=["bulk-import"])

# Spec §73's flow (Upload -> Validate -> Preview -> Show errors -> Confirm ->
# Import) maps to one call with dry_run=true (the default - preview first is
# the safe default, not an opt-in) followed by a second call with
# dry_run=false once the caller has reviewed the error report.


@router.post("/customers", response_model=schemas.BulkImportResult)
async def import_customers(
    file: UploadFile = File(...),
    dry_run: bool = Query(True),
    user: User = Depends(require_permission("customers.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.import_customers(db, user.organization_id, await file.read(), dry_run)


@router.post("/suppliers", response_model=schemas.BulkImportResult)
async def import_suppliers(
    file: UploadFile = File(...),
    dry_run: bool = Query(True),
    user: User = Depends(require_permission("procurement.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.import_suppliers(db, user.organization_id, await file.read(), dry_run)


@router.post("/inventory-items", response_model=schemas.BulkImportResult)
async def import_inventory_items(
    file: UploadFile = File(...),
    dry_run: bool = Query(True),
    user: User = Depends(require_permission("inventory.adjust")),
    db: AsyncSession = Depends(get_db),
):
    return await service.import_inventory_items(db, user.organization_id, await file.read(), dry_run)


@router.post("/livestock", response_model=schemas.BulkImportResult)
async def import_livestock(
    farm_id: uuid.UUID,
    location_id: uuid.UUID | None = Query(None),
    file: UploadFile = File(...),
    dry_run: bool = Query(True),
    user: User = Depends(require_permission("livestock.create")),
    db: AsyncSession = Depends(get_db),
):
    return await service.import_livestock(
        db, user.organization_id, user.id, farm_id, location_id, await file.read(), dry_run,
    )


@router.post("/crops", response_model=schemas.BulkImportResult)
async def import_crops(
    farm_id: uuid.UUID,
    location_id: uuid.UUID | None = Query(None),
    file: UploadFile = File(...),
    dry_run: bool = Query(True),
    user: User = Depends(require_permission("crops.create")),
    db: AsyncSession = Depends(get_db),
):
    return await service.import_crops(
        db, user.organization_id, user.id, farm_id, location_id, await file.read(), dry_run,
    )
