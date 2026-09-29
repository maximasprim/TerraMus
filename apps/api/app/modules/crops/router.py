import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.identity.deps import require_permission
from app.modules.identity.models import User
from app.modules.farm.models import Farm, Location
from app.modules.crops import schemas, service
from app.modules.crops.models import CropPlanting, INACTIVE_PLANTING_STATUSES

router = APIRouter(prefix="/api/v1/crops", tags=["crops"])


async def _assert_farm_and_location_belong_to_org(
    db: AsyncSession, org_id: uuid.UUID, farm_id: uuid.UUID, location_id: uuid.UUID | None
) -> None:
    farm = (await db.execute(
        select(Farm).where(Farm.id == farm_id, Farm.organization_id == org_id)
    )).scalar_one_or_none()
    if not farm:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Farm not found")
    if location_id is not None:
        loc = (await db.execute(
            select(Location).join(Location.branch).where(
                Location.id == location_id, Location.branch.has(farm_id=farm_id)
            )
        )).scalar_one_or_none()
        if not loc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found on this farm")


@router.get("", response_model=list[schemas.CropPlantingOut])
async def list_plantings(
    user: User = Depends(require_permission("crops.read")),
    db: AsyncSession = Depends(get_db),
    crop_type: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    farm_id: uuid.UUID | None = Query(None),
    active_only: bool = Query(False, description="Exclude harvested/failed/archived plantings"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    query = select(CropPlanting).where(CropPlanting.organization_id == user.organization_id)
    if crop_type:
        query = query.where(CropPlanting.crop_type == crop_type)
    if status_filter:
        query = query.where(CropPlanting.status == status_filter)
    if farm_id:
        query = query.where(CropPlanting.farm_id == farm_id)
    if active_only:
        query = query.where(CropPlanting.status.notin_(INACTIVE_PLANTING_STATUSES))
    query = query.order_by(CropPlanting.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("", response_model=schemas.CropPlantingOut, status_code=status.HTTP_201_CREATED)
async def create_planting(
    req: schemas.CropPlantingCreate,
    user: User = Depends(require_permission("crops.create")),
    db: AsyncSession = Depends(get_db),
):
    await _assert_farm_and_location_belong_to_org(db, user.organization_id, req.farm_id, req.location_id)
    return await service.create_planting(db, user.organization_id, user.id, req)


@router.get("/{planting_id}", response_model=schemas.CropPlantingOut)
async def get_planting(
    planting_id: uuid.UUID,
    user: User = Depends(require_permission("crops.read")),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_planting(db, planting_id, user.organization_id)


@router.patch("/{planting_id}", response_model=schemas.CropPlantingOut)
async def update_planting(
    planting_id: uuid.UUID,
    req: schemas.CropPlantingUpdate,
    user: User = Depends(require_permission("crops.update")),
    db: AsyncSession = Depends(get_db),
):
    planting = await service.get_planting(db, planting_id, user.organization_id)
    if req.location_id is not None:
        await _assert_farm_and_location_belong_to_org(db, user.organization_id, planting.farm_id, req.location_id)
    return await service.update_planting(db, planting, req, user.id)


@router.post("/{planting_id}/status", response_model=schemas.CropPlantingOut)
async def change_status(
    planting_id: uuid.UUID,
    req: schemas.StatusChangeRequest,
    user: User = Depends(require_permission("crops.update")),
    db: AsyncSession = Depends(get_db),
):
    planting = await service.get_planting(db, planting_id, user.organization_id)
    return await service.change_status(db, planting, req, user.id)


@router.get("/{planting_id}/timeline", response_model=list[schemas.CropEventOut])
async def get_timeline(
    planting_id: uuid.UUID,
    user: User = Depends(require_permission("crops.read")),
    db: AsyncSession = Depends(get_db),
):
    planting = await service.get_planting(db, planting_id, user.organization_id)
    return planting.events  # already ordered by event_at via relationship config


@router.get("/{planting_id}/harvests", response_model=list[schemas.HarvestRecordOut])
async def get_harvests(
    planting_id: uuid.UUID,
    user: User = Depends(require_permission("crops.read")),
    db: AsyncSession = Depends(get_db),
):
    planting = await service.get_planting(db, planting_id, user.organization_id)
    return service.compute_harvest_history_with_cumulative(planting.harvests)


@router.post("/{planting_id}/harvests", response_model=schemas.HarvestRecordOut, status_code=status.HTTP_201_CREATED)
async def add_harvest(
    planting_id: uuid.UUID,
    req: schemas.HarvestRecordCreate,
    user: User = Depends(require_permission("crops.harvest")),
    db: AsyncSession = Depends(get_db),
):
    planting = await service.get_planting(db, planting_id, user.organization_id)
    record = await service.record_harvest(db, planting, req, user.id)
    return schemas.HarvestRecordOut(
        id=record.id, quantity=record.quantity, unit=record.unit, quality_grade=record.quality_grade,
        harvested_at=record.harvested_at, recorded_by=record.recorded_by, notes=record.notes,
        cumulative_yield=None,
    )


@router.get("/{planting_id}/profitability", response_model=schemas.CropPlantingProfitability)
async def get_profitability(
    planting_id: uuid.UUID,
    user: User = Depends(require_permission("crops.read")),
    db: AsyncSession = Depends(get_db),
):
    planting = await service.get_planting(db, planting_id, user.organization_id)
    return service.compute_profitability(planting)


@router.get("/stats/summary")
async def crop_summary(
    user: User = Depends(require_permission("reports.view")),
    db: AsyncSession = Depends(get_db),
):
    """Backs dashboard-style 'Total Crops' cards, mirroring livestock's /stats/summary."""
    return await service.get_crop_summary(db, user.organization_id)
