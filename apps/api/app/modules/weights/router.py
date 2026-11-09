import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.cycles.deps import CycleSel, cycle_filter
from app.modules.identity.deps import require_permission
from app.modules.identity.models import User
from app.modules.weights import service

router = APIRouter(prefix="/api/v1/weights", tags=["weights"])


class TargetIn(BaseModel):
    target_weight_kg: Decimal | None = Field(default=None, gt=0, le=2000)   # null clears it


@router.get("/overview")
async def overview(batch_id: uuid.UUID | None = Query(None), user: User = Depends(require_permission("weights.view")),
                   db: AsyncSession = Depends(get_db), cycle: CycleSel | None = Depends(cycle_filter)):
    """Every animal still on the farm: latest weight, gain, target, readiness - plus a summary per batch."""
    return await service.overview(db, user.organization_id, batch_id, cycle)


@router.get("/daily")
async def daily(day: date | None = Query(None), user: User = Depends(require_permission("weights.view")),
                db: AsyncSession = Depends(get_db), cycle: CycleSel | None = Depends(cycle_filter)):
    """Weights recorded on one day (default: the latest weigh day), each compared with the animal's previous weighing."""
    return await service.daily(db, user.organization_id, day, cycle)


@router.get("/animals/{animal_id}")
async def animal_detail(animal_id: uuid.UUID, user: User = Depends(require_permission("weights.view")),
                        db: AsyncSession = Depends(get_db)):
    """One animal's weight history, gain per interval, projection to its target and its batch average."""
    return await service.animal_detail(db, user.organization_id, animal_id)


@router.put("/batches/{batch_id}/target")
async def set_batch_target(batch_id: uuid.UUID, req: TargetIn, user: User = Depends(require_permission("weights.targets")),
                           db: AsyncSession = Depends(get_db)):
    return await service.set_batch_target(db, user.organization_id, batch_id,
                                          float(req.target_weight_kg) if req.target_weight_kg else None)


@router.put("/animals/{animal_id}/target")
async def set_animal_target(animal_id: uuid.UUID, req: TargetIn, user: User = Depends(require_permission("weights.targets")),
                            db: AsyncSession = Depends(get_db)):
    return await service.set_animal_target(db, user.organization_id, animal_id,
                                           float(req.target_weight_kg) if req.target_weight_kg else None)
