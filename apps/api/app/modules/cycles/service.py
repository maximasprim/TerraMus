"""Production cycle lifecycle, adoption of existing records, and the unassigned overview."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cycles import resolve
from app.modules.cycles.deps import CycleSel, ensure_writable, get_cycle
from app.modules.cycles.models import ProductionCycle
from app.modules.cycles.schemas import (AssignRequest, CycleClose, CycleCreate, CycleOut, CyclePreferences,
                                        CyclePreferencesOut, CycleUpdate)
from app.modules.feedlot.models import FeedlotAnimal, IntakeBatch, SaleBatch
from app.modules.livestock.models import Animal, INACTIVE_STATUSES

# Records a cycle can own directly (table -> (model path, org column?, date column, activity column or None)).
# Resolved lazily so importing this module never imports every feature module.
def _taggables():
    from app.modules.crops.models import CropPlanting
    from app.modules.finance.models import FinanceTransaction
    from app.modules.fodder.models import FodderCycle, FodderMovement
    from app.modules.fuel.models import FuelLog
    from app.modules.groups.models import AnimalGroup
    from app.modules.inventory.models import StockMovement
    from app.modules.procurement.models import PurchaseOrder
    from app.modules.receivables.models import AccountEntry
    from app.modules.training.models import TrainingSession
    return {
        "finance": ("Finance transactions", FinanceTransaction, FinanceTransaction.transaction_date, FinanceTransaction.activity),
        "receivables": ("Customer account entries", AccountEntry, AccountEntry.entry_date, AccountEntry.activity),
        "fuel": ("Fuel logs", FuelLog, FuelLog.log_date, FuelLog.activity),
        "groups": ("Flocks / ponds / hutches", AnimalGroup, AnimalGroup.start_date, None),
        "fodder_cycles": ("Fodder plantings", FodderCycle, FodderCycle.start_date, None),
        "fodder_movements": ("Fodder stock movements", FodderMovement, FodderMovement.movement_date, None),
        "crops": ("Crop plantings", CropPlanting, CropPlanting.planting_date, None),
        "training": ("Training sessions", TrainingSession, TrainingSession.start_date, None),
        "inventory": ("Inventory movements", StockMovement, func.date(StockMovement.moved_at), None),
        "purchase_orders": ("Purchase orders", PurchaseOrder, PurchaseOrder.order_date, None),
    }


def _out(c: ProductionCycle, counts: dict | None = None) -> CycleOut:
    o = CycleOut.model_validate(c)
    if counts:
        o.head_registered, o.head_active, o.intake_batches = counts.get("registered", 0), counts.get("active", 0), counts.get("batches", 0)
    return o


async def _counts(db, org_id) -> dict[uuid.UUID, dict]:
    out: dict[uuid.UUID, dict] = {}
    rows = await db.execute(
        select(IntakeBatch.production_cycle_id, func.count(FeedlotAnimal.id),
               func.count(FeedlotAnimal.id).filter(Animal.status.not_in(INACTIVE_STATUSES)))
        .select_from(IntakeBatch)
        .join(FeedlotAnimal, FeedlotAnimal.intake_batch_id == IntakeBatch.id, isouter=True)
        .join(Animal, Animal.id == FeedlotAnimal.animal_id, isouter=True)
        .where(IntakeBatch.organization_id == org_id, IntakeBatch.production_cycle_id.is_not(None))
        .group_by(IntakeBatch.production_cycle_id))
    for cid, reg, act in rows.all():
        out[cid] = {"registered": reg, "active": act}
    for cid, n in (await db.execute(select(IntakeBatch.production_cycle_id, func.count(IntakeBatch.id))
                                    .where(IntakeBatch.organization_id == org_id, IntakeBatch.production_cycle_id.is_not(None))
                                    .group_by(IntakeBatch.production_cycle_id))).all():
        out.setdefault(cid, {})["batches"] = n
    return out


async def list_cycles(db, org_id, state: str | None = None, enterprise: str | None = None) -> list[CycleOut]:
    q = select(ProductionCycle).where(ProductionCycle.organization_id == org_id)
    if state:
        q = q.where(ProductionCycle.status == state)
    if enterprise:
        q = q.where(ProductionCycle.enterprise == enterprise)
    rows = (await db.execute(q.order_by(ProductionCycle.cycle_number.desc()))).scalars().all()
    counts = await _counts(db, org_id)
    return [_out(c, counts.get(c.id)) for c in rows]


async def cycle_out(db, org_id, cycle_id) -> CycleOut:
    c = await get_cycle(db, org_id, cycle_id)
    return _out(c, (await _counts(db, org_id)).get(c.id))


async def create_cycle(db, org_id, user_id, req: CycleCreate) -> CycleOut:
    if req.farm_id:
        from app.modules.farm.models import Farm
        if not (await db.execute(select(Farm.id).where(Farm.id == req.farm_id, Farm.organization_id == org_id))).first():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Farm not found")
    number = req.cycle_number or ((await db.execute(select(func.max(ProductionCycle.cycle_number))
                                                     .where(ProductionCycle.organization_id == org_id))).scalar() or 0) + 1
    name = (req.name or f"Cycle {number}").strip()
    clash = await db.execute(select(ProductionCycle.cycle_number, ProductionCycle.name).where(
        ProductionCycle.organization_id == org_id,
        (ProductionCycle.cycle_number == number) | (func.lower(ProductionCycle.name) == name.lower())))
    if clash.first():
        raise HTTPException(status.HTTP_409_CONFLICT, f"A production cycle numbered {number} or named '{name}' already exists")
    c = ProductionCycle(organization_id=org_id, farm_id=req.farm_id, cycle_number=number, name=name, enterprise=req.enterprise,
                        status=req.status, start_date=req.start_date, end_date=req.end_date, notes=req.notes, created_by=user_id)
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return _out(c)


async def update_cycle(db, org_id, cycle_id, req: CycleUpdate) -> CycleOut:
    c = await get_cycle(db, org_id, cycle_id)
    changes = req.model_dump(exclude_unset=True)
    if c.status == "closed" and set(changes) - {"notes"}:
        raise HTTPException(status.HTTP_409_CONFLICT, "A closed cycle can only have its notes edited. Reopen it first.")
    if "name" in changes and changes["name"].strip().lower() != c.name.lower():
        if (await db.execute(select(ProductionCycle.id).where(ProductionCycle.organization_id == org_id,
                                                              func.lower(ProductionCycle.name) == changes["name"].strip().lower()))).first():
            raise HTTPException(status.HTTP_409_CONFLICT, f"A production cycle named '{changes['name']}' already exists")
        changes["name"] = changes["name"].strip()
    s, e = changes.get("start_date", c.start_date), changes.get("end_date", c.end_date)
    if s and e and e < s:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "end_date cannot be before start_date")
    for k, v in changes.items():
        setattr(c, k, v)
    await db.commit()
    await db.refresh(c)
    return _out(c, (await _counts(db, org_id)).get(c.id))


async def start_cycle(db, org_id, cycle_id) -> CycleOut:
    c = await get_cycle(db, org_id, cycle_id)
    if c.status != "planned":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Only a planned cycle can be started (this one is {c.status})")
    c.status = "running"
    c.start_date = c.start_date or date.today()
    await db.commit()
    await db.refresh(c)
    return _out(c, (await _counts(db, org_id)).get(c.id))


async def close_cycle(db, org_id, user_id, cycle_id, req: CycleClose) -> CycleOut:
    from app.modules.cycles.summary import build_summary
    c = await get_cycle(db, org_id, cycle_id)
    if c.status == "closed":
        raise HTTPException(status.HTTP_409_CONFLICT, "This cycle is already closed")
    on_feed = (await _counts(db, org_id)).get(c.id, {}).get("active", 0)
    if on_feed and not req.force:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"{on_feed} animal(s) are still on feed in '{c.name}'. Sell or cull them first, or close with force=true "
                            "(they stay in this cycle; their later weights and sales will be refused until it is reopened).")
    end = req.end_date or c.end_date or date.today()
    if c.start_date and end < c.start_date:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "end_date cannot be before the cycle's start_date")
    snapshot = await build_summary(db, org_id, c, as_of=end)           # frozen reference of the numbers at closing time
    snapshot["closed_with_animals_on_feed"] = on_feed
    c.status, c.end_date, c.closed_at, c.closed_by = "closed", end, datetime.now(timezone.utc), user_id
    c.close_summary = _jsonable(snapshot)
    if req.notes:
        c.notes = ((c.notes + "\n") if c.notes else "") + req.notes
    await db.commit()
    await db.refresh(c)
    return _out(c, (await _counts(db, org_id)).get(c.id))


async def reopen_cycle(db, org_id, cycle_id) -> CycleOut:
    c = await get_cycle(db, org_id, cycle_id)
    if c.status != "closed":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a closed cycle can be reopened")
    c.status, c.closed_at, c.closed_by = "running", None, None      # the closing snapshot is kept as history
    await db.commit()
    await db.refresh(c)
    return _out(c, (await _counts(db, org_id)).get(c.id))


async def delete_cycle(db, org_id, cycle_id) -> None:
    c = await get_cycle(db, org_id, cycle_id)
    used = []
    for label, model in (("intake batches", IntakeBatch), ("sale batches", SaleBatch)):
        n = (await db.execute(select(func.count()).select_from(model).where(model.production_cycle_id == c.id))).scalar_one()
        if n:
            used.append(f"{n} {label}")
    for key, (label, model, _, _) in _taggables().items():
        n = (await db.execute(select(func.count()).select_from(model).where(model.production_cycle_id == c.id))).scalar_one()
        if n:
            used.append(f"{n} {label.lower()}")
    from app.modules.feedlot.models import CostingDocument
    n = (await db.execute(select(func.count()).select_from(CostingDocument).where(CostingDocument.production_cycle_id == c.id))).scalar_one()
    if n:
        used.append(f"{n} costing documents")
    if used:
        raise HTTPException(status.HTTP_409_CONFLICT, "This cycle has records and cannot be deleted: " + ", ".join(used) + ".")
    await db.delete(c)
    await db.commit()


def _jsonable(o):
    import json
    return json.loads(json.dumps(o, default=lambda x: float(x) if hasattr(x, "quantize") else str(x)))


# ------------------------------------------------------------------------------------------- default view
async def get_preferences(db, org_id) -> CyclePreferencesOut:
    from app.modules.identity.models import Organization
    view = (await db.execute(select(Organization.default_cycle_view).where(Organization.id == org_id))).scalar_one_or_none() or "all"
    running = (await db.execute(select(ProductionCycle.id).where(ProductionCycle.organization_id == org_id,
                                                                 ProductionCycle.status == "running"))).scalars().all()
    return CyclePreferencesOut(default_view=view, running_cycles=len(running),
                               default_cycle_id=running[0] if view == "running" and len(running) == 1 else None)


async def set_preferences(db, org_id, req: CyclePreferences) -> CyclePreferencesOut:
    from app.modules.identity.models import Organization
    org = (await db.execute(select(Organization).where(Organization.id == org_id))).scalar_one()
    org.default_cycle_view = req.default_view
    await db.commit()
    return await get_preferences(db, org_id)


# ------------------------------------------------------------------------------------------- adoption
async def unassigned_overview(db, org_id) -> dict:
    """How much existing data sits outside every cycle (what 'assign' can still adopt)."""
    out = {}
    out["intake_batches"] = (await db.execute(select(func.count()).select_from(IntakeBatch).where(
        IntakeBatch.organization_id == org_id, IntakeBatch.production_cycle_id.is_(None)))).scalar_one()
    out["sale_batches"] = (await db.execute(select(func.count()).select_from(SaleBatch).where(
        SaleBatch.organization_id == org_id, SaleBatch.production_cycle_id.is_(None)))).scalar_one()
    for key, (label, model, _, _) in _taggables().items():
        q = select(func.count()).select_from(model).where(model.production_cycle_id.is_(None))
        if key == "finance":
            q = select(func.count()).select_from(model).where(model.organization_id == org_id, resolve.ledger_cycle(model).is_(None))
        elif hasattr(model, "organization_id"):
            q = q.where(model.organization_id == org_id)
        out[key] = (await db.execute(q)).scalar_one()
    return out


async def assign(db, org_id, cycle_id, req: AssignRequest) -> dict:
    """Adopt existing records into a cycle.

    * intake_batch_ids / sale_batch_ids: put those batches in the cycle. Everything that traces to their
      animals (weights, exits, purchase and sale ledger rows, customer payments, feed and vet cost) follows
      automatically because cycle membership is derived, not copied.
    * by_date: tag records that have NO cycle yet and fall inside a date window (manual expenses, fuel,
      flocks, ...). Tags are write-once: a record already in a cycle is never moved by this tool.
    dry_run (default) reports what would change and writes nothing."""
    c = await get_cycle(db, org_id, cycle_id)
    if not req.dry_run:
        await ensure_writable(db, org_id, cycle_id)
    report: dict = {"cycle": c.name, "dry_run": req.dry_run, "intake_batches": [], "sale_batches": [], "tagged": {}, "skipped": []}

    for model, ids, key in ((IntakeBatch, req.intake_batch_ids, "intake_batches"), (SaleBatch, req.sale_batch_ids, "sale_batches")):
        for bid in ids:
            b = (await db.execute(select(model).where(model.id == bid, model.organization_id == org_id))).scalar_one_or_none()
            if not b:
                raise HTTPException(status.HTTP_404_NOT_FOUND, f"{key[:-1].replace('_', ' ')} {bid} not found")
            if b.production_cycle_id == c.id:
                report["skipped"].append({"id": str(bid), "batch": b.batch_number, "reason": "already in this cycle"})
                continue
            clash = (await db.execute(select(model.id).where(
                model.organization_id == org_id, model.production_cycle_id == c.id,
                model.batch_number == b.batch_number, model.id != b.id).limit(1))).first()
            if clash:
                raise HTTPException(status.HTTP_409_CONFLICT,
                                    f"Cycle '{c.name}' already has a {key[:-1].replace('_', ' ')} numbered {b.batch_number}; "
                                    "batch numbers are unique within a cycle.")
            if b.production_cycle_id is not None:
                old = await get_cycle(db, org_id, b.production_cycle_id)
                if old.status == "closed":
                    raise HTTPException(status.HTTP_409_CONFLICT, f"Batch {b.batch_number} is in closed cycle '{old.name}'. Reopen it before moving the batch.")
                report["skipped"].append({"id": str(bid), "batch": b.batch_number, "reason": f"in cycle '{old.name}' (moved)"})
            report[key].append({"id": str(bid), "batch": b.batch_number, "from": str(b.production_cycle_id) if b.production_cycle_id else None})
            if not req.dry_run:
                b.production_cycle_id = c.id

    if req.by_date:
        w = req.by_date
        wanted = set(w.tables) or set(_taggables())
        unknown = wanted - set(_taggables())
        if unknown:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown table(s): {sorted(unknown)}. Use: {sorted(_taggables())}")
        for key in sorted(wanted):
            label, model, datecol, actcol = _taggables()[key]
            conds = [datecol >= w.from_date, datecol <= w.to_date]
            if hasattr(model, "organization_id"):
                conds.append(model.organization_id == org_id)
            if w.activity and actcol is not None:
                conds.append(actcol == w.activity)
            if w.farm_id and hasattr(model, "farm_id"):
                conds.append(model.farm_id == w.farm_id)
            # records with no tag of their own AND (for the ledgers) no cycle derived from their animals
            untagged = model.production_cycle_id.is_(None)
            if key == "finance":
                untagged = resolve.ledger_cycle(model).is_(None)
            elif key == "receivables":
                untagged = resolve.entry_cycle(model).is_(None)
            elif key == "inventory":
                untagged = resolve.stock_cycle(model).is_(None)
            n = (await db.execute(select(func.count()).select_from(model).where(*conds, untagged))).scalar_one()
            report["tagged"][key] = {"label": label, "records": n}
            if n and not req.dry_run:
                ids_q = select(model.id).where(*conds, untagged, model.production_cycle_id.is_(None))
                await db.execute(update(model).where(model.id.in_(ids_q)).values(production_cycle_id=c.id)
                                 .execution_options(synchronize_session=False))
    if req.dry_run:
        await db.rollback()
    else:
        await db.commit()
    return report
