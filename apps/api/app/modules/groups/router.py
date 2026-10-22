import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.groups import schemas, service
from app.modules.identity.deps import require_permission
from app.modules.identity.models import User

router = APIRouter(prefix="/api/v1/groups", tags=["groups"])


@router.get("")
async def list_groups(species: str | None = Query(None, pattern="^(poultry|rabbits|fish|pigs|other)$"), state: str | None = Query(None, pattern="^(active|closed)$"),
                      user: User = Depends(require_permission("groups.read")), db: AsyncSession = Depends(get_db)):
    return await service.list_groups(db, user.organization_id, species, state)


@router.post("", status_code=201)
async def create_group(req: schemas.GroupCreate, user: User = Depends(require_permission("groups.manage")), db: AsyncSession = Depends(get_db)):
    return await service.create_group(db, user.organization_id, req)


@router.get("/{group_id}/performance")
async def performance(group_id: uuid.UUID, as_of: date | None = Query(None), user: User = Depends(require_permission("groups.read")), db: AsyncSession = Depends(get_db)):
    return await service.performance(db, user.organization_id, group_id, as_of)


@router.get("/{group_id}/records")
async def records(group_id: uuid.UUID, record_type: str | None = Query(None), start_date: date | None = Query(None), end_date: date | None = Query(None),
                  user: User = Depends(require_permission("groups.read")), db: AsyncSession = Depends(get_db)):
    return await service.list_records(db, user.organization_id, group_id, record_type, start_date, end_date)


@router.post("/{group_id}/records", status_code=201)
async def add_record(group_id: uuid.UUID, req: schemas.RecordCreate, user: User = Depends(require_permission("groups.record")), db: AsyncSession = Depends(get_db)):
    return await service.add_record(db, user.organization_id, user.id, group_id, req)


@router.post("/{group_id}/close")
async def close_group(group_id: uuid.UUID, req: schemas.GroupClose, user: User = Depends(require_permission("groups.manage")), db: AsyncSession = Depends(get_db)):
    return await service.close_group(db, user.organization_id, group_id, req)
