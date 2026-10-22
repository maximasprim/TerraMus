import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import publish
from app.modules.livestock.models import Animal, AnimalEvent, WeightRecord, Movement, INACTIVE_STATUSES
from app.modules.livestock import schemas


# Allowed status transitions (spec §52.1/§52.2: sold/reserved animals guarded).
# Anything not listed as a source key is terminal or has no outbound transitions
# defined yet beyond returning to 'active' (e.g. un-reserving).
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "active": {"for_sale", "quarantined", "missing", "deceased", "transferred", "archived", "culled"},
    "quarantined": {"active", "deceased", "missing", "culled"},
    "for_sale": {"reserved", "active", "sold", "deceased", "missing", "culled"},
    "reserved": {"sold", "for_sale", "deceased"},
    "sold": set(),          # terminal - spec §52.1: sold livestock cannot be sold again
    "transferred": set(),   # terminal
    "deceased": set(),      # terminal
    "missing": {"active", "deceased"},
    "archived": set(),      # terminal
    "culled": set(),        # terminal (removed from the herd as unfit; no sale revenue)
}


async def record_external_event(
    db: AsyncSession, animal_id: uuid.UUID, event_type: str,
    data: dict | None = None, recorded_by: uuid.UUID | None = None,
    event_at: datetime | None = None,
) -> AnimalEvent:
    """Public seam for other bounded contexts (Health, Breeding, Dairy) to append
    to an animal's immutable timeline within the *same* DB transaction - the
    timeline needs strong consistency with the record that caused it, which the
    async event bus (core/events.py, fire-and-forget) intentionally does not
    guarantee. This is a deliberate, narrow shared-kernel exception (spec §31
    otherwise keeps modules decoupled); callers still own their own commit."""
    return await _record_event(db, animal_id, event_type, data, recorded_by, event_at)


async def _record_event(
    db: AsyncSession, animal_id: uuid.UUID, event_type: str,
    data: dict | None = None, recorded_by: uuid.UUID | None = None,
    event_at: datetime | None = None,
) -> AnimalEvent:
    event = AnimalEvent(
        animal_id=animal_id,
        event_type=event_type,
        event_at=event_at or datetime.now(timezone.utc),
        data=data,
        recorded_by=recorded_by,
    )
    db.add(event)
    return event


async def get_animal(db: AsyncSession, animal_id: uuid.UUID, org_id: uuid.UUID) -> Animal:
    result = await db.execute(
        select(Animal).where(Animal.id == animal_id, Animal.organization_id == org_id)
    )
    animal = result.scalar_one_or_none()
    if not animal:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Animal not found")
    return animal


async def create_animal(
    db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID, req: schemas.AnimalCreate,
) -> Animal:
    from app.modules.billing.service import check_animal_limit
    await check_animal_limit(db, org_id)

    from app.modules.catalog.service import is_species_allowed
    if not await is_species_allowed(db, org_id, req.species):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Species '{req.species}' is not enabled for this organization. "
            "Contact your platform administrator to have it enabled.",
        )

    animal = Animal(
        organization_id=org_id,
        status="active",
        health_status="healthy",
        **req.model_dump(),
    )
    db.add(animal)
    await db.flush()  # obtain animal.id before recording the event

    await _record_event(
        db, animal.id, "acquired",
        data={
            "acquisition_method": req.acquisition_method,
            "acquisition_cost": str(req.acquisition_cost),
        },
        recorded_by=user_id,
        event_at=datetime.combine(req.acquisition_date, datetime.min.time(), tzinfo=timezone.utc),
    )
    if req.current_weight is not None:
        acquisition_dt = datetime.combine(req.acquisition_date, datetime.min.time(), tzinfo=timezone.utc)
        db.add(WeightRecord(
            animal_id=animal.id, weight_kg=req.current_weight,
            recorded_at=acquisition_dt, recorded_by=user_id,
            notes="Initial weight at acquisition",
        ))

    await db.commit()
    await db.refresh(animal)

    # Spec §31/§52.6 - acquisition must eventually create a Finance ledger entry.
    # The Finance service doesn't exist yet (Phase 5); publishing now means the
    # handler can be added later without touching this call site.
    await publish("AnimalAcquired", {
        "organization_id": str(org_id),
        "animal_id": str(animal.id),
        "acquisition_cost": str(req.acquisition_cost),
    })
    return animal


