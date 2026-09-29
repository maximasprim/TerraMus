import uuid
from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assets.models import Asset, AssetMaintenanceRecord, AssetCounter
from app.modules.assets import schemas


async def _next_asset_number(db: AsyncSession, org_id: uuid.UUID) -> str:
    """Row-locked per-org counter - same mechanism as every other counter in
    this codebase (finance.InvoiceCounter, procurement.PurchaseOrderCounter,
    employees.EmployeeCounter)."""
    result = await db.execute(
        select(AssetCounter).where(AssetCounter.organization_id == org_id).with_for_update()
    )
    counter = result.scalar_one_or_none()
    if not counter:
        counter = AssetCounter(organization_id=org_id, next_number=1)
        db.add(counter)
        await db.flush()
    number = counter.next_number
    counter.next_number += 1
    from app.modules.identity.service import get_organization
    org = await get_organization(db, org_id)
    return f"{org.asset_prefix}-{number:06d}"  # spec §60 - prefix is now org-configurable


def depreciated_value(asset: Asset, as_of: date | None = None) -> Decimal | None:
    """Straight-line depreciation (spec §15). Returns None when there isn't
    enough information to compute one (no acquisition cost, or depreciation
    inputs deliberately left unset - see models.py's Asset docstring), in
    which case the caller falls back to acquisition_cost as current_value.

    current_value = acquisition_cost
                    - (acquisition_cost - salvage_value) * min(years_elapsed, useful_life_years) / useful_life_years

    Floored at salvage_value; never negative, never above acquisition_cost.
    """
    if asset.acquisition_cost is None or asset.useful_life_years is None or asset.acquisition_date is None:
        return None
    salvage = asset.salvage_value if asset.salvage_value is not None else Decimal("0")
    today = as_of or date.today()
    years_elapsed = Decimal(str((today - asset.acquisition_date).days)) / Decimal("365.25")
    years_elapsed = max(Decimal("0"), min(years_elapsed, Decimal(asset.useful_life_years)))

    depreciable_base = Decimal(str(asset.acquisition_cost)) - Decimal(str(salvage))
    depreciation = depreciable_base * years_elapsed / Decimal(asset.useful_life_years)
    value = Decimal(str(asset.acquisition_cost)) - depreciation
    return value.quantize(Decimal("0.01"))


def _to_out(asset: Asset) -> schemas.AssetOut:
    current_value = depreciated_value(asset)
    if current_value is None and asset.acquisition_cost is not None:
        current_value = Decimal(str(asset.acquisition_cost))
    total_maintenance_cost = sum(
        (Decimal(str(r.cost)) for r in asset.maintenance_records if r.cost is not None), Decimal("0")
    ).quantize(Decimal("0.01"))
    return schemas.AssetOut(
        id=asset.id, organization_id=asset.organization_id, asset_number=asset.asset_number,
        name=asset.name, asset_type=asset.asset_type, serial_number=asset.serial_number,
        status=asset.status, condition=asset.condition,
        acquisition_date=asset.acquisition_date, acquisition_cost=asset.acquisition_cost,
        useful_life_years=asset.useful_life_years, salvage_value=asset.salvage_value,
        warranty_expiry=asset.warranty_expiry, assigned_farm_id=asset.assigned_farm_id,
        assigned_location_id=asset.assigned_location_id, supplier_id=asset.supplier_id,
        notes=asset.notes, created_at=asset.created_at,
        current_value=current_value, total_maintenance_cost=total_maintenance_cost,
    )


async def create_asset(db: AsyncSession, org_id: uuid.UUID, req: schemas.AssetCreate) -> schemas.AssetOut:
    asset_number = await _next_asset_number(db, org_id)
    asset = Asset(organization_id=org_id, asset_number=asset_number, **req.model_dump())
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return _to_out(asset)


async def get_asset(db: AsyncSession, org_id: uuid.UUID, asset_id: uuid.UUID) -> Asset:
    result = await db.execute(select(Asset).where(Asset.id == asset_id, Asset.organization_id == org_id))
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Asset not found")
    return asset


async def get_asset_detail(db: AsyncSession, org_id: uuid.UUID, asset_id: uuid.UUID) -> schemas.AssetDetailOut:
    asset = await get_asset(db, org_id, asset_id)
    base = _to_out(asset)
    return schemas.AssetDetailOut(**base.model_dump(), maintenance_records=list(asset.maintenance_records))


async def list_assets(
    db: AsyncSession, org_id: uuid.UUID, asset_type: str | None = None,
    status_filter: str | None = None, assigned_farm_id: uuid.UUID | None = None, search: str | None = None,
) -> list[schemas.AssetOut]:
    query = select(Asset).where(Asset.organization_id == org_id)
    if asset_type:
        query = query.where(Asset.asset_type == asset_type)
    if status_filter:
        query = query.where(Asset.status == status_filter)
    if assigned_farm_id:
        query = query.where(Asset.assigned_farm_id == assigned_farm_id)
    if search:
        like = f"%{search}%"
        query = query.where((Asset.name.ilike(like)) | (Asset.asset_number.ilike(like)) | (Asset.serial_number.ilike(like)))
    result = await db.execute(query.order_by(Asset.name))
    return [_to_out(a) for a in result.scalars().all()]


async def update_asset(
    db: AsyncSession, org_id: uuid.UUID, asset_id: uuid.UUID, req: schemas.AssetUpdate,
) -> schemas.AssetOut:
    asset = await get_asset(db, org_id, asset_id)
    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(asset, field, value)
    await db.commit()
    await db.refresh(asset)
    return _to_out(asset)


async def add_maintenance_record(
    db: AsyncSession, org_id: uuid.UUID, asset_id: uuid.UUID, req: schemas.MaintenanceRecordCreate,
) -> AssetMaintenanceRecord:
    asset = await get_asset(db, org_id, asset_id)  # 404s if not in this org
    record = AssetMaintenanceRecord(asset_id=asset.id, **req.model_dump())
    db.add(record)
    # A record of type 'repair' or 'service' implies the asset was just
    # worked on - nudge status back to in_use if it had been flagged
    # under_maintenance, mirroring how commerce/livestock status changes are
    # a side effect of the real-world event, not a separate manual step.
    if asset.status == "under_maintenance" and req.maintenance_type in ("service", "repair"):
        asset.status = "in_use"
    await db.commit()
    await db.refresh(record)
    return record


async def list_maintenance_records(
    db: AsyncSession, org_id: uuid.UUID, asset_id: uuid.UUID,
) -> list[AssetMaintenanceRecord]:
    asset = await get_asset(db, org_id, asset_id)
    return list(asset.maintenance_records)
