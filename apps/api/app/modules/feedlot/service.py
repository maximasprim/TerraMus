"""Feedlot service: batches, bulk weigh-in, exits, performance, costing, profitability."""
import uuid
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import publish
from app.modules.feedlot import metrics, schemas
from app.modules.feedlot.models import (
    CostingDocument, FeedlotAnimal, FeedlotExit, IntakeBatch, SaleBatch, WeighSession,
)
from app.modules.livestock import schemas as livestock_schemas, service as livestock_service
from app.modules.livestock.models import INACTIVE_STATUSES, Animal, WeightRecord


def _day_start(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=timezone.utc)


def _404(what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found")


# ------------------------------------------------------------------ batches
async def _next_number(db: AsyncSession, model, org_id: uuid.UUID) -> int:
    r = await db.execute(select(func.coalesce(func.max(model.batch_number), 0)).where(model.organization_id == org_id))
    return int(r.scalar_one()) + 1


async def _intake_counts(db: AsyncSession, org_id: uuid.UUID) -> dict[uuid.UUID, tuple[int, int]]:
    rows = await db.execute(
        select(FeedlotAnimal.intake_batch_id, func.count(FeedlotAnimal.id),
               func.count(FeedlotAnimal.id).filter(Animal.status.notin_(INACTIVE_STATUSES)))
        .join(Animal, Animal.id == FeedlotAnimal.animal_id)
        .where(FeedlotAnimal.organization_id == org_id).group_by(FeedlotAnimal.intake_batch_id)
    )
    return {b: (int(t), int(a)) for b, t, a in rows.all()}


def _intake_out(b: IntakeBatch, counts: dict) -> schemas.IntakeBatchOut:
    total, active = counts.get(b.id, (0, 0))
    out = schemas.IntakeBatchOut.model_validate(b)
    out.landed_cost, out.landed_cost_per_head = b.landed_cost, b.landed_cost_per_head
    out.head_registered, out.head_active = total, active
    return out


async def list_intake_batches(db, org_id):
    rows = (await db.execute(select(IntakeBatch).where(IntakeBatch.organization_id == org_id)
                             .order_by(IntakeBatch.batch_number))).scalars().all()
    counts = await _intake_counts(db, org_id)
    return [_intake_out(b, counts) for b in rows]


async def get_intake_batch(db, org_id, batch_id) -> IntakeBatch:
    b = (await db.execute(select(IntakeBatch).where(IntakeBatch.id == batch_id,
                                                    IntakeBatch.organization_id == org_id))).scalar_one_or_none()
    if not b:
        raise _404("Intake batch")
    return b


async def create_intake_batch(db, org_id, req: schemas.IntakeBatchCreate) -> schemas.IntakeBatchOut:
    number = req.batch_number or await _next_number(db, IntakeBatch, org_id)
    dup = (await db.execute(select(IntakeBatch.id).where(IntakeBatch.organization_id == org_id,
                                                         IntakeBatch.batch_number == number))).first()
    if dup:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Intake batch {number} already exists")
    data = req.model_dump(exclude={"batch_number", "name"})
    b = IntakeBatch(organization_id=org_id, batch_number=number, name=req.name or f"BATCH {number}", **data)
    db.add(b)
    await db.commit()
    await db.refresh(b)
    return _intake_out(b, {})


async def update_intake_batch(db, org_id, batch_id, req: schemas.IntakeBatchUpdate) -> schemas.IntakeBatchOut:
    b = await get_intake_batch(db, org_id, batch_id)
    for k, v in req.model_dump(exclude_unset=True).items():
        setattr(b, k, v)
    await db.commit()
    await db.refresh(b)
    return _intake_out(b, await _intake_counts(db, org_id))


async def delete_intake_batch(db, org_id, batch_id) -> None:
    b = await get_intake_batch(db, org_id, batch_id)
    n = (await db.execute(select(func.count(FeedlotAnimal.id)).where(FeedlotAnimal.intake_batch_id == b.id))).scalar_one()
    if n:
        raise HTTPException(status.HTTP_409_CONFLICT, "Batch has animals linked to it and cannot be deleted")
    await db.delete(b)
    await db.commit()


async def _sale_totals(db, org_id) -> dict[uuid.UUID, tuple[int, float, float]]:
    rows = await db.execute(
        select(FeedlotExit.sale_batch_id, func.count(FeedlotExit.id),
               func.coalesce(func.sum(FeedlotExit.exit_weight_kg), 0), func.coalesce(func.sum(FeedlotExit.amount), 0))
        .where(FeedlotExit.organization_id == org_id, FeedlotExit.exit_type == "sold",
               FeedlotExit.sale_batch_id.is_not(None)).group_by(FeedlotExit.sale_batch_id)
    )
    return {b: (int(n), float(w), float(a)) for b, n, w, a in rows.all()}


def _sale_out(b: SaleBatch, totals: dict) -> schemas.SaleBatchOut:
    n, w, a = totals.get(b.id, (0, 0.0, 0.0))
    out = schemas.SaleBatchOut.model_validate(b)
    out.head_sold, out.total_weight_kg, out.total_amount = n, w, a
    return out


async def list_sale_batches(db, org_id):
    rows = (await db.execute(select(SaleBatch).where(SaleBatch.organization_id == org_id)
                             .order_by(SaleBatch.batch_number))).scalars().all()
    totals = await _sale_totals(db, org_id)
    return [_sale_out(b, totals) for b in rows]


async def get_sale_batch(db, org_id, batch_id) -> SaleBatch:
    b = (await db.execute(select(SaleBatch).where(SaleBatch.id == batch_id,
                                                  SaleBatch.organization_id == org_id))).scalar_one_or_none()
    if not b:
        raise _404("Sale batch")
    return b


async def create_sale_batch(db, org_id, req: schemas.SaleBatchCreate) -> schemas.SaleBatchOut:
    number = req.batch_number or await _next_number(db, SaleBatch, org_id)
    dup = (await db.execute(select(SaleBatch.id).where(SaleBatch.organization_id == org_id,
                                                       SaleBatch.batch_number == number))).first()
    if dup:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Sale batch {number} already exists")
    b = SaleBatch(organization_id=org_id, batch_number=number, **req.model_dump(exclude={"batch_number"}))
    db.add(b)
    await db.commit()
    await db.refresh(b)
    return _sale_out(b, {})


async def update_sale_batch(db, org_id, batch_id, req: schemas.SaleBatchUpdate) -> schemas.SaleBatchOut:
    b = await get_sale_batch(db, org_id, batch_id)
    for k, v in req.model_dump(exclude_unset=True).items():
        setattr(b, k, v)
    await db.commit()
    await db.refresh(b)
    return _sale_out(b, await _sale_totals(db, org_id))


# ------------------------------------------------- registering animals in a batch
async def register_batch_animals(db, org_id, user_id, batch: IntakeBatch, req: schemas.RegisterAnimalsRequest) -> dict:
    farm_id = req.farm_id or batch.farm_id
    if not farm_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "farm_id is required (the batch has no farm set)")
    # capture scalars now: a rollback below would expire the ORM object
    batch_id, delivered_on, source, sex_class = batch.id, batch.delivered_on, batch.source, batch.sex_class
    per_head = Decimal(str(batch.landed_cost_per_head))
    category = req.category or (sex_class if sex_class in ("bull", "steer", "heifer") else None)
    sex = "female" if sex_class == "heifer" else "male"
    tags = [a.animal_number for a in req.animals]
    existing = set((await db.execute(select(Animal.animal_number).where(
        Animal.organization_id == org_id, Animal.animal_number.in_(tags)))).scalars().all())
    results = []
    for item in req.animals:
        if item.animal_number in existing:
            results.append({"animal_number": item.animal_number, "status": "exists"})
            continue
        try:
            animal = await livestock_service.create_animal(db, org_id, user_id, livestock_schemas.AnimalCreate(
                farm_id=farm_id, animal_number=item.animal_number, ear_tag=item.ear_tag, rfid=item.rfid,
                species=req.species, breed=item.breed, category=category, sex=sex,
                acquisition_date=delivered_on, acquisition_method="purchased", acquisition_cost=per_head,
                current_weight=item.entry_weight_kg, source=source, notes=item.notes))
            db.add(FeedlotAnimal(organization_id=org_id, animal_id=animal.id, intake_batch_id=batch_id,
                                 received_on=delivered_on, entry_weight_kg=item.entry_weight_kg))
            await db.commit()
            results.append({"animal_number": item.animal_number, "status": "created", "animal_id": str(animal.id)})
        except HTTPException as e:
            await db.rollback()
            results.append({"animal_number": item.animal_number, "status": "error", "detail": e.detail})
        except Exception as e:  # e.g. unique violation from a concurrent request
            await db.rollback()
            results.append({"animal_number": item.animal_number, "status": "error", "detail": str(e)[:200]})
    return {"created": sum(r["status"] == "created" for r in results), "results": results}


