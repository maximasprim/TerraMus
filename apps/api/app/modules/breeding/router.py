import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.identity.deps import require_permission
from app.modules.identity.models import User
from app.modules.breeding import schemas, service

router = APIRouter(prefix="/api/v1/breeding", tags=["breeding"])
animal_breeding_router = APIRouter(prefix="/api/v1/livestock/{animal_id}/breeding", tags=["breeding"])


@router.post("", response_model=schemas.BreedingRecordOut, status_code=201)
async def create_breeding_record(
    req: schemas.BreedingRecordCreate,
    user: User = Depends(require_permission("breeding.create")),
    db: AsyncSession = Depends(get_db),
):
    return await service.create_breeding_record(db, user.organization_id, user.id, req)


@router.get("/{record_id}", response_model=schemas.BreedingRecordOut)
async def get_breeding_record(
    record_id: uuid.UUID,
    user: User = Depends(require_permission("breeding.read")),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_breeding_record(db, user.organization_id, record_id)


@router.post("/{record_id}/pregnancy-checks", response_model=schemas.BreedingRecordOut)
async def add_pregnancy_check(
    record_id: uuid.UUID,
    req: schemas.PregnancyCheckCreate,
    user: User = Depends(require_permission("breeding.create")),
    db: AsyncSession = Depends(get_db),
):
    return await service.add_pregnancy_check(db, user.organization_id, record_id, user.id, req)


@router.post("/{record_id}/delivery", response_model=schemas.BreedingRecordOut)
async def record_delivery(
    record_id: uuid.UUID,
    req: schemas.DeliveryRecord,
    user: User = Depends(require_permission("breeding.create")),
    db: AsyncSession = Depends(get_db),
):
    return await service.record_delivery(db, user.organization_id, record_id, user.id, req)


@router.get("/upcoming-deliveries", response_model=list[schemas.BreedingRecordOut])
async def upcoming_deliveries(
    within_days: int = Query(30, ge=1, le=365),
    user: User = Depends(require_permission("breeding.read")),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_upcoming_deliveries(db, user.organization_id, within_days)


@animal_breeding_router.get("", response_model=list[schemas.BreedingRecordOut])
async def list_animal_breeding_records(
    animal_id: uuid.UUID,
    user: User = Depends(require_permission("breeding.read")),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_breeding_records_for_animal(db, user.organization_id, animal_id)
