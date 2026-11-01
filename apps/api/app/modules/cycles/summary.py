"""Cross-module roll-up of one production cycle, and side-by-side comparison of several."""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.modules.cycles import resolve
from app.modules.cycles.deps import CycleSel
from app.modules.cycles.models import ProductionCycle


def _f(x) -> float:
    return round(float(x or 0), 2)


async def _feedlot(db, org_id, sel: CycleSel, as_of: date) -> dict:
    from app.modules.feedlot import service as fl
    perf = await fl.performance(db, org_id, as_of, cycle=sel)
    prof = await fl.profitability(db, org_id, as_of, cycle=sel)
    ps, t = perf["summary"], prof["totals"]
    return {"head": ps["head"], "active": ps["active"], "sold": ps["sold"], "culled": ps["culled"], "died": ps["died"],
            "market_ready": ps["market_ready"], "avg_adg_active": ps["avg_adg_active"],
            "loss_rate_pct": round(100 * (ps["culled"] + ps["died"]) / ps["head"], 1) if ps["head"] else 0.0,
            "revenue": t["revenue"], "landed_cost": t["landed_cost"], "feed_cost": t["feed_cost"], "ops_cost": t["ops_cost"],
            "total_cost": t["total_cost"], "profit": t["profit"], "profit_per_head": t["profit_per_head"],
            "avg_adg": t["avg_adg"], "avg_days_on_farm": t["avg_days_on_farm"], "cost_per_kg_gain": t["cost_per_kg_gain"],
            "head_realised": t["head_realised"], "head_open": t["head_open"],
            "unrealised_projected_profit": t["unrealised_projected_profit"],
            "by_intake_batch": [{k: b.get(k) for k in ("intake_batch", "head_total", "head_sold", "head_active", "profit", "profit_per_head", "avg_adg", "loss_rate_pct")}
                                for b in prof["by_intake_batch"]]}


async def _finance(db, org_id, c: ProductionCycle, sel: CycleSel, as_of: date, include_shared: bool) -> dict:
    from app.modules.finance.models import FinanceTransaction as T
    rows = (await db.execute(select(T.transaction_type, T.category, func.sum(T.amount))
                             .where(T.organization_id == org_id, resolve.ledger_cond(sel, T))
                             .group_by(T.transaction_type, T.category))).all()
    inc, exp = defaultdict(Decimal), defaultdict(Decimal)
    for kind, cat, total in rows:
        (inc if kind == "income" else exp)[cat] += Decimal(total)
    ti, te = sum(inc.values(), Decimal(0)), sum(exp.values(), Decimal(0))
    out = {"income": _f(ti), "expense": _f(te), "net": _f(ti - te),
           "income_by_category": {k: _f(v) for k, v in sorted(inc.items(), key=lambda kv: -kv[1])},
           "expense_by_category": {k: _f(v) for k, v in sorted(exp.items(), key=lambda kv: -kv[1])}}
    # Costs nobody tagged to ANY cycle but that were incurred while this one was running (salaries, lease...).
    lo, hi = c.start_date, (c.end_date or as_of)
    if lo:
        shared = (await db.execute(select(T.transaction_date, T.transaction_type, T.amount).where(
            T.organization_id == org_id, resolve.ledger_cycle(T).is_(None), T.transaction_date >= lo, T.transaction_date <= hi))).all()
        sh_exp = sum((Decimal(a) for d, k, a in shared if k == "expense"), Decimal(0))
        sh_inc = sum((Decimal(a) for d, k, a in shared if k == "income"), Decimal(0))
        out["shared_in_window"] = {"from": lo.isoformat(), "to": hi.isoformat(), "expense": _f(sh_exp), "income": _f(sh_inc),
                                   "note": "Untagged ledger rows dated inside this cycle's window. NOT included in the totals above."}
        if include_shared and shared:
            others = (await db.execute(select(ProductionCycle.start_date, ProductionCycle.end_date, ProductionCycle.status)
                                       .where(ProductionCycle.organization_id == org_id, ProductionCycle.enterprise == c.enterprise,
                                              ProductionCycle.start_date.is_not(None), ProductionCycle.status != "planned"))).all()
            est = Decimal(0)
            for d, k, a in shared:
                if k != "expense":
                    continue
                n = sum(1 for s, e, _ in others if s <= d <= (e or as_of)) or 1
                est += Decimal(a) / n
            out["shared_in_window"]["estimated_share_of_expense"] = _f(est)
            out["shared_in_window"]["method"] = "each untagged expense split equally between the cycles of this enterprise running on its date"
    return out


async def _receivables(db, org_id, sel: CycleSel) -> dict:
    from app.modules.receivables.models import AccountEntry as E
    rows = dict((await db.execute(select(E.entry_type, func.sum(E.amount)).where(
        E.organization_id == org_id, resolve.entry_cond(sel, E)).group_by(E.entry_type))).all())
    ch, pd, wo = (Decimal(rows.get(k) or 0) for k in ("charge", "payment", "writeoff"))
    return {"charged": _f(ch), "collected": _f(pd), "written_off": _f(wo), "outstanding": _f(ch - pd - wo)}


