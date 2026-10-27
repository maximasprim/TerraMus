import uuid
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.customers.models import Customer
from app.modules.finance.models import FinanceTransaction
from app.modules.fodder import engine, schemas
from app.modules.fodder.models import (
    FodderCost, FodderCycle, FodderHarvest, FodderInvestment, FodderMovement, FodderPlot, FodderPrice, FodderProduct,
)
from app.modules.receivables.models import AccountEntry

D = lambda x: Decimal(str(x))
F = lambda x: float(x)
_COST_TO_LEDGER = {"seed": "seed", "fertilizer": "fertilizer", "chemicals": "chemicals", "labour": "labour", "fuel": "fuel",
                   "machinery_hire": "equipment", "irrigation": "utilities", "transport": "transport", "packaging": "other_expense", "other": "other_expense"}


def _404(what): return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found")


async def _one(db, model, org_id, id_, what):
    r = (await db.execute(select(model).where(model.id == id_, model.organization_id == org_id))).scalar_one_or_none()
    if not r:
        raise _404(what)
    return r


# ----------------------------------------------------------------------- products & prices
def _product_out(p: FodderProduct, price: float | None = None) -> dict:
    return {"id": str(p.id), "name": p.name, "category": p.category, "unit_label": p.unit_label, "kg_per_unit": F(p.kg_per_unit),
            "dry_matter_pct": F(p.dry_matter_pct) if p.dry_matter_pct is not None else None, "reorder_days": p.reorder_days,
            "is_active": p.is_active, "notes": p.notes, "current_price_per_kg": price}


async def _prices(db, org_id, product_id=None) -> dict[uuid.UUID, list[tuple[date, float]]]:
    q = select(FodderPrice).where(FodderPrice.organization_id == org_id)
    if product_id:
        q = q.where(FodderPrice.product_id == product_id)
    out = defaultdict(list)
    for p in (await db.execute(q)).scalars():
        out[p.product_id].append((p.effective_from, F(p.price_per_kg)))
    return out


async def list_products(db, org_id, active_only=False):
    q = select(FodderProduct).where(FodderProduct.organization_id == org_id).order_by(FodderProduct.name)
    if active_only:
        q = q.where(FodderProduct.is_active.is_(True))
    prices = await _prices(db, org_id)
    return [_product_out(p, engine.price_at(prices.get(p.id, []), date.today())) for p in (await db.execute(q)).scalars()]


async def create_product(db, org_id, req: schemas.ProductCreate):
    if (await db.execute(select(FodderProduct.id).where(FodderProduct.organization_id == org_id, func.lower(FodderProduct.name) == req.name.lower()))).first():
        raise HTTPException(status.HTTP_409_CONFLICT, f"A fodder product named '{req.name}' already exists")
    p = FodderProduct(organization_id=org_id, **req.model_dump())
    db.add(p); await db.commit()
    return _product_out(p)


async def update_product(db, org_id, product_id, req: schemas.ProductUpdate):
    p = await _one(db, FodderProduct, org_id, product_id, "Product")
    for k, v in req.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    await db.commit()
    return _product_out(p)


async def add_price(db, org_id, product_id, req: schemas.PriceCreate):
    await _one(db, FodderProduct, org_id, product_id, "Product")
    ex = (await db.execute(select(FodderPrice).where(FodderPrice.product_id == product_id, FodderPrice.effective_from == req.effective_from))).scalar_one_or_none()
    if ex:
        ex.price_per_kg, ex.source = req.price_per_kg, req.source          # re-quoting the same day corrects it
    else:
        db.add(FodderPrice(organization_id=org_id, product_id=product_id, **req.model_dump()))
    await db.commit()
    return {"prices": [{"effective_from": d.isoformat(), "price_per_kg": p} for d, p in sorted((await _prices(db, org_id, product_id))[product_id])]}


