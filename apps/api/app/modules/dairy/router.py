import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.identity.deps import require_permission
from app.modules.identity.models import User
from app.modules.dairy import schemas, service

router = APIRouter(prefix="/api/v1/livestock/{animal_id}/dairy", tags=["dairy"])
herd_router = APIRouter(prefix="/api/v1/dairy", tags=["dairy"])


@router.post("/lactation-cycles", response_model=schemas.LactationCycleOut, status_code=201)
async def start_lactation_cycle(
    animal_id: uuid.UUID, req: schemas.LactationCycleCreate,
    user: User = Depends(require_permission("dairy.create")),
    db: AsyncSession = Depends(get_db),
):
    return await service.start_lactation_cycle(db, user.organization_id, animal_id, req)


@router.post("/lactation-cycles/dry-off", response_model=schemas.LactationCycleOut)
async def dry_off(
    animal_id: uuid.UUID, req: schemas.DryOffRequest,
    user: User = Depends(require_permission("dairy.create")),
    db: AsyncSession = Depends(get_db),
):
    return await service.dry_off(db, user.organization_id, animal_id, req)


@router.post("/milk", response_model=schemas.MilkRecordOut, status_code=201)
async def record_milk(
    animal_id: uuid.UUID, req: schemas.MilkRecordCreate,
    user: User = Depends(require_permission("dairy.create")),
    db: AsyncSession = Depends(get_db),
):
    return await service.record_milk(db, user.organization_id, animal_id, user.id, req)


@router.get("/milk", response_model=list[schemas.MilkRecordOut])
async def production_history(
    animal_id: uuid.UUID,
    user: User = Depends(require_permission("dairy.read")),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_animal_production_history(db, user.organization_id, animal_id)


@herd_router.get("/summary", response_model=schemas.HerdMilkSummary)
async def herd_summary(
    for_date: date | None = Query(None),
    user: User = Depends(require_permission("dairy.read")),
    db: AsyncSession = Depends(get_db),
):
    return await service.herd_summary(db, user.organization_id, for_date)
