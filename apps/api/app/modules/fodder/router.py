import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.fodder import schemas, service
from app.modules.identity.deps import get_user_permissions, require_permission
from app.modules.identity.models import User

router = APIRouter(prefix="/api/v1/fodder", tags=["fodder"])
READ, RECORD, MANAGE = require_permission("fodder.read"), require_permission("fodder.record"), require_permission("fodder.manage")


# ---- products and the 'would have bought' prices
@router.get("/products")
async def products(active_only: bool = Query(False), user: User = Depends(READ), db: AsyncSession = Depends(get_db)):
    return await service.list_products(db, user.organization_id, active_only)


@router.post("/products", status_code=201)
async def create_product(req: schemas.ProductCreate, user: User = Depends(MANAGE), db: AsyncSession = Depends(get_db)):
    return await service.create_product(db, user.organization_id, req)


@router.patch("/products/{product_id}")
async def update_product(product_id: uuid.UUID, req: schemas.ProductUpdate, user: User = Depends(MANAGE), db: AsyncSession = Depends(get_db)):
    return await service.update_product(db, user.organization_id, product_id, req)


@router.post("/products/{product_id}/prices", status_code=201)
async def add_price(product_id: uuid.UUID, req: schemas.PriceCreate, user: User = Depends(MANAGE), db: AsyncSession = Depends(get_db)):
    return await service.add_price(db, user.organization_id, product_id, req)


# ---- plots and production cycles
@router.get("/plots")
async def plots(user: User = Depends(READ), db: AsyncSession = Depends(get_db)):
    return await service.list_plots(db, user.organization_id)


@router.post("/plots", status_code=201)
async def create_plot(req: schemas.PlotCreate, user: User = Depends(MANAGE), db: AsyncSession = Depends(get_db)):
    return await service.create_plot(db, user.organization_id, req)


@router.patch("/plots/{plot_id}")
async def update_plot(plot_id: uuid.UUID, req: schemas.PlotUpdate, user: User = Depends(MANAGE), db: AsyncSession = Depends(get_db)):
    return await service.update_plot(db, user.organization_id, plot_id, req)


@router.get("/cycles")
async def cycles(state: str | None = Query(None, pattern="^(open|closed)$"), as_of: date | None = Query(None), user: User = Depends(READ), db: AsyncSession = Depends(get_db)):
    return await service.list_cycles(db, user.organization_id, state, as_of)


@router.post("/cycles", status_code=201)
async def create_cycle(req: schemas.CycleCreate, user: User = Depends(MANAGE), db: AsyncSession = Depends(get_db)):
    return await service.create_cycle(db, user.organization_id, req)


@router.get("/cycles/{cycle_id}")
async def cycle_detail(cycle_id: uuid.UUID, as_of: date | None = Query(None), user: User = Depends(READ), db: AsyncSession = Depends(get_db)):
    return await service.cycle_detail(db, user.organization_id, cycle_id, as_of)


@router.post("/cycles/{cycle_id}/close")
async def close_cycle(cycle_id: uuid.UUID, req: schemas.CycleClose, user: User = Depends(MANAGE), db: AsyncSession = Depends(get_db)):
    return await service.close_cycle(db, user.organization_id, cycle_id, req)


@router.post("/cycles/{cycle_id}/costs", status_code=201)
async def add_cost(cycle_id: uuid.UUID, req: schemas.CostCreate, user: User = Depends(RECORD), db: AsyncSession = Depends(get_db)):
    return await service.add_cost(db, user.organization_id, user.id, cycle_id, req)


@router.post("/cycles/{cycle_id}/harvests", status_code=201)
async def add_harvest(cycle_id: uuid.UUID, req: schemas.HarvestCreate, user: User = Depends(RECORD), db: AsyncSession = Depends(get_db)):
    return await service.add_harvest(db, user.organization_id, user.id, cycle_id, req)


# ---- amortised investments
@router.get("/investments")
async def investments(as_of: date | None = Query(None), user: User = Depends(READ), db: AsyncSession = Depends(get_db)):
    return await service.investment_schedule(db, user.organization_id, as_of)


@router.post("/investments", status_code=201)
async def create_investment(req: schemas.InvestmentCreate, user: User = Depends(MANAGE), db: AsyncSession = Depends(get_db)):
    return await service.create_investment(db, user.organization_id, req)


@router.post("/investments/{investment_id}/dispose")
async def dispose_investment(investment_id: uuid.UUID, req: schemas.InvestmentDispose, user: User = Depends(MANAGE), db: AsyncSession = Depends(get_db)):
    return await service.dispose_investment(db, user.organization_id, investment_id, req)


# ---- stock
@router.get("/stock")
async def stock(as_of: date | None = Query(None), user: User = Depends(READ), db: AsyncSession = Depends(get_db)):
    return await service.stock_position(db, user.organization_id, as_of)


@router.get("/movements")
async def movements(product_id: uuid.UUID | None = Query(None), start_date: date | None = Query(None), end_date: date | None = Query(None),
                    user: User = Depends(READ), db: AsyncSession = Depends(get_db)):
    return await service.list_movements(db, user.organization_id, product_id, start_date, end_date)


@router.post("/movements", status_code=201)
async def add_movement(req: schemas.MovementCreate, user: User = Depends(RECORD), db: AsyncSession = Depends(get_db)):
    """Issues, losses and stock counts need `fodder.record`; purchases and sales move money so they need `fodder.manage`."""
    if req.movement_type in ("purchase", "sale") and "fodder.manage" not in await get_user_permissions(db, user):
        raise HTTPException(403, "Missing required permission: fodder.manage")
    return await service.add_movement(db, user.organization_id, user.id, req)


@router.get("/summary")
async def summary(start_date: date = Query(...), end_date: date = Query(...), user: User = Depends(READ), db: AsyncSession = Depends(get_db)):
    return await service.summary(db, user.organization_id, start_date, end_date)