# ------------------------------------------------------------------------------------ plots
def _plot_out(p: FodderPlot, in_use: float = 0.0) -> dict:
    return {"id": str(p.id), "name": p.name, "acres": F(p.acres), "acres_in_use": round(in_use, 2), "acres_free": round(F(p.acres) - in_use, 2),
            "irrigated": p.irrigated, "crop": p.crop, "established_on": p.established_on.isoformat() if p.established_on else None,
            "status": p.status, "farm_id": str(p.farm_id) if p.farm_id else None, "notes": p.notes}


async def _acres_in_use(db, org_id) -> dict[uuid.UUID, float]:
    rows = await db.execute(select(FodderCycle.plot_id, func.sum(FodderCycle.acres)).where(FodderCycle.organization_id == org_id, FodderCycle.status == "open").group_by(FodderCycle.plot_id))
    return {pid: F(a) for pid, a in rows.all()}


async def list_plots(db, org_id):
    use = await _acres_in_use(db, org_id)
    return [_plot_out(p, use.get(p.id, 0.0)) for p in (await db.execute(select(FodderPlot).where(FodderPlot.organization_id == org_id).order_by(FodderPlot.name))).scalars()]


async def create_plot(db, org_id, req: schemas.PlotCreate):
    if (await db.execute(select(FodderPlot.id).where(FodderPlot.organization_id == org_id, func.lower(FodderPlot.name) == req.name.lower()))).first():
        raise HTTPException(status.HTTP_409_CONFLICT, f"A plot named '{req.name}' already exists")
    p = FodderPlot(organization_id=org_id, **req.model_dump())
    db.add(p); await db.commit()
    return _plot_out(p)


async def update_plot(db, org_id, plot_id, req: schemas.PlotUpdate):
    p = await _one(db, FodderPlot, org_id, plot_id, "Plot")
    data = req.model_dump(exclude_unset=True)
    if "acres" in data and data["acres"] < (await _acres_in_use(db, org_id)).get(p.id, 0.0):
        raise HTTPException(422, "The plot cannot be made smaller than the acres currently planted on it")
    for k, v in data.items():
        setattr(p, k, v)
    await db.commit()
    return _plot_out(p, (await _acres_in_use(db, org_id)).get(p.id, 0.0))


# ----------------------------------------------------------------- cycles: costing & allocation
async def _engine_inputs(db, org_id, as_of: date):
    cycles = list((await db.execute(select(FodderCycle).where(FodderCycle.organization_id == org_id))).scalars())
    invs = list((await db.execute(select(FodderInvestment).where(FodderInvestment.organization_id == org_id))).scalars())
    alloc = engine.allocate_investments(
        [engine.Investment(str(i.id), str(i.plot_id) if i.plot_id else None, F(i.cost), F(i.salvage_value), i.in_service_on, F(i.life_years), i.disposed_on) for i in invs],
        [engine.Cycle(str(c.id), str(c.plot_id), F(c.acres), c.start_date, c.end_date) for c in cycles], as_of)
    return cycles, invs, alloc


async def _budget_targets(db, org_id) -> dict[str, tuple[float | None, float | None]]:
    """Target cost per kg and yield per acre from the enterprise budgets in Feedlot > Costing."""
    try:
        from app.modules.feedlot import metrics
        from app.modules.feedlot.models import CostingDocument
    except ImportError:
        return {}
    out = {}
    for d in (await db.execute(select(CostingDocument).where(CostingDocument.organization_id == org_id, CostingDocument.kind == "enterprise_budget"))).scalars():
        c = metrics.budget_cost(d.data)
        kg_per_acre = F(d.data.get("yield_per_year", 0)) * (F(d.data.get("unit_weight_kg", 1)) if d.data.get("unit_weight_kg") else 1)
        out[d.name] = (c["cost_per_kg"] if c["cost_per_kg"] is not None else None, kg_per_acre or None)
    return out


