"""Derived cycle membership.

A record belongs to a production cycle in one of two ways:

  1. it carries an explicit `production_cycle_id` (batches, manual ledger entries, fuel, flocks, ...), or
  2. it has none of its own but points at something that does: an animal sits in an intake batch that is in a
     cycle, so that animal's weights, exit, purchase cost, vet cost, feed cost, sale and the customer
     payments for that sale are all in the same cycle.

Rule 2 is evaluated in SQL when you ask for a cycle, never copied onto rows. That is what lets the append-only
ledgers stay untouched: put an intake batch into Cycle 1 and every ledger row that traces back to its
animals is in Cycle 1 immediately, including rows posted years earlier.  An explicit tag always wins over a
derived value.
"""
from __future__ import annotations

import uuid

from sqlalchemy import case, func, select
from sqlalchemy.orm import aliased

from app.modules.cycles.deps import CycleSel, cond
from app.modules.commerce.models import OrderItem
from app.modules.crops.models import CropCost, CropPlanting, CropSale
from app.modules.fodder.models import FodderCost, FodderCycle, FodderHarvest, FodderMovement
from app.modules.feedlot.models import FeedlotAnimal, FeedlotExit, IntakeBatch, SaleBatch
from app.modules.finance.models import FinanceTransaction
from app.modules.inventory.models import StockMovement
from app.modules.receivables.models import AccountEntry


# --------------------------------------------------------------------------- animals
def animal_cycle(animal_id_col):
    """Scalar sub-query: the cycle of the intake batch this animal sits in (NULL if none / not a feedlot animal)."""
    fa, ib = aliased(FeedlotAnimal), aliased(IntakeBatch)     # aliased so it never auto-correlates with an outer query on the same table
    return (select(ib.production_cycle_id)
            .select_from(fa).join(ib, ib.id == fa.intake_batch_id)
            .where(fa.animal_id == animal_id_col).scalar_subquery())


def animal_ids_in(org_id: uuid.UUID, sel: CycleSel):
    """Sub-query of animal ids in (or, for 'unassigned', outside) the selected cycle."""
    if sel.unassigned:
        return (select(FeedlotAnimal.animal_id).join(IntakeBatch, IntakeBatch.id == FeedlotAnimal.intake_batch_id)
                .where(FeedlotAnimal.organization_id == org_id, IntakeBatch.production_cycle_id.is_(None)))
    return (select(FeedlotAnimal.animal_id).join(IntakeBatch, IntakeBatch.id == FeedlotAnimal.intake_batch_id)
            .where(FeedlotAnimal.organization_id == org_id, IntakeBatch.production_cycle_id == sel.id))


def exit_cycle(exit_id_col):
    ex, fa, ib = aliased(FeedlotExit), aliased(FeedlotAnimal), aliased(IntakeBatch)
    return (select(ib.production_cycle_id)
            .select_from(ex)
            .join(fa, fa.animal_id == ex.animal_id)
            .join(ib, ib.id == fa.intake_batch_id)
            .where(ex.id == exit_id_col).scalar_subquery())


# --------------------------------------------------------------------------- receivables
def crop_record_cycle(model, record_id_col):
    """Cycle of the planting a crop sale / crop cost belongs to."""
    rec, cp = aliased(model), aliased(CropPlanting)
    return (select(cp.production_cycle_id).select_from(rec).join(cp, cp.id == rec.planting_id)
            .where(rec.id == record_id_col).scalar_subquery())


def fodder_movement_cycle(M=FodderMovement):
    """Effective cycle of a fodder stock movement: its own tag, else (for a harvest) its fodder planting's cycle."""
    hv, fy = aliased(FodderHarvest), aliased(FodderCycle)
    harvest = (select(fy.production_cycle_id).select_from(hv).join(fy, fy.id == hv.cycle_id)
               .where(hv.id == M.reference_id).scalar_subquery())
    return func.coalesce(M.production_cycle_id, case((M.reference_type == "harvest", harvest), else_=None))


def fodder_movement_cycle_by_id(movement_id_col):
    fm = aliased(FodderMovement)
    return select(fodder_movement_cycle(fm)).where(fm.id == movement_id_col).scalar_subquery()


def fodder_cost_cycle(cost_id_col):
    """A fodder cost belongs to the cycle of the fodder planting it was spent on."""
    fc, fy = aliased(FodderCost), aliased(FodderCycle)
    return (select(fy.production_cycle_id).select_from(fc).join(fy, fy.id == fc.cycle_id)
            .where(fc.id == cost_id_col).scalar_subquery())


