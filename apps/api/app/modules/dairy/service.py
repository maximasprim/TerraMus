import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import publish
from app.modules.dairy.models import LactationCycle, MilkProductionRecord
from app.modules.dairy import schemas
from app.modules.livestock.service import get_animal

# Dairy goats are a well-established, profitable enterprise in the Kenyan
# market alongside dairy cattle, so this is intentionally widened from
# cattle-only to both - purely additive (no existing cattle-only lactation
# data or behavior changes).
DAIRY_SPECIES = ("cattle", "goat")

async def start_lactation_cycle(
    db: AsyncSession, org_id: uuid.UUID, animal_id: uuid.UUID, req: schemas.LactationCycleCreate,
) -> LactationCycle:
    animal = await get_animal(db, animal_id, org_id)
    if animal.species not in DAIRY_SPECIES or animal.sex != "female":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Lactation cycles apply to female animals (cattle or goats)")

    existing = await db.execute(
        select(LactationCycle).where(LactationCycle.animal_id == animal_id, LactationCycle.is_active.is_(True))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Animal already has an active lactation cycle")

    cycle = LactationCycle(organization_id=org_id, animal_id=animal_id, start_date=req.start_date, is_active=True)
    db.add(cycle)
    await db.commit()
    await db.refresh(cycle)
    return cycle


async def get_active_cycle(db: AsyncSession, org_id: uuid.UUID, animal_id: uuid.UUID) -> LactationCycle | None:
    result = await db.execute(
        select(LactationCycle).where(
            LactationCycle.organization_id == org_id,
            LactationCycle.animal_id == animal_id,
            LactationCycle.is_active.is_(True),
        )
    )
    return result.scalar_one_or_none()


async def dry_off(
    db: AsyncSession, org_id: uuid.UUID, animal_id: uuid.UUID, req: schemas.DryOffRequest,
) -> LactationCycle:
    cycle = await get_active_cycle(db, org_id, animal_id)
    if not cycle:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No active lactation cycle for this animal")
    cycle.end_date = req.end_date
    cycle.is_active = False
    await db.commit()
    await db.refresh(cycle)
    return cycle


async def record_milk(
    db: AsyncSession, org_id: uuid.UUID, animal_id: uuid.UUID,
    user_id: uuid.UUID, req: schemas.MilkRecordCreate,
) -> MilkProductionRecord:
    animal = await get_animal(db, animal_id, org_id)

    dup = await db.execute(
        select(MilkProductionRecord).where(
            MilkProductionRecord.animal_id == animal_id,
            MilkProductionRecord.production_date == req.production_date,
            MilkProductionRecord.session == req.session,
        )
    )
    if dup.scalar_one_or_none():
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"A {req.session} milk record already exists for this animal on {req.production_date}",
        )

    cycle = await get_active_cycle(db, org_id, animal_id)
    record = MilkProductionRecord(
        organization_id=org_id, animal_id=animal_id,
        lactation_cycle_id=cycle.id if cycle else None,
        production_date=req.production_date, session=req.session,
        quantity_liters=req.quantity_liters, rejected=req.rejected,
        rejection_reason=req.rejection_reason, recorded_by=user_id,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    await publish("MilkProductionRecorded", {
        "organization_id": str(org_id), "animal_id": str(animal_id),
        "quantity_liters": str(req.quantity_liters), "production_date": str(req.production_date),
    })
    return record


async def get_animal_production_history(
    db: AsyncSession, org_id: uuid.UUID, animal_id: uuid.UUID,
) -> list[MilkProductionRecord]:
    await get_animal(db, animal_id, org_id)
    result = await db.execute(
        select(MilkProductionRecord)
        .where(MilkProductionRecord.organization_id == org_id, MilkProductionRecord.animal_id == animal_id)
        .order_by(MilkProductionRecord.production_date.desc(), MilkProductionRecord.session)
    )
    return list(result.scalars().all())


async def herd_summary(db: AsyncSession, org_id: uuid.UUID, for_date: date | None = None) -> schemas.HerdMilkSummary:
    """Backs 'today's total milk' / 'average milk/cow' / 'top producing cows' (spec §12)."""
    target_date = for_date or date.today()

    rows = await db.execute(
        select(MilkProductionRecord.animal_id, func.sum(MilkProductionRecord.quantity_liters))
        .where(
            MilkProductionRecord.organization_id == org_id,
            MilkProductionRecord.production_date == target_date,
            MilkProductionRecord.rejected.is_(False),
        )
        .group_by(MilkProductionRecord.animal_id)
    )
    per_animal = rows.all()
    total = sum((qty for _, qty in per_animal), Decimal("0"))
    cows_milked = len(per_animal)
    average = (total / cows_milked) if cows_milked else Decimal("0")
    top = sorted(per_animal, key=lambda r: r[1], reverse=True)[:5]

    return schemas.HerdMilkSummary(
        date=target_date,
        total_liters=total,
        average_per_cow=round(average, 2),
        cows_milked=cows_milked,
        top_producers=[{"animal_id": str(a), "quantity_liters": str(q)} for a, q in top],
    )
