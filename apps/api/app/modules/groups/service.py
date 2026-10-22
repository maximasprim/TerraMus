import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.customers.models import Customer
from app.modules.finance.models import FinanceTransaction
from app.modules.groups import schemas
from app.modules.groups.models import AnimalGroup, GroupRecord
from app.modules.receivables.models import AccountEntry

D = lambda x: Decimal(str(x))
_ACTIVITY = {"poultry": "poultry", "rabbits": "rabbits", "fish": "fish"}


def _sale_category(species: str, product: str | None) -> str:
    if product == "eggs": return "egg_sale"
    return {"fish": "fish_sale", "rabbits": "rabbit_sale", "poultry": "poultry_sale"}.get(species, "other_revenue")


def _group_out(g: AnimalGroup) -> dict:
    return {"id": str(g.id), "code": g.code, "name": g.name, "species": g.species, "purpose": g.purpose, "breed": g.breed,
            "source": g.source, "farm_id": str(g.farm_id) if g.farm_id else None, "start_date": g.start_date.isoformat(),
            "initial_count": g.initial_count, "current_count": g.current_count, "acquisition_cost": float(g.acquisition_cost),
            "status": g.status, "closed_on": g.closed_on.isoformat() if g.closed_on else None, "notes": g.notes}


async def _get(db, org_id, group_id) -> AnimalGroup:
    g = (await db.execute(select(AnimalGroup).where(AnimalGroup.id == group_id, AnimalGroup.organization_id == org_id))).scalar_one_or_none()
    if not g:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Group not found")
    return g


async def create_group(db, org_id, req: schemas.GroupCreate) -> dict:
    if (await db.execute(select(AnimalGroup.id).where(AnimalGroup.organization_id == org_id, AnimalGroup.code == req.code))).first():
        raise HTTPException(status.HTTP_409_CONFLICT, f"A group with code '{req.code}' already exists")
    g = AnimalGroup(organization_id=org_id, current_count=req.initial_count, **req.model_dump())
    db.add(g); await db.commit()
    return _group_out(g)


async def list_groups(db, org_id, species=None, state=None) -> list[dict]:
    q = select(AnimalGroup).where(AnimalGroup.organization_id == org_id).order_by(AnimalGroup.start_date.desc())
    if species: q = q.where(AnimalGroup.species == species)
    if state: q = q.where(AnimalGroup.status == state)
    return [_group_out(g) for g in (await db.execute(q)).scalars()]


async def add_record(db, org_id, user_id, group_id, req: schemas.RecordCreate) -> dict:
    g = await _get(db, org_id, group_id)
    if g.status == "closed":
        raise HTTPException(status.HTTP_409_CONFLICT, "This group is closed; no more records can be added")
    if req.record_date < g.start_date:
        raise HTTPException(422, f"record_date is before the group started ({g.start_date})")
    qty = int(req.quantity) if req.record_type in ("mortality", "cull", "addition") else req.quantity
    heads_out = 0
    if req.record_type in ("mortality", "cull"):
        heads_out = qty
    elif req.record_type == "sale" and (req.product == "live" or (req.unit or "") == "head"):
        heads_out = int(req.quantity)
    if heads_out > g.current_count:
        raise HTTPException(422, f"Only {g.current_count} animals are left in this group (tried to remove {heads_out})")
    if req.customer_id and not (await db.execute(select(Customer.id).where(Customer.id == req.customer_id, Customer.organization_id == org_id))).first():
        raise HTTPException(404, "Customer not found")
    g.current_count += (qty if req.record_type == "addition" else 0) - heads_out
    r = GroupRecord(organization_id=org_id, group_id=g.id, created_by=user_id, **req.model_dump())
    db.add(r); await db.flush()
    posted = None
    if req.record_type == "sale":   # same transaction as the record: no sale without its ledger entry
        activity = _ACTIVITY.get(g.species, "general")
        desc = f"{g.name}: {req.quantity:g} {req.unit or req.product or ''}".strip()
        if req.customer_id:
            db.add(AccountEntry(organization_id=org_id, customer_id=req.customer_id, entry_type="charge", amount=req.value, entry_date=req.record_date,
                                reference_type="group_sale", reference_id=r.id, description=desc, farm_id=g.farm_id, activity=activity, created_by=user_id))
            posted = "charged_to_customer_account"
        else:
            db.add(FinanceTransaction(organization_id=org_id, transaction_type="income", category=_sale_category(g.species, req.product),
                                      amount=req.value, transaction_date=req.record_date, farm_id=g.farm_id, activity=activity, description=desc,
                                      reference_type="group_sale", reference_id=r.id, created_by=user_id))
            posted = "income_posted"
    warn = None
    if g.current_count == 0 and g.status == "active":
        warn = "No animals left; consider closing the group"
    await db.commit()
    return {"id": str(r.id), "current_count": g.current_count, "ledger": posted, **({"warning": warn} if warn else {})}


