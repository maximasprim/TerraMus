import uuid
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import publish
from app.modules.breeding.models import BreedingRecord, PregnancyCheck
from app.modules.breeding import schemas
from app.modules.livestock.service import get_animal, record_external_event
from app.modules.livestock import schemas as livestock_schemas
from app.modules.livestock.service import create_animal as create_livestock_animal

# Falls back to "young" (via .get() below) for any species not listed here,
# so adding a new species to livestock/catalog.py never breaks offspring
# creation - it just gets a generic category until this map is updated too.
CATEGORY_BY_SPECIES = {
    "cattle": "calf", "sheep": "lamb", "goat": "kid", "pig": "piglet",
    "rabbit": "kit", "poultry": "chick", "camel": "calf", "donkey": "foal",
}


async def create_breeding_record(
    db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID, req: schemas.BreedingRecordCreate,
) -> BreedingRecord:
    dam = await get_animal(db, req.dam_id, org_id)
    if dam.sex != "female":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "dam_id must reference a female animal")
    if req.sire_id:
        sire = await get_animal(db, req.sire_id, org_id)
        if sire.sex != "male":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "sire_id must reference a male animal")

    record = BreedingRecord(
        organization_id=org_id, recorded_by=user_id,
        **req.model_dump(),
    )
    db.add(record)
    await db.flush()

    await record_external_event(
        db, dam.id, "breeding:bred",
        data={"breeding_record_id": str(record.id), "method": req.method},
        recorded_by=user_id,
    )
    dam.reproductive_status = "bred"
    await db.commit()
    await db.refresh(record)
    return record


async def get_breeding_record(db: AsyncSession, org_id: uuid.UUID, record_id: uuid.UUID) -> BreedingRecord:
    result = await db.execute(
        select(BreedingRecord).where(BreedingRecord.id == record_id, BreedingRecord.organization_id == org_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Breeding record not found")
    return record


async def add_pregnancy_check(
    db: AsyncSession, org_id: uuid.UUID, record_id: uuid.UUID,
    user_id: uuid.UUID, req: schemas.PregnancyCheckCreate,
) -> BreedingRecord:
    record = await get_breeding_record(db, org_id, record_id)
    if record.pregnancy_status in ("delivered", "aborted"):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Breeding record is already '{record.pregnancy_status}'")

    check = PregnancyCheck(
        breeding_record_id=record.id, check_date=req.check_date,
        result=req.result, notes=req.notes, performed_by=user_id,
    )
    db.add(check)

    if req.result == "confirmed":
        record.pregnancy_status = "confirmed_pregnant"
    elif req.result == "not_pregnant":
        record.pregnancy_status = "not_pregnant"

    dam = await get_animal(db, record.dam_id, org_id)
    if req.result == "confirmed":
        dam.reproductive_status = "pregnant"
        await record_external_event(
            db, dam.id, "breeding:pregnancy_confirmed",
            data={"breeding_record_id": str(record.id)}, recorded_by=user_id,
            event_at=None,
        )
        await publish("PregnancyConfirmed", {
            "organization_id": str(org_id), "animal_id": str(dam.id),
            "expected_delivery_date": str(record.expected_delivery_date) if record.expected_delivery_date else None,
        })

    await db.commit()
    await db.refresh(record)
    return record


async def record_delivery(
    db: AsyncSession, org_id: uuid.UUID, record_id: uuid.UUID,
    user_id: uuid.UUID, req: schemas.DeliveryRecord,
) -> BreedingRecord:
    record = await get_breeding_record(db, org_id, record_id)
    if record.pregnancy_status == "delivered":
        raise HTTPException(status.HTTP_409_CONFLICT, "Delivery already recorded for this breeding record")
    if record.pregnancy_status in ("not_pregnant", "aborted"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot record delivery - breeding record is '{record.pregnancy_status}'",
        )

    dam = await get_animal(db, record.dam_id, org_id)

    record.actual_delivery_date = req.actual_delivery_date
    record.offspring_count = req.offspring_count
    record.pregnancy_status = "delivered"

    dam.reproductive_status = "lactating" if dam.species == "cattle" else "post_partum"
    await record_external_event(
        db, dam.id, "breeding:delivered",
        data={"breeding_record_id": str(record.id), "offspring_count": req.offspring_count},
        recorded_by=user_id,
        event_at=None,
    )
    await db.commit()
    await db.refresh(record)

    offspring_ids: list[str] = []
    if req.create_offspring_animals and req.offspring_count > 0:
        category = CATEGORY_BY_SPECIES.get(dam.species, "young")
        base_number = f"{dam.animal_number}-OFF"
        for i in range(req.offspring_count):
            sex = "female"
            if req.offspring_sex and i < len(req.offspring_sex):
                sex = req.offspring_sex[i]
            offspring = await create_livestock_animal(
                db, org_id, user_id,
                livestock_schemas.AnimalCreate(
                    farm_id=dam.farm_id,
                    location_id=dam.location_id,
                    dam_id=dam.id,
                    sire_id=record.sire_id,
                    animal_number=f"{base_number}-{i + 1}-{req.actual_delivery_date.isoformat()}",
                    species=dam.species,
                    category=category,
                    sex=sex,
                    date_of_birth=req.actual_delivery_date,
                    acquisition_date=req.actual_delivery_date,
                    acquisition_method="born_on_farm",
                    acquisition_cost=0,
                ),
            )
            offspring_ids.append(str(offspring.id))

    await publish("BirthRecorded", {
        "organization_id": str(org_id), "dam_id": str(dam.id),
        "breeding_record_id": str(record.id), "offspring_ids": offspring_ids,
    })
    return record


async def list_breeding_records_for_animal(
    db: AsyncSession, org_id: uuid.UUID, animal_id: uuid.UUID,
) -> list[BreedingRecord]:
    await get_animal(db, animal_id, org_id)
    result = await db.execute(
        select(BreedingRecord)
        .where(BreedingRecord.organization_id == org_id, BreedingRecord.dam_id == animal_id)
        .order_by(BreedingRecord.mating_date.desc())
    )
    return list(result.scalars().all())


async def list_upcoming_deliveries(db: AsyncSession, org_id: uuid.UUID, within_days: int = 30) -> list[BreedingRecord]:
    from datetime import timedelta
    horizon = date.today() + timedelta(days=within_days)
    result = await db.execute(
        select(BreedingRecord)
        .where(
            BreedingRecord.organization_id == org_id,
            BreedingRecord.pregnancy_status == "confirmed_pregnant",
            BreedingRecord.expected_delivery_date.is_not(None),
            BreedingRecord.expected_delivery_date <= horizon,
        )
        .order_by(BreedingRecord.expected_delivery_date.asc())
    )
    return list(result.scalars().all())