async def all_cycle_economics(db, org_id, as_of: date | None = None) -> dict[uuid.UUID, dict]:
    as_of = as_of or date.today()
    cycles, _, alloc = await _engine_inputs(db, org_id, as_of)
    products = {p.id: p for p in (await db.execute(select(FodderProduct).where(FodderProduct.organization_id == org_id))).scalars()}
    prices = await _prices(db, org_id)
    targets = await _budget_targets(db, org_id)
    direct = defaultdict(float)
    for cid, amt in (await db.execute(select(FodderCost.cycle_id, func.sum(FodderCost.amount)).where(FodderCost.organization_id == org_id, FodderCost.cost_date <= as_of).group_by(FodderCost.cycle_id))).all():
        direct[cid] = F(amt)
    harvests = defaultdict(list)
    for h in (await db.execute(select(FodderHarvest).where(FodderHarvest.organization_id == org_id, FodderHarvest.harvest_date <= as_of))).scalars():
        harvests[h.cycle_id].append((h.harvest_date, F(h.kg)))
    out = {}
    for c in cycles:
        if c.start_date > as_of:
            continue
        prod = products[c.product_id]
        tc, ty = targets.get(c.budget_name or "", (None, None))
        out[c.id] = engine.cycle_economics(F(c.acres), direct[c.id], alloc["by_cycle"].get(str(c.id), 0.0), harvests.get(c.id, []), prices.get(prod.id, []),
                                           F(prod.kg_per_unit), tc, ty)
    return out


def _cycle_out(c: FodderCycle, plot: FodderPlot, prod: FodderProduct, econ: dict | None) -> dict:
    return {"id": str(c.id), "label": c.label, "plot_id": str(c.plot_id), "plot": plot.name, "product_id": str(c.product_id), "product": prod.name,
            "unit_label": prod.unit_label, "start_date": c.start_date.isoformat(), "end_date": c.end_date.isoformat() if c.end_date else None,
            "acres": F(c.acres), "status": c.status, "budget_name": c.budget_name, "notes": c.notes, "economics": econ}


async def list_cycles(db, org_id, state: str | None = None, as_of: date | None = None):
    q = select(FodderCycle, FodderPlot, FodderProduct).join(FodderPlot, FodderPlot.id == FodderCycle.plot_id).join(FodderProduct, FodderProduct.id == FodderCycle.product_id) \
        .where(FodderCycle.organization_id == org_id).order_by(FodderCycle.start_date.desc())
    if state:
        q = q.where(FodderCycle.status == state)
    econ = await all_cycle_economics(db, org_id, as_of)
    return [_cycle_out(c, p, pr, econ.get(c.id)) for c, p, pr in (await db.execute(q)).all()]


async def create_cycle(db, org_id, req: schemas.CycleCreate):
    plot = await _one(db, FodderPlot, org_id, req.plot_id, "Plot")
    prod = await _one(db, FodderProduct, org_id, req.product_id, "Product")
    acres = D(req.acres if req.acres is not None else plot.acres)
    free = F(plot.acres) - (await _acres_in_use(db, org_id)).get(plot.id, 0.0)
    if plot.status == "retired":
        raise HTTPException(409, "This plot is retired")
    if F(acres) > free + 1e-9:
        raise HTTPException(422, f"Only {free:g} acres of {plot.name} are free (the rest is planted in an open cycle). Close that cycle first or plant fewer acres.")
    c = FodderCycle(organization_id=org_id, plot_id=plot.id, product_id=prod.id, label=req.label, start_date=req.start_date, acres=acres, budget_name=req.budget_name, notes=req.notes)
    db.add(c); await db.commit()
    return _cycle_out(c, plot, prod, None)