async def list_records(db, org_id, group_id, record_type=None, start=None, end=None, limit=500) -> list[dict]:
    await _get(db, org_id, group_id)
    q = select(GroupRecord).where(GroupRecord.group_id == group_id, GroupRecord.organization_id == org_id)
    if record_type: q = q.where(GroupRecord.record_type == record_type)
    if start: q = q.where(GroupRecord.record_date >= start)
    if end: q = q.where(GroupRecord.record_date <= end)
    rows = (await db.execute(q.order_by(GroupRecord.record_date.desc(), GroupRecord.created_at.desc()).limit(limit))).scalars()
    return [{"id": str(r.id), "date": r.record_date.isoformat(), "type": r.record_type, "quantity": float(r.quantity), "unit": r.unit,
             "value": float(r.value) if r.value is not None else None, "avg_weight_kg": float(r.avg_weight_kg) if r.avg_weight_kg else None,
             "product": r.product, "notes": r.notes} for r in rows]


async def close_group(db, org_id, group_id, req: schemas.GroupClose) -> dict:
    g = await _get(db, org_id, group_id)
    if g.status == "closed":
        raise HTTPException(409, "Group is already closed")
    if req.closed_on < g.start_date:
        raise HTTPException(422, "closed_on is before the group started")
    g.status, g.closed_on = "closed", req.closed_on
    if req.notes: g.notes = ((g.notes + "\n") if g.notes else "") + req.notes
    await db.commit()
    return _group_out(g)


async def performance(db, org_id, group_id, as_of: date | None = None) -> dict:
    g = await _get(db, org_id, group_id)
    as_of = as_of or g.closed_on or date.today()
    recs = list((await db.execute(select(GroupRecord).where(GroupRecord.group_id == g.id, GroupRecord.record_date <= as_of)
                                  .order_by(GroupRecord.record_date))).scalars())
    sums = defaultdict(lambda: Decimal("0"))
    prod_by_unit = defaultdict(lambda: Decimal("0"))
    sold_kg = Decimal("0")
    for r in recs:
        sums[r.record_type] += D(r.quantity)
        if r.record_type == "production": prod_by_unit[r.unit or "units"] += D(r.quantity)
        if r.record_type == "sale" and (r.unit or "") == "kg": sold_kg += D(r.quantity)
    revenue = sum((D(r.value) for r in recs if r.record_type == "sale"), Decimal("0"))
    feed_cost = sum((D(r.value) for r in recs if r.record_type == "feed" and r.value), Decimal("0"))
    additions = int(sums["addition"])
    exposure = g.initial_count + additions
    lost = int(sums["mortality"] + sums["cull"])
    days = max((as_of - g.start_date).days, 1)
    weights = [r for r in recs if r.record_type == "weight_sample" and r.avg_weight_kg]
    latest_w = float(weights[-1].avg_weight_kg) if weights else None
    biomass = (g.current_count * latest_w) if latest_w else None
    out = {"group": _group_out(g), "as_of": as_of.isoformat(), "days": days,
           "mortality": {"died": int(sums["mortality"]), "culled": int(sums["cull"]), "total_lost": lost,
                         "mortality_pct": round(100 * float(sums["mortality"]) / exposure, 2), "loss_pct": round(100 * lost / exposure, 2)},
           "feed_kg": float(sums["feed"]), "feed_cost": float(feed_cost),
           "production": {u: float(v) for u, v in prod_by_unit.items()},
           "latest_avg_weight_kg": latest_w, "estimated_biomass_kg": round(biomass, 1) if biomass else None,
           "economics": {"revenue": float(revenue), "acquisition_cost": float(g.acquisition_cost), "feed_cost": float(feed_cost),
                         "margin": float(revenue - D(g.acquisition_cost) - feed_cost)}}
    eggs = prod_by_unit.get("eggs", Decimal("0"))
    if g.species == "poultry" and eggs > 0:
        first, last = next(r.record_date for r in recs if r.record_type == "production"), [r.record_date for r in recs if r.record_type == "production"][-1]
        span = max((last - first).days + 1, 1)
        avg_birds = (g.initial_count + g.current_count) / 2
        out["egg_production"] = {"eggs": float(eggs), "recording_days": span, "avg_birds": avg_birds,
                                 "hen_day_pct": round(100 * float(eggs) / (avg_birds * span), 1), "eggs_per_bird": round(float(eggs) / avg_birds, 1)}
    denom = (biomass or 0) + float(sold_kg) + float(prod_by_unit.get("kg", 0))
    if denom > 0 and sums["feed"] > 0:
        out["approx_fcr"] = round(float(sums["feed"]) / denom, 2)
        out["fcr_note"] = "feed kg ÷ (estimated biomass now + kg sold + kg harvested); weigh samples regularly to keep it accurate"
    total_units = sum(prod_by_unit.values(), Decimal("0"))
    if total_units > 0 and feed_cost > 0:
        out["feed_cost_per_unit_produced"] = round(float(feed_cost / total_units), 2)
    return out
