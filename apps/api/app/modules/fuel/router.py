import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.assets.models import Asset
from app.modules.finance.models import FinanceTransaction
from app.modules.fuel.models import FuelLog
from app.modules.identity.deps import require_permission
from app.modules.identity.models import User

router = APIRouter(prefix="/api/v1/fuel", tags=["fuel"])
ACTIVITY = "^(livestock|feedlot|dairy|crops|fodder|poultry|fish|rabbits|training|general)$"


class FuelCreate(BaseModel):
    asset_id: uuid.UUID
    log_date: date
    litres: Decimal = Field(gt=0, le=5000)
    cost: Decimal = Field(default=Decimal("0"), ge=0)
    meter_reading: Decimal | None = Field(default=None, ge=0)
    purpose: str | None = Field(default=None, max_length=120)
    activity: str | None = Field(default=None, pattern=ACTIVITY)
    farm_id: uuid.UUID | None = None
    driver: str | None = Field(default=None, max_length=120)
    post_to_finance: bool = True


def _out(f: FuelLog, asset_name: str | None = None) -> dict:
    return {"id": str(f.id), "asset_id": str(f.asset_id), "asset": asset_name, "date": f.log_date.isoformat(), "litres": float(f.litres),
            "cost": float(f.cost), "cost_per_litre": round(float(f.cost) / float(f.litres), 2) if f.litres else None,
            "meter_reading": float(f.meter_reading) if f.meter_reading is not None else None, "purpose": f.purpose,
            "activity": f.activity, "driver": f.driver}


@router.post("", status_code=201)
async def log_fuel(req: FuelCreate, user: User = Depends(require_permission("assets.manage")), db: AsyncSession = Depends(get_db)):
    asset = (await db.execute(select(Asset).where(Asset.id == req.asset_id, Asset.organization_id == user.organization_id))).scalar_one_or_none()
    if not asset:
        raise HTTPException(404, "Asset not found")
    farm_id = req.farm_id or asset.assigned_farm_id
    f = FuelLog(organization_id=user.organization_id, asset_id=asset.id, farm_id=farm_id, log_date=req.log_date, litres=req.litres,
                cost=req.cost, meter_reading=req.meter_reading, purpose=req.purpose, activity=req.activity, driver=req.driver, created_by=user.id)
    db.add(f); await db.flush()
    if req.post_to_finance and req.cost > 0:     # same transaction: the expense can't be missing
        t = FinanceTransaction(organization_id=user.organization_id, transaction_type="expense", category="fuel", amount=req.cost,
                               transaction_date=req.log_date, farm_id=farm_id, activity=req.activity,
                               description=f"Fuel: {asset.name} {float(req.litres):g}L", reference_type="fuel_log", reference_id=f.id, created_by=user.id)
        db.add(t); await db.flush(); f.finance_transaction_id = t.id
    await db.commit()
    return _out(f, asset.name)


@router.get("")
async def list_fuel(asset_id: uuid.UUID | None = Query(None), start_date: date | None = Query(None), end_date: date | None = Query(None),
                    user: User = Depends(require_permission("assets.manage")), db: AsyncSession = Depends(get_db)):
    q = select(FuelLog, Asset.name).join(Asset, Asset.id == FuelLog.asset_id).where(FuelLog.organization_id == user.organization_id)
    if asset_id: q = q.where(FuelLog.asset_id == asset_id)
    if start_date: q = q.where(FuelLog.log_date >= start_date)
    if end_date: q = q.where(FuelLog.log_date <= end_date)
    return [_out(f, n) for f, n in (await db.execute(q.order_by(FuelLog.log_date.desc()).limit(1000))).all()]


@router.get("/summary")
async def fuel_summary(start_date: date = Query(...), end_date: date = Query(...), user: User = Depends(require_permission("assets.manage")),
                       db: AsyncSession = Depends(get_db)):
    """Litres, cost and consumption per asset (litres per hour/km from consecutive meter readings)."""
    rows = (await db.execute(select(FuelLog, Asset.name).join(Asset, Asset.id == FuelLog.asset_id).where(
        FuelLog.organization_id == user.organization_id, FuelLog.log_date >= start_date, FuelLog.log_date <= end_date)
        .order_by(FuelLog.log_date, FuelLog.created_at))).all()
    per, month = defaultdict(lambda: {"litres": Decimal("0"), "cost": Decimal("0"), "fills": 0, "readings": []}), defaultdict(lambda: {"litres": Decimal("0"), "cost": Decimal("0")})
    act = defaultdict(lambda: Decimal("0"))
    for f, name in rows:
        p = per[(str(f.asset_id), name)]
        p["litres"] += f.litres; p["cost"] += f.cost; p["fills"] += 1
        if f.meter_reading is not None: p["readings"].append((float(f.meter_reading), float(f.litres)))
        m = month[f.log_date.strftime("%Y-%m")]; m["litres"] += f.litres; m["cost"] += f.cost
        act[f.activity or "unassigned"] += f.cost
    assets = []
    for (aid, name), p in per.items():
        eff = None
        if len(p["readings"]) >= 2:    # litres put in AFTER the first reading cover the distance/hours since it
            used = sum(l for _, l in p["readings"][1:]); span = p["readings"][-1][0] - p["readings"][0][0]
            eff = round(used / span, 2) if span > 0 else None
        assets.append({"asset_id": aid, "asset": name, "fills": p["fills"], "litres": float(p["litres"]), "cost": float(p["cost"]),
                       "avg_cost_per_litre": round(float(p["cost"] / p["litres"]), 2) if p["litres"] else None, "litres_per_meter_unit": eff})
    return {"start_date": start_date, "end_date": end_date, "total_litres": float(sum((a["litres"] for a in assets), 0)),
            "total_cost": float(sum((a["cost"] for a in assets), 0)), "by_asset": sorted(assets, key=lambda a: -a["cost"]),
            "by_month": [{"month": k, "litres": float(v["litres"]), "cost": float(v["cost"])} for k, v in sorted(month.items())],
            "cost_by_activity": {k: float(v) for k, v in act.items()}}