def planting_cycle(planting_id_col):
    cp = aliased(CropPlanting)
    return select(cp.production_cycle_id).where(cp.id == planting_id_col).scalar_subquery()


def entry_cycle(entry=AccountEntry):
    """Effective cycle of a customer-account entry."""
    return func.coalesce(entry.production_cycle_id, case(
        (entry.reference_type == "feedlot_sale", exit_cycle(entry.reference_id)),
        (entry.reference_type == "crop_sale", crop_record_cycle(CropSale, entry.reference_id)),
        (entry.reference_type == "fodder_sale", fodder_movement_cycle_by_id(entry.reference_id)),
        else_=None))


# --------------------------------------------------------------------------- finance ledger
def ledger_cycle(T=FinanceTransaction):
    """Effective cycle of a finance ledger row (explicit tag, else traced through its reference)."""
    ae = aliased(AccountEntry)
    pay = select(entry_cycle(ae)).where(ae.id == T.reference_id).scalar_subquery()
    oi, fa, ib = aliased(OrderItem), aliased(FeedlotAnimal), aliased(IntakeBatch)
    order = (select(ib.production_cycle_id)
             .select_from(oi)
             .join(fa, fa.animal_id == oi.animal_id)
             .join(ib, ib.id == fa.intake_batch_id)
             .where(oi.order_id == T.reference_id).limit(1).scalar_subquery())
    # crop-only web orders: the produce belongs to a planting, and the planting to a cycle
    oi2, cp = aliased(OrderItem), aliased(CropPlanting)
    crop_order = (select(cp.production_cycle_id).select_from(oi2).join(cp, cp.id == oi2.crop_planting_id)
                  .where(oi2.order_id == T.reference_id).limit(1).scalar_subquery())
    return func.coalesce(T.production_cycle_id, case(
        (T.reference_type == "feedlot_sale", exit_cycle(T.reference_id)),
        (T.reference_type == "animal", animal_cycle(T.reference_id)),
        (T.reference_type == "account_payment", pay),
        (T.reference_type == "order", func.coalesce(order, crop_order)),
        (T.reference_type.in_(("crop_sale", "crop_sale_void")), crop_record_cycle(CropSale, T.reference_id)),
        (T.reference_type.in_(("crop_cost", "crop_cost_void")), crop_record_cycle(CropCost, T.reference_id)),
        (T.reference_type == "crop_planting", planting_cycle(T.reference_id)),
        (T.reference_type == "fodder_cost", fodder_cost_cycle(T.reference_id)),
        (T.reference_type.in_(("fodder_purchase", "fodder_sale")), fodder_movement_cycle_by_id(T.reference_id)),
        else_=None))


def stock_cycle(M=StockMovement):
    """Stock movements: explicit tag, else the cycle of the animal the feed/medicine was issued to."""
    return func.coalesce(M.production_cycle_id, case((M.animal_id.is_not(None), animal_cycle(M.animal_id)), else_=None))


# --------------------------------------------------------------------------- sale batches
def sale_batch_in(org_id: uuid.UUID, sel: CycleSel):
    """Condition for SaleBatch: tagged to the cycle, or any of its exits is an animal of the cycle."""
    via_animals = (select(FeedlotExit.sale_batch_id)
                   .where(FeedlotExit.organization_id == org_id, FeedlotExit.sale_batch_id.is_not(None),
                          FeedlotExit.animal_id.in_(animal_ids_in(org_id, CycleSel(sel.id)))))
    if sel.unassigned:
        return SaleBatch.production_cycle_id.is_(None) & SaleBatch.id.not_in(
            select(FeedlotExit.sale_batch_id).where(FeedlotExit.organization_id == org_id,
                                                    FeedlotExit.sale_batch_id.is_not(None),
                                                    FeedlotExit.animal_id.in_(
                                                        select(FeedlotAnimal.animal_id).join(
                                                            IntakeBatch, IntakeBatch.id == FeedlotAnimal.intake_batch_id)
                                                        .where(IntakeBatch.production_cycle_id.is_not(None)))))
    return (SaleBatch.production_cycle_id == sel.id) | SaleBatch.id.in_(via_animals)


def ledger_cond(sel: CycleSel, T=FinanceTransaction):
    return cond(ledger_cycle(T), sel)


def entry_cond(sel: CycleSel, entry=AccountEntry):
    return cond(entry_cycle(entry), sel)


def stock_cond(sel: CycleSel, M=StockMovement):
    return cond(stock_cycle(M), sel)