async def link_existing_animals(db, org_id, batch: IntakeBatch, req: schemas.LinkExistingRequest) -> dict:
    results = []
    for item in req.animals:
        animal = (await db.execute(select(Animal).where(Animal.id == item.animal_id,
                                                        Animal.organization_id == org_id))).scalar_one_or_none()
        if not animal:
            results.append({"animal_id": str(item.animal_id), "status": "not_found"})
            continue
        if (await db.execute(select(FeedlotAnimal.id).where(FeedlotAnimal.animal_id == animal.id))).first():
            results.append({"animal_id": str(item.animal_id), "status": "already_linked"})
            continue
        entry = item.entry_weight_kg or animal.current_weight
        db.add(FeedlotAnimal(organization_id=org_id, animal_id=animal.id, intake_batch_id=batch.id,
                             received_on=animal.acquisition_date, entry_weight_kg=entry))
        results.append({"animal_id": str(item.animal_id), "status": "linked"})
    await db.commit()
    return {"linked": sum(r["status"] == "linked" for r in results), "results": results}


# ------------------------------------------------------------------ weigh days
async def bulk_weigh(db, org_id, user_id, req: schemas.BulkWeighRequest) -> dict:
    tags = [e.animal_number for e in req.entries if e.animal_number]
    ids = [e.animal_id for e in req.entries if e.animal_id]
    q = select(Animal).where(Animal.organization_id == org_id)
    conds = []
    if tags:
        conds.append(Animal.animal_number.in_(tags))
    if ids:
        conds.append(Animal.id.in_(ids))
    from sqlalchemy import or_
    animals = (await db.execute(q.where(or_(*conds)))).scalars().all()
    by_tag = {a.animal_number: a for a in animals}
    by_id = {a.id: a for a in animals}

    day_lo, day_hi = _day_start(req.weighed_on), _day_start(req.weighed_on + timedelta(days=1))
    aids = [a.id for a in animals]
    existing_today: dict[uuid.UUID, WeightRecord] = {}
    all_weights: dict[uuid.UUID, list[tuple[datetime, float]]] = defaultdict(list)
    if aids:
        for w in (await db.execute(select(WeightRecord).where(WeightRecord.animal_id.in_(aids)))).scalars():
            all_weights[w.animal_id].append((w.recorded_at, float(w.weight_kg)))
            if day_lo <= w.recorded_at < day_hi:
                existing_today[w.animal_id] = w

    s = metrics.get_settings(await _settings_data(db, org_id))
    results, seen, recorded = [], set(), 0
    for e in req.entries:
        animal = by_id.get(e.animal_id) if e.animal_id else by_tag.get(e.animal_number)
        label = e.animal_number or str(e.animal_id)
        if not animal:
            results.append({"animal": label, "status": "unknown_animal"})
            continue
        if animal.id in seen:
            results.append({"animal": label, "status": "duplicate_in_request"})
            continue
        seen.add(animal.id)
        if animal.status in INACTIVE_STATUSES:
            results.append({"animal": label, "status": "inactive_animal", "detail": animal.status})
            continue
        w = float(e.weight_kg)
        flags = []
        prior = sorted((t, kg) for t, kg in all_weights.get(animal.id, []) if t < day_lo)
        if prior:
            days = (req.weighed_on - prior[-1][0].date()).days
            if days > 0 and abs(w - prior[-1][1]) / days > s["implausible_gain_kg_per_day"]:
                flags.append(f"large_change_{round(w - prior[-1][1], 1)}kg_in_{days}d")
        dup = existing_today.get(animal.id)
        if dup is not None and not req.overwrite:
            results.append({"animal": label, "status": "already_recorded", "existing_kg": float(dup.weight_kg)})
            continue
        if not req.dry_run:
            if dup is not None:
                dup.weight_kg = e.weight_kg
            else:
                db.add(WeightRecord(animal_id=animal.id, weight_kg=e.weight_kg, recorded_at=_day_start(req.weighed_on),
                                    recorded_by=user_id, notes=req.notes or "Weigh day"))
                await livestock_service._record_event(db, animal.id, "weighed", data={"weight_kg": str(e.weight_kg)},
                                                      recorded_by=user_id, event_at=_day_start(req.weighed_on))
            latest_prior = max((t for t, _ in all_weights.get(animal.id, [])), default=None)
            if latest_prior is None or _day_start(req.weighed_on) >= latest_prior:
                animal.current_weight = e.weight_kg   # never let a back-dated weight overwrite a newer one
        recorded += 1
        results.append({"animal": label, "status": "would_record" if req.dry_run else ("updated" if dup else "recorded"),
                        **({"flags": flags} if flags else {})})
    session_id = None
    if not req.dry_run and recorded:
        sess = WeighSession(organization_id=org_id, farm_id=req.farm_id, weighed_on=req.weighed_on,
                            scale_label=req.scale_label, notes=req.notes, head_count=recorded, created_by=user_id)
        db.add(sess)
        await db.commit()
        session_id = str(sess.id)
    elif not req.dry_run:
        await db.rollback()
    return {"dry_run": req.dry_run, "weighed_on": req.weighed_on.isoformat(), "recorded": recorded,
            "session_id": session_id, "results": results,
            "problems": [r for r in results if r["status"] in ("unknown_animal", "inactive_animal", "duplicate_in_request")]}