async def cycle_detail(db, org_id, cycle_id, as_of: date | None = None):
    c = await _one(db, FodderCycle, org_id, cycle_id, "Cycle")
    plot, prod = await _one(db, FodderPlot, org_id, c.plot_id, "Plot"), await _one(db, FodderProduct, org_id, c.product_id, "Product")
    econ = (await all_cycle_economics(db, org_id, as_of)).get(c.id)
    costs = (await db.execute(select(FodderCost).where(FodderCost.cycle_id == c.id).order_by(FodderCost.cost_date, FodderCost.created_at))).scalars().all()
    harv = (await db.execute(select(FodderHarvest).where(FodderHarvest.cycle_id == c.id).order_by(FodderHarvest.harvest_date))).scalars().all()
    by_cat = defaultdict(float)
    for x in costs:
        by_cat[x.category] += F(x.amount)
    out = _cycle_out(c, plot, prod, econ)
    out["costs"] = [{"id": str(x.id), "date": x.cost_date.isoformat(), "category": x.category, "amount": F(x.amount), "description": x.description} for x in costs]
    out["cost_by_category"] = {k: round(v, 2) for k, v in by_cat.items()}
    out["harvests"] = [{"id": str(h.id), "date": h.harvest_date.isoformat(), "quantity": F(h.quantity), "kg": F(h.kg), "quality": h.quality, "notes": h.notes} for h in harv]
    return out


async def close_cycle(db, org_id, cycle_id, req: schemas.CycleClose):
    c = await _one(db, FodderCycle, org_id, cycle_id, "Cycle")
    if c.status == "closed":
        raise HTTPException(409, "This cycle is already closed")
    last = (await db.execute(select(func.max(FodderHarvest.harvest_date)).where(FodderHarvest.cycle_id == c.id))).scalar_one()
    if req.end_date < c.start_date or (last and req.end_date < last):
        raise HTTPException(422, f"end_date cannot be before the cycle started or its last harvest ({last or c.start_date})")
    c.end_date, c.status = req.end_date, "closed"
    await db.commit()
    return await cycle_detail(db, org_id, c.id)


async def add_cost(db, org_id, user_id, cycle_id, req: schemas.CostCreate):
    c = await _one(db, FodderCycle, org_id, cycle_id, "Cycle")
    plot = await _one(db, FodderPlot, org_id, c.plot_id, "Plot")
    if c.end_date and req.cost_date > c.end_date:
        raise HTTPException(422, f"This cycle ended on {c.end_date}; later costs belong to a new cycle")
    row = FodderCost(organization_id=org_id, cycle_id=c.id, cost_date=req.cost_date, category=req.category, amount=req.amount, description=req.description, created_by=user_id)
    db.add(row); await db.flush()
    if req.post_to_finance:      # same transaction: the expense cannot be missing from the books
        t = FinanceTransaction(organization_id=org_id, transaction_type="expense", category=_COST_TO_LEDGER[req.category], amount=req.amount, transaction_date=req.cost_date,
                               farm_id=plot.farm_id, activity=schemas.ACTIVITY_FODDER, description=f"Fodder: {c.label} - {req.description or req.category}",
                               reference_type="fodder_cost", reference_id=row.id, created_by=user_id)
        db.add(t); await db.flush(); row.finance_transaction_id = t.id
    await db.commit()
    return {"id": str(row.id), "posted_to_finance": bool(row.finance_transaction_id)}


async def add_harvest(db, org_id, user_id, cycle_id, req: schemas.HarvestCreate):
    c = await _one(db, FodderCycle, org_id, cycle_id, "Cycle")
    prod = await _one(db, FodderProduct, org_id, c.product_id, "Product")
    if req.harvest_date < c.start_date or (c.end_date and req.harvest_date > c.end_date):
        raise HTTPException(422, f"The harvest date must fall inside the cycle ({c.start_date} to {c.end_date or 'now'})")
    kg = D(req.kg) if req.kg is not None else (D(req.quantity) * D(prod.kg_per_unit))
    h = FodderHarvest(organization_id=org_id, cycle_id=c.id, harvest_date=req.harvest_date, quantity=req.quantity, kg=kg, quality=req.quality, notes=req.notes, created_by=user_id)
    db.add(h); await db.flush()
    db.add(FodderMovement(organization_id=org_id, product_id=prod.id, movement_date=req.harvest_date, movement_type="harvest", kg_delta=kg,
                          reference_type="harvest", reference_id=h.id, reason=f"Harvest: {c.label}", created_by=user_id))
    await db.commit()
    return {"id": str(h.id), "kg": F(kg), "units": F(req.quantity), "unit_label": prod.unit_label}


