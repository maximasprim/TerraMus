"""In-process schedulers (no cron/Celery in this deployment).

* daily_checks_loop  - once a day after SCHEDULER_RUN_HOUR (Nairobi time) runs every organisation's alert checks.
* payment_reconcile_loop - every few minutes asks M-Pesa about prompts whose callback never arrived.

Safe with several server replicas and with restarts:
  - the (job, run_date) row in scheduler_runs is the lock: the replica that inserts it runs the job, the others skip;
  - the loop POLLS (every 5 min) rather than sleeping until 06:00, so a server that was down at 06:00 still runs the
    checks when it comes back up that day;
  - a run that died half-way ('running' for 2h+) can be taken over, so one crash cannot cancel a day's alerts;
  - each organisation runs in its own session and its own try/except: one farm's error never blocks the others."""
import asyncio
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.modules.scheduler.models import SchedulerRun

logger = logging.getLogger("app.scheduler")
settings = get_settings()
JOB_DAILY = "daily_checks"
STALE_AFTER = timedelta(hours=2)


def local_now() -> datetime:
    return datetime.now(ZoneInfo(settings.DEFAULT_TIMEZONE))


def should_run_now(local: datetime, run_hour: int) -> bool:
    return local.hour >= run_hour


async def claim_run(db, job: str, run_date: date, now: datetime | None = None) -> uuid.UUID | None:
    """Try to become the runner of `job` for `run_date`. None = someone else has it (or already did it)."""
    now = now or datetime.now(timezone.utc)
    run = SchedulerRun(job=job, run_date=run_date, started_at=now, status="running")
    db.add(run)
    try:
        await db.commit()
        return run.id
    except IntegrityError:
        await db.rollback()
    taken = await db.execute(update(SchedulerRun).where(
        SchedulerRun.job == job, SchedulerRun.run_date == run_date, SchedulerRun.status == "running",
        SchedulerRun.started_at < now - STALE_AFTER).values(started_at=now).returning(SchedulerRun.id))
    row = taken.first()
    await db.commit()
    return row[0] if row else None


async def finish_run(db, run_id: uuid.UUID, status: str, summary: dict) -> None:
    await db.execute(update(SchedulerRun).where(SchedulerRun.id == run_id).values(
        status=status, summary=summary, finished_at=datetime.now(timezone.utc)))
    await db.commit()


async def run_daily_checks_for_all_orgs(session_factory, today: date) -> tuple[str, dict]:
    from app.modules.identity.models import Organization
    from app.modules.notifications.scheduled import run_scheduled_checks
    async with session_factory() as db:
        org_ids = list((await db.execute(select(Organization.id).where(Organization.is_suspended.is_(False)))).scalars())
    totals: dict[str, int] = {}
    ok = failed = 0
    for org_id in org_ids:
        try:
            async with session_factory() as db:
                result = await run_scheduled_checks(db, org_id, today)
            for k, v in result.model_dump().items():
                totals[k] = totals.get(k, 0) + v
            ok += 1
        except Exception:  # noqa: BLE001 - isolate the failing organisation
            failed += 1
            logger.exception("daily checks failed for organisation %s", org_id)
    status = "ok" if failed == 0 else ("partial" if ok else "failed")
    return status, {"organisations": len(org_ids), "succeeded": ok, "failed": failed, **totals}


async def run_daily_once(session_factory, now_local: datetime | None = None) -> dict | None:
    """One poll of the daily job. Returns the summary if THIS call ran it, else None."""
    now_local = now_local or local_now()
    if not should_run_now(now_local, settings.SCHEDULER_RUN_HOUR):
        return None
    async with session_factory() as db:
        run_id = await claim_run(db, JOB_DAILY, now_local.date())
    if not run_id:
        return None
    status, summary = await run_daily_checks_for_all_orgs(session_factory, now_local.date())
    async with session_factory() as db:
        await finish_run(db, run_id, status, summary)
    logger.info("daily checks %s: %s", status, summary)
    return summary


async def daily_checks_loop(session_factory, poll_seconds: int = 300) -> None:
    while True:
        try:
            await run_daily_once(session_factory)
        except Exception:  # noqa: BLE001
            logger.exception("daily checks loop error")
        await asyncio.sleep(poll_seconds)


async def payment_reconcile_loop(session_factory) -> None:
    from app.modules.payments.service import reconcile_pending
    while True:
        await asyncio.sleep(settings.PAYMENT_RECONCILE_INTERVAL_SECONDS)
        try:
            async with session_factory() as db:
                out = await reconcile_pending(db, "mpesa")
            if out["checked"]:
                logger.info("payment reconciliation: %s", out)
        except Exception:  # noqa: BLE001
            logger.exception("payment reconciliation failed")