async def list_weigh_sessions(db, org_id, limit: int = 100):
    rows = (await db.execute(select(WeighSession).where(WeighSession.organization_id == org_id)
                             .order_by(WeighSession.weighed_on.desc()).limit(limit))).scalars().all()
    return [{"id": str(r.id), "weighed_on": r.weighed_on.isoformat(), "scale_label": r.scale_label,
             "head_count": r.head_count, "notes": r.notes} for r in rows]


# ------------------------------------------------------------------------ exits
async def _resolve_animal(db, org_id, animal_number=None, animal_id=None) -> Animal | None:
    q = select(Animal).where(Animal.organization_id == org_id)
    q = q.where(Animal.id == animal_id) if animal_id else q.where(Animal.animal_number == animal_number)
    return (await db.execute(q)).scalar_one_or_none()


async def record_sale(db, org_id, user_id, animal: Animal, *, exit_date, weight, price, sale_batch: SaleBatch | None,
                      customer_id=None, salesperson=None) -> FeedlotExit:
    fa = (await db.execute(select(FeedlotAnimal).where(FeedlotAnimal.animal_id == animal.id))).scalar_one_or_none()
    if not fa:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{animal.animal_number} is not in a feedlot intake batch")
    if (await db.execute(select(FeedlotExit.id).where(FeedlotExit.animal_id == animal.id))).first():
        raise HTTPException(status.HTTP_409_CONFLICT, f"{animal.animal_number} has already left the feedlot")
    if animal.status in INACTIVE_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{animal.animal_number} is {animal.status} and cannot be sold")
    rate = price if price is not None else (sale_batch.price_per_kg if sale_batch else None)
    if rate is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "price_per_kg is required (none on the sale batch either)")
    amount = metrics.q2(Decimal(str(weight)) * Decimal(str(rate)))
    ex = FeedlotExit(organization_id=org_id, animal_id=animal.id, exit_type="sold", exit_date=exit_date,
                     sale_batch_id=sale_batch.id if sale_batch else None, exit_weight_kg=weight, price_per_kg=rate,
                     amount=amount, customer_id=customer_id or (sale_batch.customer_id if sale_batch else None),
                     salesperson=salesperson, created_by=user_id)
    db.add(ex)
    await db.flush()
    from app.modules.receivables import service as receivables   # same transaction: no sale without its ledger entry
    await receivables.stage_feedlot_sale(db, org_id, user_id, ex, animal)
    prev = animal.status
    animal.status = "sold"
    await livestock_service._record_event(db, animal.id, "status_changed:sold", recorded_by=user_id,
                                          data={"from": prev, "to": "sold", "weight_kg": str(weight),
                                                "price_per_kg": str(rate), "amount": str(amount)})
    await db.commit()
    await publish("AnimalSold", {"animal_id": str(animal.id), "organization_id": str(org_id)})
    return ex


