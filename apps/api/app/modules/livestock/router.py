import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.identity.deps import require_permission
from app.modules.identity.models import User
from app.modules.farm.models import Farm, Location
from app.modules.livestock import schemas, service
from app.modules.livestock.models import Animal, INACTIVE_STATUSES

router = APIRouter(prefix="/api/v1/livestock", tags=["livestock"])


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


@router.get("", response_model=list[schemas.AnimalOut])
async def list_animals(
    user: User = Depends(require_permission("livestock.read")),
    db: AsyncSession = Depends(get_db),
    species: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    farm_id: uuid.UUID | None = Query(None),
    active_only: bool = Query(False, description="Exclude sold/transferred/deceased/archived animals"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    query = select(Animal).where(Animal.organization_id == user.organization_id)
    if species:
        query = query.where(Animal.species == species)
    if status_filter:
        query = query.where(Animal.status == status_filter)
    if farm_id:
        query = query.where(Animal.farm_id == farm_id)
    if active_only:
        query = query.where(Animal.status.notin_(INACTIVE_STATUSES))
    query = query.order_by(Animal.created_at.desc(), Animal.id).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("", response_model=schemas.AnimalOut, status_code=status.HTTP_201_CREATED)
async def create_animal(
    req: schemas.AnimalCreate,
    user: User = Depends(require_permission("livestock.create")),
    db: AsyncSession = Depends(get_db),
):
    await _assert_farm_and_location_belong_to_org(db, user.organization_id, req.farm_id, req.location_id)
    return await service.create_animal(db, user.organization_id, user.id, req)


@router.get("/{animal_id}", response_model=schemas.AnimalOut)
async def get_animal(
    animal_id: uuid.UUID,
    user: User = Depends(require_permission("livestock.read")),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_animal(db, animal_id, user.organization_id)


@router.get("/{animal_id}/qrcode.svg")
async def get_animal_qrcode(
    animal_id: uuid.UUID,
    user: User = Depends(require_permission("livestock.read")),
    db: AsyncSession = Depends(get_db),
):
    """Spec §38."""
    from fastapi.responses import Response
    svg_bytes = await service.get_animal_qr_svg(db, user.organization_id, animal_id)
    return Response(content=svg_bytes, media_type="image/svg+xml")


@router.patch("/{animal_id}", response_model=schemas.AnimalOut)
async def update_animal(
    animal_id: uuid.UUID,
    req: schemas.AnimalUpdate,
    user: User = Depends(require_permission("livestock.update")),
    db: AsyncSession = Depends(get_db),
):
    animal = await service.get_animal(db, animal_id, user.organization_id)
    if req.location_id is not None:
        await _assert_farm_and_location_belong_to_org(db, user.organization_id, animal.farm_id, req.location_id)
    return await service.update_animal(db, animal, req, user.id)


@router.post("/{animal_id}/status", response_model=schemas.AnimalOut)
async def change_status(
    animal_id: uuid.UUID,
    req: schemas.StatusChangeRequest,
    user: User = Depends(require_permission("livestock.update")),
    db: AsyncSession = Depends(get_db),
):
    animal = await service.get_animal(db, animal_id, user.organization_id)
    # Selling specifically requires the finer-grained livestock.sell permission (spec §5).
    if req.status == "sold":
        from app.modules.identity.service import get_user_permissions
        perms = await get_user_permissions(db, user)
        if "livestock.sell" not in perms:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing required permission: livestock.sell")
    return await service.change_status(db, animal, req, user.id)


@router.get("/{animal_id}/timeline", response_model=list[schemas.AnimalEventOut])
async def get_timeline(
    animal_id: uuid.UUID,
    user: User = Depends(require_permission("livestock.read")),
    db: AsyncSession = Depends(get_db),
):
    animal = await service.get_animal(db, animal_id, user.organization_id)
    return animal.events  # already ordered by event_at via relationship config


@router.get("/{animal_id}/weights", response_model=list[schemas.WeightRecordOut])
async def get_weights(
    animal_id: uuid.UUID,
    user: User = Depends(require_permission("livestock.read")),
    db: AsyncSession = Depends(get_db),
):
    animal = await service.get_animal(db, animal_id, user.organization_id)
    return service.compute_weight_history_with_adg(animal.weights)


@router.post("/{animal_id}/weights", response_model=schemas.WeightRecordOut, status_code=status.HTTP_201_CREATED)
async def add_weight(
    animal_id: uuid.UUID,
    req: schemas.WeightRecordCreate,
    user: User = Depends(require_permission("livestock.update")),
    db: AsyncSession = Depends(get_db),
):
    animal = await service.get_animal(db, animal_id, user.organization_id)
    record = await service.record_weight(db, animal, req, user.id)
    return schemas.WeightRecordOut(
        id=record.id, weight_kg=record.weight_kg, recorded_at=record.recorded_at,
        recorded_by=record.recorded_by, notes=record.notes, average_daily_gain=None,
    )


@router.post("/{animal_id}/movements", response_model=schemas.MovementOut, status_code=status.HTTP_201_CREATED)
async def move_animal(
    animal_id: uuid.UUID,
    req: schemas.MovementCreate,
    user: User = Depends(require_permission("livestock.update")),
    db: AsyncSession = Depends(get_db),
):
    animal = await service.get_animal(db, animal_id, user.organization_id)
    await _assert_farm_and_location_belong_to_org(db, user.organization_id, animal.farm_id, req.to_location_id)
    return await service.move_animal(db, animal, req, user.id)


@router.get("/{animal_id}/movements", response_model=list[schemas.MovementOut])
async def list_movements(
    animal_id: uuid.UUID,
    user: User = Depends(require_permission("livestock.read")),
    db: AsyncSession = Depends(get_db),
):
    animal = await service.get_animal(db, animal_id, user.organization_id)
    return animal.movements


@router.get("/{animal_id}/profitability", response_model=schemas.AnimalProfitability)
async def get_profitability(
    animal_id: uuid.UUID,
    user: User = Depends(require_permission("livestock.read")),
    db: AsyncSession = Depends(get_db),
):
    animal = await service.get_animal(db, animal_id, user.organization_id)
    return service.compute_profitability(animal)


@router.get("/stats/summary")
async def herd_summary(
    user: User = Depends(require_permission("reports.view")),
    db: AsyncSession = Depends(get_db),
):
    """Backs the dashboard 'Total Herd' style cards (spec §24/§68) - Phase 2 slice."""
    return await service.get_herd_summary(db, user.organization_id)
