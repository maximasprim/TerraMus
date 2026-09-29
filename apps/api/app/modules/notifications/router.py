import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.identity.deps import get_current_user, require_permission
from app.modules.identity.models import User
from app.modules.notifications import schemas, service
from app.modules.notifications.scheduled import run_scheduled_checks

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


@router.get("", response_model=list[schemas.NotificationOut])
async def list_notifications(
    unread_only: bool = Query(False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_notifications(db, user, unread_only)


@router.post("/{notification_id}/read", response_model=schemas.NotificationOut)
async def mark_read(
    notification_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.mark_read(db, user, notification_id)


@router.post("/read-all")
async def mark_all_read(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    count = await service.mark_all_read(db, user)
    return {"marked_read": count}


@router.put("/preferences")
async def set_preference(
    req: schemas.PreferenceUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    pref = await service.set_preference(db, user, req.category, req.enabled)
    return {"category": pref.category, "enabled": pref.enabled}


@router.post("/run-scheduled-checks", response_model=schemas.ScheduledChecksResult)
async def trigger_scheduled_checks(
    user: User = Depends(require_permission("farm.manage")),
    db: AsyncSession = Depends(get_db),
):
    """Stand-in for a real cron/Celery-beat trigger (see scheduled.py docstring)."""
    return await run_scheduled_checks(db, user.organization_id)


@router.get("/email-outbox", response_model=list[schemas.EmailOutboxOut])
async def list_email_outbox(
    user: User = Depends(require_permission("audit.view")),
    db: AsyncSession = Depends(get_db),
):
    """Spec §13/§55 - same permission as the audit log (both are
    'what actually happened' visibility, not a day-to-day operational
    permission most roles need)."""
    return await service.list_email_outbox(db, user.organization_id)