async def record_cull(db, org_id, user_id, animal: Animal, req: schemas.CullRequest) -> FeedlotExit:
    fa = (await db.execute(select(FeedlotAnimal).where(FeedlotAnimal.animal_id == animal.id))).scalar_one_or_none()
    if not fa:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{animal.animal_number} is not in a feedlot intake batch")
    if (await db.execute(select(FeedlotExit.id).where(FeedlotExit.animal_id == animal.id))).first():
        raise HTTPException(status.HTTP_409_CONFLICT, f"{animal.animal_number} has already left the feedlot")
    if animal.status in INACTIVE_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{animal.animal_number} is already {animal.status}")
    ex = FeedlotExit(organization_id=org_id, animal_id=animal.id, exit_type=req.exit_type, exit_date=req.exit_date,
                     exit_weight_kg=req.exit_weight_kg, amount=0, reason=req.reason, created_by=user_id)
    db.add(ex)
    new_status = "culled" if req.exit_type == "culled" else "deceased"
    prev = animal.status
    animal.status = new_status
    await livestock_service._record_event(db, animal.id, f"status_changed:{new_status}", recorded_by=user_id,
                                          data={"from": prev, "to": new_status, "reason": req.reason})
    await db.commit()
    if new_status == "deceased":
        await publish("AnimalDeceased", {"animal_id": str(animal.id), "organization_id": str(org_id)})
    return ex