# ----------------------------------------------------------------------- investments
def _inv_out(i: FodderInvestment, as_of: date, alloc: dict | None = None) -> dict:
    inv = engine.Investment(str(i.id), None, F(i.cost), F(i.salvage_value), i.in_service_on, F(i.life_years), i.disposed_on)
    done = engine.amortised_to_date(inv, as_of)
    out = {"id": str(i.id), "name": i.name, "plot_id": str(i.plot_id) if i.plot_id else None, "shared": i.plot_id is None, "cost": F(i.cost),
           "salvage_value": F(i.salvage_value), "in_service_on": i.in_service_on.isoformat(), "life_years": F(i.life_years),
           "disposed_on": i.disposed_on.isoformat() if i.disposed_on else None, "per_year": round(max(F(i.cost) - F(i.salvage_value), 0) / F(i.life_years), 2),
           "per_day": round(engine.daily_charge(inv), 2), "amortised_to_date": round(done, 2), "book_value": round(F(i.cost) - done, 2)}
    if alloc:
        out.update({"allocated_to_cycles": alloc["allocated"], "idle_capacity_cost": alloc["idle"]})
    return out


async def create_investment(db, org_id, req: schemas.InvestmentCreate):
    if req.plot_id:
        await _one(db, FodderPlot, org_id, req.plot_id, "Plot")
    i = FodderInvestment(organization_id=org_id, **req.model_dump())
    db.add(i); await db.commit()
    return _inv_out(i, date.today())


async def investment_schedule(db, org_id, as_of: date | None = None):
    as_of = as_of or date.today()
    _, invs, alloc = await _engine_inputs(db, org_id, as_of)
    rows = [_inv_out(i, as_of, alloc["by_investment"].get(str(i.id))) for i in sorted(invs, key=lambda x: x.in_service_on)]
    return {"as_of": as_of.isoformat(), "investments": rows, "totals": {
        "cost": round(sum(r["cost"] for r in rows), 2), "amortised_to_date": round(sum(r["amortised_to_date"] for r in rows), 2),
        "book_value": round(sum(r["book_value"] for r in rows), 2), "per_year": round(sum(r["per_year"] for r in rows if not r["disposed_on"]), 2),
        "allocated_to_cycles": round(sum(r.get("allocated_to_cycles", 0) for r in rows), 2), "idle_capacity_cost": round(sum(r.get("idle_capacity_cost", 0) for r in rows), 2)}}


async def dispose_investment(db, org_id, inv_id, req: schemas.InvestmentDispose):
    i = await _one(db, FodderInvestment, org_id, inv_id, "Investment")
    if req.disposed_on < i.in_service_on:
        raise HTTPException(422, "disposed_on is before the asset entered service")
    i.disposed_on = req.disposed_on
    await db.commit()
    return _inv_out(i, date.today())


# ----------------------------------------------------------------- stock ledger & valuation
async def _balances(db, org_id, as_of: date | None = None) -> dict[uuid.UUID, float]:
    q = select(FodderMovement.product_id, func.sum(FodderMovement.kg_delta)).where(FodderMovement.organization_id == org_id).group_by(FodderMovement.product_id)
    if as_of:
        q = q.where(FodderMovement.movement_date <= as_of)
    return {pid: F(kg) for pid, kg in (await db.execute(q)).all()}


