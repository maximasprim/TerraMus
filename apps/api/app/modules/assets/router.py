import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.identity.deps import require_permission
from app.modules.identity.models import User
from app.modules.assets import schemas, service

router = APIRouter(prefix="/api/v1/assets", tags=["assets"])


@router.get("", response_model=list[schemas.AssetOut])
async def list_assets(
    asset_type: str | None = Query(None),
    status: str | None = Query(None),
    assigned_farm_id: uuid.UUID | None = Query(None),
    search: str | None = Query(None),
    user: User = Depends(require_permission("assets.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_assets(db, user.organization_id, asset_type, status, assigned_farm_id, search)


@router.post("", response_model=schemas.AssetOut, status_code=201)
async def create_asset(
    req: schemas.AssetCreate,
    user: User = Depends(require_permission("assets.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.create_asset(db, user.organization_id, req)


@router.get("/{asset_id}", response_model=schemas.AssetDetailOut)
async def get_asset(
    asset_id: uuid.UUID,
    user: User = Depends(require_permission("assets.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_asset_detail(db, user.organization_id, asset_id)


@router.patch("/{asset_id}", response_model=schemas.AssetOut)
async def update_asset(
    asset_id: uuid.UUID,
    req: schemas.AssetUpdate,
    user: User = Depends(require_permission("assets.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.update_asset(db, user.organization_id, asset_id, req)


@router.get("/{asset_id}/maintenance", response_model=list[schemas.MaintenanceRecordOut])
async def list_maintenance_records(
    asset_id: uuid.UUID,
    user: User = Depends(require_permission("assets.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_maintenance_records(db, user.organization_id, asset_id)


@router.post("/{asset_id}/maintenance", response_model=schemas.MaintenanceRecordOut, status_code=201)
async def add_maintenance_record(
    asset_id: uuid.UUID,
    req: schemas.MaintenanceRecordCreate,
    user: User = Depends(require_permission("assets.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.add_maintenance_record(db, user.organization_id, asset_id, req)