async def record_batch_sales(db, org_id, user_id, batch: SaleBatch, req: schemas.BatchSaleRequest) -> dict:
    results = []
    batch_id = batch.id
    for e in req.entries:
        label = e.animal_number or str(e.animal_id)
        animal = await _resolve_animal(db, org_id, e.animal_number, e.animal_id)
        if not animal:
            results.append({"animal": label, "status": "unknown_animal"})
            continue
        try:
            sb = await get_sale_batch(db, org_id, batch_id)
            ex = await record_sale(db, org_id, user_id, animal, exit_date=sb.sold_on, weight=e.exit_weight_kg,
                                   price=e.price_per_kg, sale_batch=sb, customer_id=e.customer_id,
                                   salesperson=e.salesperson)
            results.append({"animal": label, "status": "sold", "amount": float(ex.amount)})
        except HTTPException as ex_:
            await db.rollback()
            results.append({"animal": label, "status": "error", "detail": ex_.detail})
    return {"sold": sum(r["status"] == "sold" for r in results), "results": results}


# ------------------------------------------------------------------- costing docs
async def _settings_data(db, org_id) -> dict:
    d = (await db.execute(select(CostingDocument).where(CostingDocument.organization_id == org_id,
                                                        CostingDocument.kind == "settings"))).scalars().first()
    return d.data if d else {}


async def _docs_by_kind(db, org_id) -> dict[str, list[CostingDocument]]:
    out: dict[str, list[CostingDocument]] = defaultdict(list)
    for d in (await db.execute(select(CostingDocument).where(CostingDocument.organization_id == org_id)
                               .order_by(CostingDocument.kind, CostingDocument.name))).scalars():
        out[d.kind].append(d)
    return out


def _validate_doc(kind: str, data: dict) -> None:
    def need(key, typ):
        if key in data and not isinstance(data[key], typ):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"'{key}' must be a {typ.__name__}")
    if kind == "recipe":
        need("ingredients", list); need("fixed_costs", list)
    elif kind == "enterprise_budget":
        need("lines", list)
    elif kind == "ration_plan":
        need("stages", list); need("feed_costs", dict); need("cost_links", dict)
        for st in data.get("stages", []):
            if not isinstance(st, dict) or "days" not in st or not isinstance(st.get("feeds", {}), dict):
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "each stage needs 'days' and a 'feeds' map")
    elif kind == "overhead_pool":
        need("lines", list)


def _compute(doc: CostingDocument, by_kind: dict[str, list[CostingDocument]], fodder: dict[str, float] | None = None) -> dict | None:
    if doc.kind == "recipe":
        return metrics.recipe_cost(doc.data)
    if doc.kind == "enterprise_budget":
        return metrics.budget_cost(doc.data)
    if doc.kind == "overhead_pool":
        return metrics.overhead_totals(doc.data)
    if doc.kind == "ration_plan":
        costs = metrics.resolve_feed_costs(doc.data, {d.name: d.data for d in by_kind.get("enterprise_budget", [])},
                                           {d.name: d.data for d in by_kind.get("recipe", [])}, fodder)
        stages = doc.data.get("stages", [])
        per_day = [round(metrics.ration_stage_cost_per_day(st, costs), 4) for st in stages]
        total_days = sum(int(metrics._f(st.get("days"))) for st in stages)
        return {"feed_costs": costs, "stage_cost_per_day": per_day, "total_days": total_days,
                "total_cost": metrics.standard_feed_cost(stages, costs, total_days),
                "avg_cost_per_day": round(metrics.standard_feed_cost(stages, costs, total_days) / total_days, 2) if total_days else 0}
    return None