async def _wac_by_product(db, org_id, econ: dict[uuid.UUID, dict]) -> dict[uuid.UUID, float | None]:
    """Weighted average cost per kg of everything that came IN: harvests at their cycle's current cost per kg, purchases at price paid."""
    layers = defaultdict(list)
    cyc_cost = {cid: e["cost_per_kg"] for cid, e in econ.items()}
    cyc_of_h = {h.id: h for h in (await db.execute(select(FodderHarvest).where(FodderHarvest.organization_id == org_id))).scalars()}
    for m in (await db.execute(select(FodderMovement).where(FodderMovement.organization_id == org_id, FodderMovement.movement_type.in_(("harvest", "purchase"))))).scalars():
        if m.movement_type == "purchase" and m.value:
            layers[m.product_id].append((F(m.kg_delta), F(m.value) / F(m.kg_delta)))
        elif m.movement_type == "harvest":
            h = cyc_of_h.get(m.reference_id)
            c = cyc_cost.get(h.cycle_id) if h else None
            if c is not None:
                layers[m.product_id].append((F(m.kg_delta), c))
    return {pid: engine.weighted_average_cost(l) for pid, l in layers.items()}


async def stock_position(db, org_id, as_of: date | None = None) -> list[dict]:
    as_of = as_of or date.today()
    econ = await all_cycle_economics(db, org_id, as_of)
    wac = await _wac_by_product(db, org_id, econ)
    bal = await _balances(db, org_id, as_of)
    prices = await _prices(db, org_id)
    since = as_of - timedelta(days=30)
    issued = {pid: -F(kg) for pid, kg in (await db.execute(select(FodderMovement.product_id, func.sum(FodderMovement.kg_delta)).where(
        FodderMovement.organization_id == org_id, FodderMovement.movement_type == "issue", FodderMovement.movement_date > since, FodderMovement.movement_date <= as_of).group_by(FodderMovement.product_id))).all()}
    first = {pid: d for pid, d in (await db.execute(select(FodderMovement.product_id, func.min(FodderMovement.movement_date)).where(
        FodderMovement.organization_id == org_id, FodderMovement.movement_type == "issue").group_by(FodderMovement.product_id))).all()}
    out = []
    for p in (await db.execute(select(FodderProduct).where(FodderProduct.organization_id == org_id).order_by(FodderProduct.name))).scalars():
        b = bal.get(p.id, 0.0)
        history = min((as_of - first[p.id]).days + 1, 30) if p.id in first else 0
        cover = engine.days_of_cover(b, issued.get(p.id, 0.0), history or 30, history_days=history) if history else None
        w = wac.get(p.id)
        price = engine.price_at(prices.get(p.id, []), as_of)
        out.append({"product_id": str(p.id), "name": p.name, "category": p.category, "unit_label": p.unit_label, "is_active": p.is_active,
                    "balance_kg": round(b, 2), "balance_units": round(b / F(p.kg_per_unit), 1), "avg_cost_per_kg": w,
                    "stock_value": round(b * w, 2) if w is not None and b > 0 else (0.0 if b <= 0 else None),
                    "market_price_per_kg": price, "replacement_value": round(b * price, 2) if price and b > 0 else None,
                    "issued_last_30d_kg": round(issued.get(p.id, 0.0), 2), "days_of_cover": cover, "reorder_days": p.reorder_days,
                    "low_cover": cover is not None and cover <= p.reorder_days})
    return out


async def cost_map(db, org_id) -> dict[str, float]:
    """Current average cost per kg of each fodder product by name: the live link into feedlot ration costing."""
    names = {p.id: p.name for p in (await db.execute(select(FodderProduct).where(FodderProduct.organization_id == org_id))).scalars()}
    econ = await all_cycle_economics(db, org_id)
    return {names[pid]: w for pid, w in (await _wac_by_product(db, org_id, econ)).items() if w is not None and pid in names}


