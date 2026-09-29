import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import publish
from app.modules.crops.models import CropPlanting, CropEvent, HarvestRecord, INACTIVE_PLANTING_STATUSES
from app.modules.crops import schemas
from app.modules.crops.catalog import CROP_TYPE_LOOKUP

# Allowed status transitions, mirroring livestock/service.py's
# _ALLOWED_TRANSITIONS. "growing" is the entry state for every new planting.
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "growing": {"ready_for_harvest", "harvesting", "fallow", "failed", "archived"},
    "ready_for_harvest": {"harvesting", "growing", "failed", "archived"},
    "harvesting": {"harvested", "ready_for_harvest", "growing", "failed", "archived"},
    "harvested": {"fallow", "growing", "archived"},  # a perennial planting can cycle back to "growing"
    "fallow": {"growing", "archived"},
    "failed": set(),      # terminal
    "archived": set(),    # terminal
}


async def _record_event(
    db: AsyncSession, planting_id: uuid.UUID, event_type: str,
    data: dict | None = None, recorded_by: uuid.UUID | None = None,
    event_at: datetime | None = None,
) -> CropEvent:
    event = CropEvent(
        planting_id=planting_id,
        event_type=event_type,
        event_at=event_at or datetime.now(timezone.utc),
        data=data,
        recorded_by=recorded_by,
    )
    db.add(event)
    return event


async def get_planting(db: AsyncSession, planting_id: uuid.UUID, org_id: uuid.UUID) -> CropPlanting:
    result = await db.execute(
        select(CropPlanting).where(CropPlanting.id == planting_id, CropPlanting.organization_id == org_id)
    )
    planting = result.scalar_one_or_none()
    if not planting:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Crop planting not found")
    return planting


async def create_planting(
    db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID, req: schemas.CropPlantingCreate,
) -> CropPlanting:
    from app.modules.catalog.service import is_crop_type_allowed

    if not await is_crop_type_allowed(db, org_id, req.crop_type):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Crop type '{req.crop_type}' is not enabled for this organization. "
            "Contact your platform administrator to have it enabled.",
        )

    data = req.model_dump()
    # is_perennial defaults from the catalog if the caller didn't explicitly
    # override it, so the frontend doesn't have to hardcode which crop types
    # are bearing/perennial - that's already known in crops/catalog.py.
    if not data.get("is_perennial"):
        catalog_entry = CROP_TYPE_LOOKUP.get(req.crop_type)
        if catalog_entry:
            data["is_perennial"] = catalog_entry["is_perennial"]

    planting = CropPlanting(organization_id=org_id, status="growing", health_status="healthy", **data)
    db.add(planting)
    await db.flush()  # obtain planting.id before recording the event

    await _record_event(
        db, planting.id, "planted",
        data={"crop_type": req.crop_type, "planting_method": req.planting_method,
              "acquisition_cost": str(req.acquisition_cost)},
        recorded_by=user_id,
        event_at=datetime.combine(req.planting_date, datetime.min.time(), tzinfo=timezone.utc),
    )
    await db.commit()
    await db.refresh(planting)

    await publish("CropPlanted", {
        "organization_id": str(org_id),
        "planting_id": str(planting.id),
        "crop_type": req.crop_type,
        "acquisition_cost": str(req.acquisition_cost),
    })
    return planting


async def update_planting(
    db: AsyncSession, planting: CropPlanting, req: schemas.CropPlantingUpdate, user_id: uuid.UUID,
) -> CropPlanting:
    changes = req.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(planting, field, value)
    if changes:
        await _record_event(db, planting.id, "updated", data={"fields": list(changes.keys())}, recorded_by=user_id)
    await db.commit()
    await db.refresh(planting)
    return planting


async def change_status(
    db: AsyncSession, planting: CropPlanting, req: schemas.StatusChangeRequest, user_id: uuid.UUID,
) -> CropPlanting:
    allowed = _ALLOWED_TRANSITIONS.get(planting.status, set())
    if req.status == planting.status:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Planting is already in that status")
    if req.status not in allowed:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot transition planting from '{planting.status}' to '{req.status}'",
        )

    previous_status = planting.status
    planting.status = req.status
    await _record_event(
        db, planting.id, f"status_changed:{req.status}",
        data={"from": previous_status, "to": req.status, "reason": req.reason},
        recorded_by=user_id,
    )
    await db.commit()
    await db.refresh(planting)

    if req.status == "failed":
        await publish("CropFailed", {"planting_id": str(planting.id), "organization_id": str(planting.organization_id)})
    return planting