async def _fodder_costs(db, org_id) -> dict[str, float]:
    """Average cost per kg of our own fodder stock, by product name (empty if the fodder module has nothing yet)."""
    try:
        from app.modules.fodder.service import cost_map
    except ImportError:
        return {}
    return await cost_map(db, org_id)


async def list_costing_docs(db, org_id, kind: str | None = None) -> list[schemas.CostingDocumentOut]:
    by_kind = await _docs_by_kind(db, org_id)
    fodder = await _fodder_costs(db, org_id)
    out = []
    for k, docs in by_kind.items():
        if kind and k != kind:
            continue
        for d in docs:
            o = schemas.CostingDocumentOut.model_validate(d)
            o.computed = _compute(d, by_kind, fodder)
            out.append(o)
    return out


async def _get_doc(db, org_id, doc_id) -> CostingDocument:
    d = (await db.execute(select(CostingDocument).where(CostingDocument.id == doc_id,
                                                        CostingDocument.organization_id == org_id))).scalar_one_or_none()
    if not d:
        raise _404("Costing document")
    return d


async def upsert_costing_doc(db, org_id, kind: str, name: str, data: dict) -> CostingDocument:
    _validate_doc(kind, data)
    d = (await db.execute(select(CostingDocument).where(CostingDocument.organization_id == org_id,
                                                        CostingDocument.kind == kind,
                                                        CostingDocument.name == name))).scalar_one_or_none()
    if d:
        d.data = data
    else:
        d = CostingDocument(organization_id=org_id, kind=kind, name=name, data=data)
        db.add(d)
    return d


async def create_costing_doc(db, org_id, req: schemas.CostingDocumentCreate) -> schemas.CostingDocumentOut:
    _validate_doc(req.kind, req.data)
    exists = (await db.execute(select(CostingDocument.id).where(
        CostingDocument.organization_id == org_id, CostingDocument.kind == req.kind,
        CostingDocument.name == req.name))).first()
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, f"A {req.kind} named '{req.name}' already exists")
    d = CostingDocument(organization_id=org_id, kind=req.kind, name=req.name, data=req.data)
    db.add(d)
    await db.commit()
    await db.refresh(d)
    o = schemas.CostingDocumentOut.model_validate(d)
    o.computed = _compute(d, await _docs_by_kind(db, org_id), await _fodder_costs(db, org_id))
    return o


async def update_costing_doc(db, org_id, doc_id, req: schemas.CostingDocumentUpdate) -> schemas.CostingDocumentOut:
    d = await _get_doc(db, org_id, doc_id)
    if req.data is not None:
        _validate_doc(d.kind, req.data)
        d.data = req.data
    if req.name:
        d.name = req.name
    await db.commit()
    await db.refresh(d)
    o = schemas.CostingDocumentOut.model_validate(d)
    o.computed = _compute(d, await _docs_by_kind(db, org_id), await _fodder_costs(db, org_id))
    return o


async def delete_costing_doc(db, org_id, doc_id) -> None:
    await db.delete(await _get_doc(db, org_id, doc_id))
    await db.commit()