async def _simple(db, org_id, c: ProductionCycle, sel: CycleSel, as_of: date) -> dict:
    out: dict = {}
    from app.modules.fuel.models import FuelLog
    litres, cost, n = (await db.execute(select(func.coalesce(func.sum(FuelLog.litres), 0), func.coalesce(func.sum(FuelLog.cost), 0), func.count(FuelLog.id))
                                        .where(FuelLog.organization_id == org_id, FuelLog.production_cycle_id == sel.id))).one()
    out["fuel"] = {"fills": n, "litres": _f(litres), "cost": _f(cost)}

    from app.modules.groups.models import AnimalGroup as G
    g = (await db.execute(select(func.count(G.id), func.coalesce(func.sum(G.initial_count), 0), func.coalesce(func.sum(G.current_count), 0),
                                 func.coalesce(func.sum(G.acquisition_cost), 0)).where(G.organization_id == org_id, G.production_cycle_id == sel.id))).one()
    out["groups"] = {"groups": g[0], "initial_count": int(g[1]), "current_count": int(g[2]), "acquisition_cost": _f(g[3])}

    from app.modules.fodder import service as fod
    cyc = await fod.list_cycles(db, org_id, as_of=as_of, pcycle=sel)
    out["fodder"] = {"plantings": len(cyc), "acres": round(sum(x["acres"] or 0 for x in cyc), 2),
                     "harvested_kg": round(sum((x["economics"] or {}).get("harvested_kg", 0) or 0 for x in cyc), 1),
                     "total_cost": round(sum((x["economics"] or {}).get("total_cost", 0) or 0 for x in cyc), 2)}

    from app.modules.crops.models import CropPlanting as P
    p = (await db.execute(select(func.count(P.id), func.coalesce(func.sum(P.area_size), 0)).where(
        P.organization_id == org_id, P.production_cycle_id == sel.id))).one()
    from app.modules.crops import economics as crop_econ
    ce = (await crop_econ.all_economics(db, org_id, sel)).totals
    out["crops"] = {"plantings": p[0], "area": _f(p[1]), "revenue": _f(ce.total_revenue), "investment": _f(ce.total_investment), "profit": _f(ce.profit)}

    from app.modules.training import service as tr
    sessions = await tr.list_sessions(db, org_id, None, None, None, pcycle=sel)
    out["training"] = {"sessions": len(sessions), "participants": sum(s["enrolled"] for s in sessions),
                       "fees_charged": round(sum(s["fees_charged"] for s in sessions), 2)}

    from app.modules.inventory.models import StockMovement as M
    used = (await db.execute(select(func.coalesce(func.sum(-M.quantity * func.coalesce(M.unit_cost, 0)), 0), func.count(M.id)).where(
        M.organization_id == org_id, M.movement_type.in_(("consumption", "wastage")), resolve.stock_cond(sel, M)))).one()
    out["inventory"] = {"consumption_movements": used[1], "consumption_value": _f(used[0])}

    from app.modules.procurement.models import PurchaseOrder as PO, PurchaseOrderItem as POI
    po = (await db.execute(select(func.count(func.distinct(PO.id)), func.coalesce(func.sum(POI.quantity * POI.unit_cost), 0))
                           .select_from(PO).join(POI, POI.purchase_order_id == PO.id, isouter=True)
                           .where(PO.organization_id == org_id, PO.production_cycle_id == sel.id, PO.status != "cancelled"))).one()
    out["procurement"] = {"purchase_orders": po[0], "value": _f(po[1])}
    return out


async def build_summary(db, org_id, c: ProductionCycle, as_of: date | None = None, include_shared: bool = False) -> dict:
    as_of = as_of or date.today()
    sel = CycleSel(c.id)
    out = {"cycle": {"id": str(c.id), "name": c.name, "cycle_number": c.cycle_number, "enterprise": c.enterprise, "status": c.status,
                     "start_date": c.start_date.isoformat() if c.start_date else None,
                     "end_date": c.end_date.isoformat() if c.end_date else None,
                     "days": ((c.end_date or as_of) - c.start_date).days + 1 if c.start_date else None},
           "as_of": as_of.isoformat()}
    out["feedlot"] = await _feedlot(db, org_id, sel, as_of)
    out["finance"] = await _finance(db, org_id, c, sel, as_of, include_shared)
    out["receivables"] = await _receivables(db, org_id, sel)
    out.update(await _simple(db, org_id, c, sel, as_of))
    return out


async def compare(db, org_id, cycles: list[ProductionCycle], as_of: date | None = None) -> dict:
    rows = []
    for c in cycles:
        s = await build_summary(db, org_id, c, as_of)
        f, fin = s["feedlot"], s["finance"]
        rows.append({"id": s["cycle"]["id"], "name": c.name, "cycle_number": c.cycle_number, "status": c.status,
                     "days": s["cycle"]["days"], "head": f["head"], "sold": f["sold"], "loss_rate_pct": f["loss_rate_pct"],
                     "avg_adg": f["avg_adg"], "avg_days_on_farm": f["avg_days_on_farm"], "cost_per_kg_gain": f["cost_per_kg_gain"],
                     "revenue": f["revenue"], "total_cost": f["total_cost"], "profit": f["profit"], "profit_per_head": f["profit_per_head"],
                     "margin_pct": round(100 * f["profit"] / f["revenue"], 1) if f["revenue"] else None,
                     "ledger_income": fin["income"], "ledger_expense": fin["expense"], "ledger_net": fin["net"],
                     "outstanding_receivables": s["receivables"]["outstanding"]})
    return {"cycles": rows}
