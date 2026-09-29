import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.modules.identity.deps import require_permission
from app.modules.identity.models import User
from app.modules.farm import schemas
from app.modules.farm.models import Farm, Branch, Location

router = APIRouter(prefix="/api/v1/farms", tags=["farms"])


async def _get_owned_farm(db: AsyncSession, farm_id: uuid.UUID, org_id: uuid.UUID) -> Farm:
    result = await db.execute(
        select(Farm)
        .options(selectinload(Farm.branches).selectinload(Branch.locations))
        .where(Farm.id == farm_id, Farm.organization_id == org_id)  # tenant isolation (spec §52.13)
    )
    farm = result.scalar_one_or_none()
    if not farm:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Farm not found")
    return farm


@router.get("", response_model=list[schemas.FarmOut])
async def list_farms(
    user: User = Depends(require_permission("farm.manage")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Farm)
        .options(selectinload(Farm.branches).selectinload(Branch.locations))
        .where(Farm.organization_id == user.organization_id)
    )
    return result.scalars().all()


@router.post("", response_model=schemas.FarmOut, status_code=status.HTTP_201_CREATED)
async def create_farm(
    req: schemas.FarmCreate,
    user: User = Depends(require_permission("farm.manage")),
    db: AsyncSession = Depends(get_db),
):
    farm = Farm(organization_id=user.organization_id, **req.model_dump())
    db.add(farm)
    await db.commit()
    await db.refresh(farm)
    return farm


@router.get("/{farm_id}", response_model=schemas.FarmOut)
async def get_farm(
    farm_id: uuid.UUID,
    user: User = Depends(require_permission("farm.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await _get_owned_farm(db, farm_id, user.organization_id)


@router.post("/{farm_id}/branches", response_model=schemas.BranchOut, status_code=status.HTTP_201_CREATED)
async def create_branch(
    farm_id: uuid.UUID,
    req: schemas.BranchCreate,
    user: User = Depends(require_permission("farm.manage")),
    db: AsyncSession = Depends(get_db),
):
    await _get_owned_farm(db, farm_id, user.organization_id)  # ensures tenant ownership
    branch = Branch(farm_id=farm_id, name=req.name)
    db.add(branch)
    await db.commit()
    await db.refresh(branch)
    return branch


@router.post(
    "/{farm_id}/branches/{branch_id}/locations",
    response_model=schemas.LocationOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_location(
    farm_id: uuid.UUID,
    branch_id: uuid.UUID,
    req: schemas.LocationCreate,
    user: User = Depends(require_permission("farm.manage")),
    db: AsyncSession = Depends(get_db),
):
    farm = await _get_owned_farm(db, farm_id, user.organization_id)
    if not any(b.id == branch_id for b in farm.branches):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Branch not found on this farm")
    location = Location(branch_id=branch_id, name=req.name, location_type=req.location_type)
    db.add(location)
    await db.commit()
    await db.refresh(location)
    return location