async def record_harvest(
    db: AsyncSession, planting: CropPlanting, req: schemas.HarvestRecordCreate, user_id: uuid.UUID,
) -> HarvestRecord:
    harvested_at = req.harvested_at or datetime.now(timezone.utc)
    record = HarvestRecord(
        planting_id=planting.id, quantity=req.quantity, unit=req.unit,
        quality_grade=req.quality_grade, harvested_at=harvested_at,
        recorded_by=user_id, notes=req.notes,
    )
    db.add(record)
    await _record_event(
        db, planting.id, "harvested", data={"quantity": str(req.quantity), "unit": req.unit},
        recorded_by=user_id, event_at=harvested_at,
    )
    await db.commit()
    await db.refresh(record)
    await publish("CropHarvested", {
        "planting_id": str(planting.id), "quantity": str(req.quantity), "unit": req.unit,
    })
    return record


def compute_harvest_history_with_cumulative(harvests: list[HarvestRecord]) -> list[schemas.HarvestRecordOut]:
    """Running total harvested to date, mirroring livestock's ADG computation
    - useful for perennial crops (tea, avocado) harvested many times."""
    ordered = sorted(harvests, key=lambda h: h.harvested_at)
    results: list[schemas.HarvestRecordOut] = []
    running_total = Decimal("0")
    for h in ordered:
        running_total += Decimal(h.quantity)
        results.append(schemas.HarvestRecordOut(
            id=h.id, quantity=h.quantity, unit=h.unit, quality_grade=h.quality_grade,
            harvested_at=h.harvested_at, recorded_by=h.recorded_by, notes=h.notes,
            cumulative_yield=running_total,
        ))
    return list(reversed(results))  # most recent first


def compute_profitability(planting: CropPlanting) -> schemas.CropPlantingProfitability:
    acquisition = Decimal(planting.acquisition_cost)
    total = acquisition  # + input_cost + labor_cost + other_cost (later phases)
    total_harvested_value = None  # requires per-unit pricing, not tracked yet - explicit None, not silently omitted
    return schemas.CropPlantingProfitability(
        planting_id=planting.id,
        acquisition_cost=acquisition,
        total_investment=total,
        total_harvested_value=total_harvested_value,
        current_value=planting.current_value,
    )


async def get_crop_summary(db: AsyncSession, org_id: uuid.UUID) -> dict:
    """Backs dashboard-style cards, mirroring livestock.service.get_herd_summary."""
    base = select(func.count(CropPlanting.id)).where(CropPlanting.organization_id == org_id)
    total = (await db.execute(base)).scalar_one()
    active = (await db.execute(base.where(CropPlanting.status.notin_(INACTIVE_PLANTING_STATUSES)))).scalar_one()
    by_crop_type_rows = await db.execute(
        select(CropPlanting.crop_type, func.count(CropPlanting.id))
        .where(CropPlanting.organization_id == org_id, CropPlanting.status.notin_(INACTIVE_PLANTING_STATUSES))
        .group_by(CropPlanting.crop_type)
    )
    total_area_row = await db.execute(
        select(func.coalesce(func.sum(CropPlanting.area_size), 0)).where(
            CropPlanting.organization_id == org_id, CropPlanting.status.notin_(INACTIVE_PLANTING_STATUSES),
        )
    )
    planting_value_row = await db.execute(
        select(func.coalesce(func.sum(CropPlanting.current_value), 0)).where(
            CropPlanting.organization_id == org_id, CropPlanting.status.notin_(INACTIVE_PLANTING_STATUSES),
        )
    )
    return {
        "total_plantings": total,
        "active_plantings": active,
        "by_crop_type": dict(by_crop_type_rows.all()),
        "total_area": total_area_row.scalar_one(),
        "total_planting_value": planting_value_row.scalar_one(),
    }