# -------------------------------------------------------- performance & profit
async def _load(db, org_id) -> list[tuple[metrics.AnimalInput, dict]]:
    rows = (await db.execute(
        select(FeedlotAnimal, Animal, IntakeBatch)
        .join(Animal, Animal.id == FeedlotAnimal.animal_id)
        .join(IntakeBatch, IntakeBatch.id == FeedlotAnimal.intake_batch_id)
        .where(FeedlotAnimal.organization_id == org_id))).all()
    if not rows:
        return []
    ids = [a.id for _, a, _ in rows]
    weights: dict[uuid.UUID, list[tuple[date, float]]] = defaultdict(list)
    for w in (await db.execute(select(WeightRecord).where(WeightRecord.animal_id.in_(ids)))).scalars():
        weights[w.animal_id].append((w.recorded_at.date(), float(w.weight_kg)))
    exits = {e.animal_id: e for e in (await db.execute(select(FeedlotExit).where(FeedlotExit.organization_id == org_id))).scalars()}
    sbs = {b.id: b for b in (await db.execute(select(SaleBatch).where(SaleBatch.organization_id == org_id))).scalars()}
    out = []
    for fa, animal, ib in rows:
        ex = exits.get(animal.id)
        sb = sbs.get(ex.sale_batch_id) if ex and ex.sale_batch_id else None
        inp = metrics.AnimalInput(
            animal_id=str(animal.id), tag=animal.animal_number, received_on=fa.received_on,
            entry_weight=float(fa.entry_weight_kg) if fa.entry_weight_kg is not None else None,
            weights=weights.get(animal.id, []), exit_type=ex.exit_type if ex else None,
            exit_date=ex.exit_date if ex else None,
            exit_weight=float(ex.exit_weight_kg) if ex and ex.exit_weight_kg is not None else None,
            exit_amount=float(ex.amount) if ex else 0.0, intake_batch=ib.batch_number,
            sale_batch=sb.batch_number if sb else None, landed_cost=ib.landed_cost_per_head)
        out.append((inp, {"intake_batch_id": str(ib.id), "sale_batch_id": str(sb.id) if sb else None,
                          "animal_status": animal.status, "ear_tag": animal.ear_tag}))
    return out


async def performance(db, org_id, as_of: date | None = None, intake_batch_id=None, sale_batch_id=None,
                      state: str | None = None) -> dict:
    as_of = as_of or date.today()
    s = metrics.get_settings(await _settings_data(db, org_id))
    animals = []
    for inp, meta in await _load(db, org_id):
        if intake_batch_id and meta["intake_batch_id"] != str(intake_batch_id):
            continue
        if sale_batch_id and meta["sale_batch_id"] != str(sale_batch_id):
            continue
        p = metrics.animal_performance(inp, as_of, s)
        p.update(meta)
        if state and p["status"] != state:
            continue
        animals.append(p)
    active = [p for p in animals if p["status"] == "active"]
    stale_cut = (as_of - timedelta(days=45)).isoformat()
    adgs = [p["adg"] for p in active if p["adg"] is not None]
    summary = {
        "head": len(animals), "active": len(active),
        "sold": sum(p["status"] == "sold" for p in animals),
        "culled": sum(p["status"] == "culled" for p in animals), "died": sum(p["status"] == "died" for p in animals),
        "market_ready": sum(p["market_ready"] for p in active),
        "avg_adg_active": round(sum(adgs) / len(adgs), 3) if adgs else None,
        "by_adg_band": {b: sum(1 for p in active if p["adg_band"] == b) for b in ("poor", "below_target", "on_target", "excellent")},
        "no_recent_weight": [p["tag"] for p in active if not p["latest_weigh_date"] or p["latest_weigh_date"] < stale_cut],
        "flagged": [{"tag": p["tag"], "flags": p["flags"]} for p in animals if p["flags"]],
    }
    return {"as_of": as_of.isoformat(), "settings": s, "summary": summary, "animals": animals}


def _agg(rows: list[dict]) -> dict:
    n = len(rows)
    def tot(k): return round(sum(r.get(k) or 0 for r in rows), 2)
    wts = [r["end_weight"] for r in rows if r.get("end_weight")]
    gains = [r["overall_gain"] for r in rows if r.get("overall_gain") is not None]
    adgs = [r["adg"] for r in rows if r.get("adg") is not None]
    shr = [r["presale_shrink_kg"] for r in rows if r.get("presale_shrink_kg") is not None]
    return {"head": n, "revenue": tot("revenue"), "landed_cost": tot("landed_cost"), "feed_cost": tot("feed_cost"),
            "ops_cost": tot("ops_cost"), "total_cost": tot("total_cost"),
            "profit": round(tot("revenue") - tot("total_cost"), 2) if n else 0.0,
            "profit_per_head": round((tot("revenue") - tot("total_cost")) / n, 2) if n else 0.0,
            "total_weight_kg": round(sum(wts), 1), "avg_weight_kg": round(sum(wts) / len(wts), 1) if wts else None,
            "total_gain_kg": round(sum(gains), 1), "avg_adg": round(sum(adgs) / len(adgs), 3) if adgs else None,
            "avg_days_on_farm": round(sum(r["days_on_farm"] for r in rows) / n, 1) if n else None,
            "avg_presale_shrink_kg": round(sum(shr) / len(shr), 1) if shr else None,
            "cost_per_kg_gain": round((tot("feed_cost") + tot("ops_cost")) / sum(gains), 2) if gains and sum(gains) > 0 else None,
            "effective_price_per_kg": round(tot("revenue") / sum(wts), 2) if wts and tot("revenue") else None}