async def update_animal(
    db: AsyncSession, animal: Animal, req: schemas.AnimalUpdate, user_id: uuid.UUID,
) -> Animal:
    changes = req.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(animal, field, value)
    if changes:
        await _record_event(db, animal.id, "updated", data={"fields": list(changes.keys())}, recorded_by=user_id)
    await db.commit()
    await db.refresh(animal)
    return animal


async def change_status(
    db: AsyncSession, animal: Animal, req: schemas.StatusChangeRequest, user_id: uuid.UUID,
) -> Animal:
    allowed = _ALLOWED_TRANSITIONS.get(animal.status, set())
    if req.status == animal.status:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Animal is already in that status")
    if req.status not in allowed:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot transition animal from '{animal.status}' to '{req.status}'",
        )

    previous_status = animal.status
    animal.status = req.status
    await _record_event(
        db, animal.id, f"status_changed:{req.status}",
        data={"from": previous_status, "to": req.status, "reason": req.reason},
        recorded_by=user_id,
    )
    await db.commit()
    await db.refresh(animal)

    if req.status == "sold":
        await publish("AnimalSold", {"animal_id": str(animal.id), "organization_id": str(animal.organization_id)})
    elif req.status == "deceased":
        await publish("AnimalDeceased", {"animal_id": str(animal.id), "organization_id": str(animal.organization_id)})

    return animal


async def record_weight(
    db: AsyncSession, animal: Animal, req: schemas.WeightRecordCreate, user_id: uuid.UUID,
) -> WeightRecord:
    recorded_at = req.recorded_at or datetime.now(timezone.utc)
    record = WeightRecord(
        animal_id=animal.id, weight_kg=req.weight_kg,
        recorded_at=recorded_at, recorded_by=user_id, notes=req.notes,
    )
    db.add(record)
    animal.current_weight = req.weight_kg
    await _record_event(
        db, animal.id, "weighed", data={"weight_kg": str(req.weight_kg)},
        recorded_by=user_id, event_at=recorded_at,
    )
    await db.commit()
    await db.refresh(record)
    await publish("AnimalWeightUpdated", {"animal_id": str(animal.id), "weight_kg": str(req.weight_kg)})
    return record


def compute_weight_history_with_adg(weights: list[WeightRecord]) -> list[schemas.WeightRecordOut]:
    """Average Daily Gain per spec §8: ADG = (current - previous) / days_between."""
    ordered = sorted(weights, key=lambda w: w.recorded_at)
    results: list[schemas.WeightRecordOut] = []
    previous: WeightRecord | None = None
    for w in ordered:
        adg = None
        if previous is not None:
            days = (w.recorded_at - previous.recorded_at).total_seconds() / 86400
            if days > 0:
                adg = (Decimal(w.weight_kg) - Decimal(previous.weight_kg)) / Decimal(days)
        results.append(schemas.WeightRecordOut(
            id=w.id, weight_kg=w.weight_kg, recorded_at=w.recorded_at,
            recorded_by=w.recorded_by, notes=w.notes,
            average_daily_gain=adg.quantize(Decimal("0.01")) if adg is not None else None,
        ))
        previous = w
    return list(reversed(results))  # most recent first


async def move_animal(
    db: AsyncSession, animal: Animal, req: schemas.MovementCreate, user_id: uuid.UUID,
) -> Movement:
    moved_at = req.moved_at or datetime.now(timezone.utc)
    movement = Movement(
        animal_id=animal.id,
        from_location_id=animal.location_id,
        to_location_id=req.to_location_id,
        moved_at=moved_at,
        reason=req.reason,
        authorized_by=user_id,
        notes=req.notes,
    )
    db.add(movement)
    animal.location_id = req.to_location_id  # current state; movement row preserves history (spec §52.8)
    await _record_event(
        db, animal.id, "moved",
        data={"from": str(movement.from_location_id) if movement.from_location_id else None,
              "to": str(req.to_location_id), "reason": req.reason},
        recorded_by=user_id, event_at=moved_at,
    )
    await db.commit()
    await db.refresh(movement)
    return movement


