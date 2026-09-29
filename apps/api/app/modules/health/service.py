import uuid
from datetime import date, datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import publish
from app.modules.health.models import HealthRecord
from app.modules.health import schemas
from app.modules.livestock.service import get_animal, record_external_event


async def create_health_record(
    db: AsyncSession, org_id: uuid.UUID, animal_id: uuid.UUID,
    user_id: uuid.UUID, req: schemas.HealthRecordCreate,
) -> HealthRecord:
    animal = await get_animal(db, animal_id, org_id)  # 404s + tenant-scopes if missing

    performed_at = req.performed_at or datetime.now(timezone.utc)
    record = HealthRecord(
        organization_id=org_id,
        animal_id=animal.id,
        record_type=req.record_type,
        title=req.title,
        description=req.description,
        diagnosis=req.diagnosis,
        medication=req.medication,
        dosage=req.dosage,
        administered_by=req.administered_by,
        cost=req.cost,
        performed_at=performed_at,
        follow_up_date=req.follow_up_date,
        recorded_by=user_id,
    )
    db.add(record)
    await db.flush()

    # Shared-kernel write into the same transaction (see livestock/service.py
    # record_external_event docstring) - keeps the animal's timeline consistent
    # with the health record that produced this entry.
    await record_external_event(
        db, animal.id, f"health:{req.record_type}",
        data={"title": req.title, "health_record_id": str(record.id)},
        recorded_by=user_id, event_at=performed_at,
    )

    if animal.health_status == "healthy" and req.record_type in ("injury", "treatment"):
        animal.health_status = "under_treatment"

    await db.commit()
    await db.refresh(record)

    await publish("HealthRecordCreated", {
        "organization_id": str(org_id), "animal_id": str(animal.id), "health_record_id": str(record.id),
        "record_type": req.record_type, "cost": str(req.cost) if req.cost is not None else None,
        "follow_up_date": str(req.follow_up_date) if req.follow_up_date else None,
    })
    if req.follow_up_date:
        await publish("VaccinationDue" if req.record_type == "vaccination" else "HealthFollowUpDue", {
            "organization_id": str(org_id), "animal_id": str(animal.id), "due_date": str(req.follow_up_date),
        })
    return record


async def list_health_records(db: AsyncSession, org_id: uuid.UUID, animal_id: uuid.UUID) -> list[HealthRecord]:
    await get_animal(db, animal_id, org_id)  # tenant + existence check
    result = await db.execute(
        select(HealthRecord)
        .where(HealthRecord.animal_id == animal_id, HealthRecord.organization_id == org_id)
        .order_by(HealthRecord.performed_at.desc())
    )
    return list(result.scalars().all())


async def complete_follow_up(
    db: AsyncSession, org_id: uuid.UUID, record_id: uuid.UUID, user_id: uuid.UUID,
) -> HealthRecord:
    result = await db.execute(
        select(HealthRecord).where(HealthRecord.id == record_id, HealthRecord.organization_id == org_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Health record not found")
    if not record.follow_up_date:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This record has no follow-up to complete")
    record.follow_up_completed = True
    await record_external_event(
        db, record.animal_id, "health:follow_up_completed",
        data={"health_record_id": str(record.id)}, recorded_by=user_id,
    )
    await db.commit()
    await db.refresh(record)
    return record


async def get_total_health_cost_for_animal(db: AsyncSession, org_id: uuid.UUID, animal_id: uuid.UUID) -> "Decimal":
    """Spec §25 - feeds into the cross-module profitability report
    (reporting/service.py), mirroring inventory.service.feed_cost_for_animal."""
    from decimal import Decimal
    result = await db.execute(
        select(func.coalesce(func.sum(HealthRecord.cost), 0)).where(
            HealthRecord.organization_id == org_id,
            HealthRecord.animal_id == animal_id,
            HealthRecord.cost.is_not(None),
        )
    )
    return Decimal(result.scalar_one())


async def list_due_follow_ups(
    db: AsyncSession, org_id: uuid.UUID, within_days: int = 14,
) -> list[schemas.DueFollowUpOut]:
    """Backs 'which vaccinations are due' / 'which animals need medical attention'
    (spec §Product Vision). Includes overdue + upcoming-within-window, excluding
    anything already marked complete."""
    from datetime import timedelta
    horizon = date.today() + timedelta(days=within_days)
    result = await db.execute(
        select(HealthRecord)
        .where(
            HealthRecord.organization_id == org_id,
            HealthRecord.follow_up_date.is_not(None),
            HealthRecord.follow_up_date <= horizon,
            HealthRecord.follow_up_completed.is_(False),
        )
        .order_by(HealthRecord.follow_up_date.asc())
    )
    today = date.today()
    return [
        schemas.DueFollowUpOut(
            id=r.id, animal_id=r.animal_id, record_type=r.record_type,
            title=r.title, follow_up_date=r.follow_up_date,
            is_overdue=r.follow_up_date < today,
        )
        for r in result.scalars().all()
    ]