async def add_movement(db, org_id, user_id, req: schemas.MovementCreate):
    prod = await _one(db, FodderProduct, org_id, req.product_id, "Product")
    kg = D(req.kg) if req.kg is not None else D(req.units) * D(prod.kg_per_unit)
    bal = (await _balances(db, org_id)).get(prod.id, 0.0)
    t = req.movement_type
    if req.customer_id and not (await db.execute(select(Customer.id).where(Customer.id == req.customer_id, Customer.organization_id == org_id))).first():
        raise _404("Customer")
    if t in ("issue", "sale", "loss") and F(kg) > bal + 1e-6:
        raise HTTPException(422, f"Only {bal:,.1f} kg of {prod.name} is in stock (tried to take {F(kg):,.1f} kg). Record the harvest or purchase first, or do a stock count.")
    result: dict = {}
    if t == "count":
        delta = kg - D(bal)                                  # the counted quantity IS the new balance
        if delta == 0:
            return {"status": "no_difference", "balance_kg": bal}
        m = FodderMovement(organization_id=org_id, product_id=prod.id, movement_date=req.movement_date, movement_type="count_adjust", kg_delta=delta,
                           reason=req.reason or f"Stock count: {F(kg):,.1f} kg counted, {bal:,.1f} kg expected", created_by=user_id)
        result = {"expected_kg": round(bal, 2), "counted_kg": F(kg), "difference_kg": F(delta), "difference_pct": round(100 * F(delta) / bal, 1) if bal else None}
    else:
        sign = D(1) if t == "purchase" else D(-1)
        m = FodderMovement(organization_id=org_id, product_id=prod.id, movement_date=req.movement_date, movement_type=t, kg_delta=sign * kg,
                           value=req.value, destination_type=req.destination_type, destination_id=req.destination_id, destination_label=req.destination_label,
                           customer_id=req.customer_id, reason=req.reason, created_by=user_id)
    db.add(m); await db.flush()
    if t == "purchase" and req.post_to_finance and req.value:
        db.add(FinanceTransaction(organization_id=org_id, transaction_type="expense", category="feed", amount=req.value, transaction_date=req.movement_date,
                                  activity=schemas.ACTIVITY_FODDER, description=f"Fodder purchase: {prod.name} {F(kg):,.0f} kg", reference_type="fodder_purchase", reference_id=m.id, created_by=user_id))
        result["posted_to_finance"] = True
    if t == "sale" and req.value:
        desc = f"Fodder sale: {prod.name} {F(kg):,.0f} kg"
        if req.customer_id:
            db.add(AccountEntry(organization_id=org_id, customer_id=req.customer_id, entry_type="charge", amount=req.value, entry_date=req.movement_date,
                                reference_type="fodder_sale", reference_id=m.id, description=desc, activity=schemas.ACTIVITY_FODDER, created_by=user_id))
            result["ledger"] = "charged_to_customer_account"
        else:
            db.add(FinanceTransaction(organization_id=org_id, transaction_type="income", category="fodder_sale", amount=req.value, transaction_date=req.movement_date,
                                      activity=schemas.ACTIVITY_FODDER, description=desc, reference_type="fodder_sale", reference_id=m.id, created_by=user_id))
            result["ledger"] = "income_posted"
    await db.commit()
    return {"id": str(m.id), "balance_kg": round(bal + F(m.kg_delta), 2), **result}


async def list_movements(db, org_id, product_id=None, start=None, end=None, limit=500):
    q = select(FodderMovement, FodderProduct.name).join(FodderProduct, FodderProduct.id == FodderMovement.product_id).where(FodderMovement.organization_id == org_id)
    if product_id: q = q.where(FodderMovement.product_id == product_id)
    if start: q = q.where(FodderMovement.movement_date >= start)
    if end: q = q.where(FodderMovement.movement_date <= end)
    rows = (await db.execute(q.order_by(FodderMovement.movement_date.desc(), FodderMovement.created_at.desc()).limit(limit))).all()
    return [{"id": str(m.id), "date": m.movement_date.isoformat(), "product": n, "type": m.movement_type, "kg": F(m.kg_delta), "value": F(m.value) if m.value is not None else None,
             "destination": m.destination_label or m.destination_type, "reason": m.reason} for m, n in rows]