async def profitability(db, org_id, as_of: date | None = None, intake_batch_id=None, sale_batch_id=None) -> dict:
    as_of = as_of or date.today()
    s = metrics.get_settings(await _settings_data(db, org_id))
    by_kind = await _docs_by_kind(db, org_id)
    plan = by_kind["ration_plan"][0] if by_kind.get("ration_plan") else None
    pool = by_kind["overhead_pool"][0] if by_kind.get("overhead_pool") else None
    stages = plan.data.get("stages", []) if plan else []
    feed_costs = metrics.resolve_feed_costs(plan.data, {d.name: d.data for d in by_kind.get("enterprise_budget", [])},
                                            {d.name: d.data for d in by_kind.get("recipe", [])}, await _fodder_costs(db, org_id)) if plan else {}
    pool_total = metrics.overhead_totals(pool.data)["total"] if pool else 0.0

    loaded = await _load(db, org_id)
    perfs = [(inp, metrics.animal_performance(inp, as_of, s), meta) for inp, meta in loaded]
    bull_days = sum(p["days_on_farm"] for _, p, _ in perfs)
    rate = (pool_total / bull_days) if bull_days else 0.0
    if pool and pool.data.get("rate_mode") == "fixed" and pool.data.get("fixed_rate"):
        rate = metrics._f(pool.data["fixed_rate"])
    sb_price = {}
    for sb in (await db.execute(select(SaleBatch).where(SaleBatch.organization_id == org_id).order_by(SaleBatch.sold_on))).scalars():
        if sb.price_per_kg:
            sb_price[sb.batch_number] = float(sb.price_per_kg)
    ref_price = list(sb_price.values())[-1] if sb_price else None

    animals = []
    for inp, p, meta in perfs:
        if intake_batch_id and meta["intake_batch_id"] != str(intake_batch_id):
            continue
        if sale_batch_id and meta["sale_batch_id"] != str(sale_batch_id):
            continue
        feed = metrics.standard_feed_cost(stages, feed_costs, p["days_on_farm"])
        ops = round(p["days_on_farm"] * rate, 2)
        row = {**p, **meta, **metrics.animal_profit(p, inp, feed, ops, s, ref_price)}
        animals.append(row)

    def group(key):
        g = defaultdict(list)
        for r in animals:
            if r[key] is not None:
                g[r[key]].append(r)
        return g
    realised = [r for r in animals if r["realised"]]
    by_sale = [{"sale_batch": k, **_agg([r for r in v if r["status"] == "sold"])} for k, v in sorted(group("sale_batch").items())]
    by_intake = []
    for k, v in sorted(group("intake_batch").items()):
        cullish = [r for r in v if r["status"] in ("culled", "died")]
        a = _agg([r for r in v if r["realised"]])
        a.update({"intake_batch": k, "head_total": len(v), "head_sold": sum(r["status"] == "sold" for r in v),
                  "head_culled": sum(r["status"] == "culled" for r in v), "head_died": sum(r["status"] == "died" for r in v),
                  "head_active": sum(r["status"] == "active" for r in v),
                  "loss_rate_pct": round(100 * len(cullish) / len(v), 1) if v else 0,
                  "unrealised_projected_profit": round(sum(r.get("projected_profit") or 0 for r in v if not r["realised"]), 2)})
        by_intake.append(a)
    return {"as_of": as_of.isoformat(),
            "assumptions": {"ration_plan": plan.name if plan else None, "feed_costs_per_kg": feed_costs,
                            "overhead_pool": pool.name if pool else None, "overhead_pool_total": pool_total,
                            "total_bull_days": bull_days, "overhead_rate_per_bull_day": round(rate, 2),
                            "overhead_method": "pool / actual bull-days (fully allocated, never over- or under-charged)",
                            "reference_price_per_kg": ref_price or s["reference_price_per_kg"]},
            "totals": {**_agg(realised), "head_realised": len(realised), "head_open": len(animals) - len(realised),
                       "unrealised_projected_profit": round(sum(r.get("projected_profit") or 0 for r in animals if not r["realised"]), 2)},
            "by_sale_batch": by_sale, "by_intake_batch": by_intake, "animals": animals}
