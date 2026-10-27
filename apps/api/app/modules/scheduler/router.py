from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.platform_admin.deps import get_current_platform_admin
from app.modules.scheduler.models import SchedulerRun

router = APIRouter(prefix="/api/v1/platform", tags=["platform-admin"])


@router.get("/scheduler-runs")
async def scheduler_runs(_admin=Depends(get_current_platform_admin), db: AsyncSession = Depends(get_db)):
    """Did this morning's checks run, and what did they do? (Platform admins only: the summary spans all farms.)"""
    rows = (await db.execute(select(SchedulerRun).order_by(SchedulerRun.run_date.desc()).limit(14))).scalars()
    return [{"job": r.job, "run_date": r.run_date.isoformat(), "status": r.status, "started_at": r.started_at.isoformat(),
             "finished_at": r.finished_at.isoformat() if r.finished_at else None, "summary": r.summary} for r in rows]
