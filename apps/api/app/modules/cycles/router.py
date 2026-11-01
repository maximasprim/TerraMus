import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.cycles import service, summary
from app.modules.cycles.deps import get_cycle
from app.modules.cycles.schemas import (AssignRequest, CycleClose, CycleCreate, CycleOut, CyclePreferences,
                                        CyclePreferencesOut, CycleUpdate)
from app.modules.identity.deps import require_permission
from app.modules.identity.models import User

router = APIRouter(prefix="/api/v1/production-cycles", tags=["production-cycles"])
READ = require_permission("cycles.read")
MANAGE = require_permission("cycles.manage")


@router.get("", response_model=list[CycleOut])
async def list_cycles(state: str | None = Query(None, pattern="^(planned|running|closed)$"),
                      enterprise: str | None = Query(None), user: User = Depends(READ), db: AsyncSession = Depends(get_db)):
    return await service.list_cycles(db, user.organization_id, state, enterprise)


@router.post("", response_model=CycleOut, status_code=201)
async def create_cycle(req: CycleCreate, user: User = Depends(MANAGE), db: AsyncSession = Depends(get_db)):
    return await service.create_cycle(db, user.organization_id, user.id, req)


@router.get("/preferences", response_model=CyclePreferencesOut)
async def get_preferences(user: User = Depends(READ), db: AsyncSession = Depends(get_db)):
    """Which cycle the console opens on for people who have not chosen one: 'all' (default) or 'running'."""
    return await service.get_preferences(db, user.organization_id)


@router.patch("/preferences", response_model=CyclePreferencesOut)
async def set_preferences(req: CyclePreferences, user: User = Depends(MANAGE), db: AsyncSession = Depends(get_db)):
    return await service.set_preferences(db, user.organization_id, req)


@router.get("/unassigned")
async def unassigned(user: User = Depends(READ), db: AsyncSession = Depends(get_db)):
    """How many existing records sit outside every cycle (what the assign tool can still adopt)."""
    return await service.unassigned_overview(db, user.organization_id)


@router.get("/compare")
async def compare(ids: str = Query(..., description="Comma-separated cycle ids (2 to 6)"), as_of: date | None = Query(None),
                  user: User = Depends(READ), db: AsyncSession = Depends(get_db)):
    try:
        uids = [uuid.UUID(i) for i in ids.split(",") if i.strip()]
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "ids must be comma-separated cycle ids")
    if not 2 <= len(uids) <= 6:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Pick between 2 and 6 cycles to compare")
    cycles = [await get_cycle(db, user.organization_id, i) for i in dict.fromkeys(uids)]
    return await summary.compare(db, user.organization_id, cycles, as_of)


@router.get("/{cycle_id}", response_model=CycleOut)
async def get_one(cycle_id: uuid.UUID, user: User = Depends(READ), db: AsyncSession = Depends(get_db)):
    return await service.cycle_out(db, user.organization_id, cycle_id)


@router.patch("/{cycle_id}", response_model=CycleOut)
async def update_cycle(cycle_id: uuid.UUID, req: CycleUpdate, user: User = Depends(MANAGE), db: AsyncSession = Depends(get_db)):
    return await service.update_cycle(db, user.organization_id, cycle_id, req)


@router.delete("/{cycle_id}", status_code=204)
async def delete_cycle(cycle_id: uuid.UUID, user: User = Depends(MANAGE), db: AsyncSession = Depends(get_db)):
    await service.delete_cycle(db, user.organization_id, cycle_id)


@router.post("/{cycle_id}/start", response_model=CycleOut)
async def start_cycle(cycle_id: uuid.UUID, user: User = Depends(MANAGE), db: AsyncSession = Depends(get_db)):
    return await service.start_cycle(db, user.organization_id, cycle_id)


@router.post("/{cycle_id}/close", response_model=CycleOut)
async def close_cycle(cycle_id: uuid.UUID, req: CycleClose, user: User = Depends(MANAGE), db: AsyncSession = Depends(get_db)):
    return await service.close_cycle(db, user.organization_id, user.id, cycle_id, req)


@router.post("/{cycle_id}/reopen", response_model=CycleOut)
async def reopen_cycle(cycle_id: uuid.UUID, user: User = Depends(MANAGE), db: AsyncSession = Depends(get_db)):
    return await service.reopen_cycle(db, user.organization_id, cycle_id)


@router.get("/{cycle_id}/summary")
async def cycle_summary(cycle_id: uuid.UUID, as_of: date | None = Query(None),
                        include_shared: bool = Query(False, description="Also estimate this cycle's share of untagged (shared) expenses"),
                        user: User = Depends(READ), db: AsyncSession = Depends(get_db)):
    c = await get_cycle(db, user.organization_id, cycle_id)
    return await summary.build_summary(db, user.organization_id, c, as_of, include_shared)


@router.post("/{cycle_id}/assign")
async def assign(cycle_id: uuid.UUID, req: AssignRequest, user: User = Depends(MANAGE), db: AsyncSession = Depends(get_db)):
    """Adopt existing records into this cycle. Preview first (dry_run is true by default)."""
    return await service.assign(db, user.organization_id, cycle_id, req)
