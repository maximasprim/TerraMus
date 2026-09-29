import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.identity.deps import require_permission
from app.modules.identity.models import User
from app.modules.health import schemas, service

# Nested under /livestock/{animal_id}/health to match the API pattern from
# spec §40 (GET /api/v1/livestock/{id}/health), plus an org-wide /health/due.
animal_health_router = APIRouter(prefix="/api/v1/livestock/{animal_id}/health", tags=["health"])
health_router = APIRouter(prefix="/api/v1/health", tags=["health"])


@animal_health_router.get("", response_model=list[schemas.HealthRecordOut])
async def list_health_records(
    animal_id: uuid.UUID,
    user: User = Depends(require_permission("health.read")),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_health_records(db, user.organization_id, animal_id)


@animal_health_router.post("", response_model=schemas.HealthRecordOut, status_code=201)
async def create_health_record(
    animal_id: uuid.UUID,
    req: schemas.HealthRecordCreate,
    user: User = Depends(require_permission("health.create")),
    db: AsyncSession = Depends(get_db),
):
    return await service.create_health_record(db, user.organization_id, animal_id, user.id, req)


@health_router.get("/due", response_model=list[schemas.DueFollowUpOut])
async def due_follow_ups(
    within_days: int = Query(14, ge=1, le=365),
    user: User = Depends(require_permission("health.read")),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_due_follow_ups(db, user.organization_id, within_days)


@health_router.post("/records/{record_id}/complete-follow-up", response_model=schemas.HealthRecordOut)
async def complete_follow_up(
    record_id: uuid.UUID,
    user: User = Depends(require_permission("health.create")),
    db: AsyncSession = Depends(get_db),
):
    return await service.complete_follow_up(db, user.organization_id, record_id, user.id)