# ----------------------------------------------------------------------------- the report
async def summary(db, org_id, start: date, end: date) -> dict:
    econ = await all_cycle_economics(db, org_id, end)
    stock = {s["product_id"]: s for s in await stock_position(db, org_id, end)}
    names = {p.id: p for p in (await db.execute(select(FodderProduct).where(FodderProduct.organization_id == org_id))).scalars()}
    mv = list((await db.execute(select(FodderMovement).where(FodderMovement.organization_id == org_id, FodderMovement.movement_date >= start, FodderMovement.movement_date <= end))).scalars())
    per = defaultdict(lambda: defaultdict(float))
    dest = defaultdict(lambda: defaultdict(float))
    for m in mv:
        kg = F(m.kg_delta)
        per[m.product_id][m.movement_type] += kg
        if m.movement_type == "purchase": per[m.product_id]["purchase_value"] += F(m.value or 0)
        if m.movement_type == "sale": per[m.product_id]["sale_value"] += F(m.value or 0)
        if m.movement_type == "issue": dest[m.product_id][m.destination_label or m.destination_type or "unspecified"] += -kg
    products = []
    for pid, p in names.items():
        a = per.get(pid, {})
        own, bought = a.get("harvest", 0.0), a.get("purchase", 0.0)
        issued, lost = -a.get("issue", 0.0), -a.get("loss", 0.0)
        inflow = own + bought
        products.append({"product": p.name, "harvested_kg": round(own, 1), "purchased_kg": round(bought, 1), "purchase_cost": round(a.get("purchase_value", 0.0), 2),
                         "issued_kg": round(issued, 1), "sold_kg": round(-a.get("sale", 0.0), 1), "sales_value": round(a.get("sale_value", 0.0), 2),
                         "lost_kg": round(lost, 1), "loss_pct_of_inflow": round(100 * lost / inflow, 1) if inflow else None,
                         "count_adjustment_kg": round(a.get("count_adjust", 0.0), 1),
                         "self_sufficiency_pct": round(100 * own / inflow, 1) if inflow else None,
                         "issued_by_destination": {k: round(v, 1) for k, v in dest.get(pid, {}).items()}, "closing_stock": stock.get(str(pid))})
    cycles = (await db.execute(select(FodderCycle, FodderPlot.name, FodderProduct.name).join(FodderPlot, FodderPlot.id == FodderCycle.plot_id)
                               .join(FodderProduct, FodderProduct.id == FodderCycle.product_id).where(FodderCycle.organization_id == org_id,
                               FodderCycle.start_date <= end, (FodderCycle.end_date.is_(None)) | (FodderCycle.end_date >= start)))).all()
    rows = [{"cycle": c.label, "plot": pn, "product": prn, "status": c.status, **{k: econ[c.id][k] for k in ("harvested_kg", "total_cost", "cost_per_kg", "yield_kg_per_acre", "replacement_value", "saving_vs_buying")}}
            for c, pn, prn in cycles if c.id in econ]
    sched = await investment_schedule(db, org_id, end)
    total_cost = sum(r["total_cost"] for r in rows)
    value = sum(r["replacement_value"] or 0 for r in rows)
    return {"start_date": start.isoformat(), "end_date": end.isoformat(), "products": products, "cycles": rows,
            "production": {"total_cost": round(total_cost, 2), "replacement_value": round(value, 2), "saving_vs_buying": round(value - total_cost, 2)},
            "amortisation": sched["totals"]}