def compute_profitability(animal: Animal) -> schemas.AnimalProfitability:
    """Spec §25 - partial until Health/Feed/Finance services exist (Ph3/Ph5);
    those cost components are explicit zeros, not silently dropped."""
    acquisition = Decimal(animal.acquisition_cost)
    total = acquisition  # + feed_cost + health_cost + transport_cost + other_cost (later phases)
    expected_price = Decimal(animal.expected_sale_price) if animal.expected_sale_price is not None else None
    expected_profit = (expected_price - total) if expected_price is not None else None
    return schemas.AnimalProfitability(
        animal_id=animal.id,
        acquisition_cost=acquisition,
        total_investment=total,
        expected_sale_price=animal.expected_sale_price,
        expected_profit=expected_profit,
        current_value=animal.current_value,
    )


async def get_herd_summary(db: AsyncSession, org_id: uuid.UUID) -> dict:
    """Backs the dashboard 'Total Herd' style cards (spec §24/§68). Factored
    out of the router so reporting/service.py can compose it into the
    cross-module dashboard without duplicating the query."""
    base = select(func.count(Animal.id)).where(Animal.organization_id == org_id)
    total = (await db.execute(base)).scalar_one()
    active = (await db.execute(base.where(Animal.status.notin_(INACTIVE_STATUSES)))).scalar_one()
    by_species_rows = await db.execute(
        select(Animal.species, func.count(Animal.id))
        .where(Animal.organization_id == org_id, Animal.status.notin_(INACTIVE_STATUSES))
        .group_by(Animal.species)
    )
    for_sale = (await db.execute(base.where(Animal.status == "for_sale"))).scalar_one()
    reserved = (await db.execute(base.where(Animal.status == "reserved"))).scalar_one()
    sold = (await db.execute(base.where(Animal.status == "sold"))).scalar_one()
    deceased = (await db.execute(base.where(Animal.status == "deceased"))).scalar_one()
    herd_value_row = await db.execute(
        select(func.coalesce(func.sum(Animal.current_value), 0)).where(
            Animal.organization_id == org_id, Animal.status.notin_(INACTIVE_STATUSES),
        )
    )
    return {
        "total_animals": total,
        "active_animals": active,
        "by_species": dict(by_species_rows.all()),
        "for_sale": for_sale,
        "reserved": reserved,
        "sold": sold,
        "deceased": deceased,
        "herd_value": herd_value_row.scalar_one(),
    }


async def get_animal_qr_svg(db: AsyncSession, org_id: uuid.UUID, animal_id: uuid.UUID) -> bytes:
    """Spec §38 - generates a QR code encoding a link to the animal's
    profile. New dependency: qrcode (added to requirements.txt this
    session) - not installable/testable in this sandbox (no network), same
    written-not-run caveat as reportlab/finance/pdf.py. SVG output
    specifically (not PNG) so this needs no Pillow/libjpeg in the Docker
    image - qrcode's SvgImage factory renders pure vector paths.

    The link points at `{PUBLIC_SITE_BASE_URL}/animals/{animal_id}` - a
    frontend route that does not exist in apps/web yet (see
    docs/architecture.md's Phase 21 note). The backend data it should
    eventually render is already live at
    `/api/v1/public/{org_slug}/animals/{animal_id}/qr-profile`
    (public.service.get_animal_qr_profile); generating the *code* and
    building the *page* it points to are separable, and only the former is
    in scope here."""
    from app.core.config import get_settings
    from app.modules.identity.models import Organization

    await get_animal(db, animal_id, org_id)  # 404s if the animal isn't in this org

    org_result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = org_result.scalar_one()  # org_id is always the authenticated caller's own org

    settings = get_settings()
    url = f"{settings.PUBLIC_SITE_BASE_URL}/{org.slug}/animals/{animal_id}"

    import io
    import qrcode
    import qrcode.image.svg

    img = qrcode.make(url, image_factory=qrcode.image.svg.SvgImage, box_size=10)
    buffer = io.BytesIO()
    img.save(buffer)
    return buffer.getvalue()
