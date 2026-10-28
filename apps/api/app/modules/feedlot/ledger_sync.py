"""Keeps the finance ledger in step with the feedlot.

Sales and purchases recorded in the feedlot (typed in, or imported from the worksheet)
must reach Finance, the dashboard and the reports, but never twice: the ledger is
append-only, so a duplicate could not be removed afterwards.

Three layers stop a double recording:
  1. Every posting is keyed to the thing it records (reference_type + reference_id) and
     we check for an existing entry first.
  2. Partial unique indexes (migration 0036) make a duplicate impossible at the database
     level; a racing second attempt is caught and counted as "already recorded".
  3. `reconcile` (the catch-up for data imported before this existed) shows what it
     would post and refuses to apply when Finance already holds manually typed
     entries of the same kind, unless the caller explicitly confirms they are different.

Postings use the real sale / delivery date, never "today", so history is not back-dated
into the current month.
"""
from __future__ import annotations

import uuid
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.feedlot.models import FeedlotAnimal, FeedlotExit
from app.modules.finance.models import FinanceTransaction
from app.modules.livestock.models import Animal
from app.modules.receivables.models import AccountEntry

SALE_REF = "feedlot_sale"
ACQUISITION_REF = "animal"
ACQUISITION_CATEGORY = "livestock_acquisition"
# Ledger rows of these kinds are produced by the system itself and are never "manual".
_SYSTEM_REFS = (SALE_REF, "order", "account_payment", ACQUISITION_REF)
SAMPLE_LIMIT = 25


def sale_is_postable(ex: FeedlotExit) -> bool:
    """A sale can only be booked once it has a real amount: weight and price on record."""
    return (ex.exit_type == "sold" and ex.amount is not None and float(ex.amount) > 0
            and ex.exit_weight_kg is not None and ex.price_per_kg is not None)


async def _recorded_sale_ids(db: AsyncSession, org_id: uuid.UUID) -> set[uuid.UUID]:
    cash = (await db.execute(select(FinanceTransaction.reference_id).where(
        FinanceTransaction.organization_id == org_id, FinanceTransaction.reference_type == SALE_REF))).scalars().all()
    credit = (await db.execute(select(AccountEntry.reference_id).where(
        AccountEntry.organization_id == org_id, AccountEntry.reference_type == SALE_REF,
        AccountEntry.entry_type == "charge"))).scalars().all()
    return {*cash, *credit}


async def _recorded_acquisition_ids(db: AsyncSession, org_id: uuid.UUID) -> set[uuid.UUID]:
    return set((await db.execute(select(FinanceTransaction.reference_id).where(
        FinanceTransaction.organization_id == org_id, FinanceTransaction.reference_type == ACQUISITION_REF,
        FinanceTransaction.category == ACQUISITION_CATEGORY))).scalars().all())


async def post_sale(db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID | None,
                    ex: FeedlotExit, animal: Animal) -> str:
    """Book one feedlot sale. -> 'posted' | 'already_recorded' | 'no_price'. Does not commit."""
    if not sale_is_postable(ex):
        return "no_price"
    if ex.id in await _recorded_sale_ids(db, org_id):
        return "already_recorded"
    from app.modules.receivables import service as receivables   # cash sale -> income now; credit -> charge on account
    try:
        async with db.begin_nested():                             # a savepoint: a duplicate never poisons the batch
            await receivables.stage_feedlot_sale(db, org_id, user_id, ex, animal)
            await db.flush()
    except IntegrityError:
        return "already_recorded"
    return "posted"


async def post_acquisition(db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID | None,
                           animal: Animal, received_on: date, recorded: set[uuid.UUID] | None = None) -> str:
    """Book one animal's purchase cost as an expense dated on its delivery. Does not commit."""
    if animal.acquisition_cost is None or float(animal.acquisition_cost) <= 0:
        return "no_cost"
    if animal.id in (recorded if recorded is not None else await _recorded_acquisition_ids(db, org_id)):
        return "already_recorded"
    try:
        async with db.begin_nested():
            db.add(FinanceTransaction(
                organization_id=org_id, transaction_type="expense", category=ACQUISITION_CATEGORY,
                amount=animal.acquisition_cost, transaction_date=received_on, farm_id=animal.farm_id,
                activity="feedlot", description=f"Purchase of {animal.animal_number} (feedlot intake)",
                reference_type=ACQUISITION_REF, reference_id=animal.id, created_by=user_id))
            await db.flush()
    except IntegrityError:
        return "already_recorded"
    if recorded is not None:
        recorded.add(animal.id)
    return "posted"


async def _manual_totals(db: AsyncSession, org_id: uuid.UUID, kind: str, category: str) -> dict:
    """Ledger rows of this kind typed in by hand (not produced by an order, a feedlot sale or an
    animal registration). These are the ones that could overlap with what we are about to post."""
    row = (await db.execute(
        select(func.count(FinanceTransaction.id), func.coalesce(func.sum(FinanceTransaction.amount), 0),
               func.min(FinanceTransaction.transaction_date), func.max(FinanceTransaction.transaction_date))
        .where(FinanceTransaction.organization_id == org_id, FinanceTransaction.transaction_type == kind,
               FinanceTransaction.category == category,
               or_(FinanceTransaction.reference_type.is_(None), FinanceTransaction.reference_type.notin_(_SYSTEM_REFS))))).one()
    return {"count": int(row[0]), "total": float(row[1]),
            "first": row[2].isoformat() if row[2] else None, "last": row[3].isoformat() if row[3] else None}


async def reconcile(db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID, *, dry_run: bool = True,
                    include_purchases: bool = True, confirm_overlap: bool = False) -> dict:
    """Catch-up for feedlot sales/purchases that exist but never reached the ledger (e.g. imported
    before the importer posted to Finance). Safe to run repeatedly: only what is missing is posted."""
    sold = (await db.execute(
        select(FeedlotExit, Animal).join(Animal, Animal.id == FeedlotExit.animal_id)
        .where(FeedlotExit.organization_id == org_id, FeedlotExit.exit_type == "sold")
        .order_by(FeedlotExit.exit_date, Animal.animal_number))).all()
    sale_done = await _recorded_sale_ids(db, org_id)
    sales = {"already_recorded": 0, "no_price": 0, "missing": 0, "missing_amount": 0.0, "posted": 0}
    sale_todo: list[tuple[FeedlotExit, Animal]] = []
    for ex, animal in sold:
        if not sale_is_postable(ex):
            sales["no_price"] += 1
        elif ex.id in sale_done:
            sales["already_recorded"] += 1
        else:
            sales["missing"] += 1
            sales["missing_amount"] += float(ex.amount)
            sale_todo.append((ex, animal))

    buy = {"already_recorded": 0, "no_cost": 0, "missing": 0, "missing_amount": 0.0, "posted": 0}
    buy_todo: list[tuple[FeedlotAnimal, Animal]] = []
    if include_purchases:
        rows = (await db.execute(
            select(FeedlotAnimal, Animal).join(Animal, Animal.id == FeedlotAnimal.animal_id)
            .where(FeedlotAnimal.organization_id == org_id).order_by(FeedlotAnimal.received_on, Animal.animal_number))).all()
        acq_done = await _recorded_acquisition_ids(db, org_id)
        for fa, animal in rows:
            if animal.acquisition_cost is None or float(animal.acquisition_cost) <= 0:
                buy["no_cost"] += 1
            elif animal.id in acq_done:
                buy["already_recorded"] += 1
            else:
                buy["missing"] += 1
                buy["missing_amount"] += float(animal.acquisition_cost)
                buy_todo.append((fa, animal))

    overlap = {"manual_sales": await _manual_totals(db, org_id, "income", "livestock_sale"),
               "manual_purchases": await _manual_totals(db, org_id, "expense", ACQUISITION_CATEGORY)}
    sales_overlap = bool(sale_todo) and overlap["manual_sales"]["count"] > 0
    buy_overlap = bool(buy_todo) and overlap["manual_purchases"]["count"] > 0
    needs_confirmation = sales_overlap or buy_overlap

    sample = [{"kind": "sale", "animal": a.animal_number, "date": e.exit_date.isoformat(), "amount": float(e.amount)}
              for e, a in sale_todo[:SAMPLE_LIMIT]]
    sample += [{"kind": "purchase", "animal": a.animal_number, "date": fa.received_on.isoformat(),
                "amount": float(a.acquisition_cost)} for fa, a in buy_todo[:max(0, SAMPLE_LIMIT - len(sample))]]

    result = {"dry_run": dry_run, "sales": sales, "purchases": buy, "overlap": overlap,
              "needs_confirmation": needs_confirmation, "sample": sample}
    if dry_run:
        return result

    if needs_confirmation and not confirm_overlap:
        parts = []
        if sales_overlap:
            m = overlap["manual_sales"]
            parts.append(f"{m['count']} manually entered livestock sale(s) totalling KES {m['total']:,.0f}")
        if buy_overlap:
            m = overlap["manual_purchases"]
            parts.append(f"{m['count']} manually entered livestock purchase(s) totalling KES {m['total']:,.0f}")
        raise HTTPException(status.HTTP_409_CONFLICT, (
            "Finance already holds " + " and ".join(parts) + ". If they record the same bulls, posting these too "
            "would count them twice. Review them in Finance first. If they are different, repeat the request "
            "with confirm_overlap=true."))

    recorded_acq = await _recorded_acquisition_ids(db, org_id) if buy_todo else set()
    for ex, animal in sale_todo:
        outcome = await post_sale(db, org_id, user_id, ex, animal)
        if outcome == "posted":
            sales["posted"] += 1
        elif outcome == "already_recorded":
            sales["already_recorded"] += 1
            sales["missing"] -= 1
    for fa, animal in buy_todo:
        outcome = await post_acquisition(db, org_id, user_id, animal, fa.received_on, recorded_acq)
        if outcome == "posted":
            buy["posted"] += 1
        elif outcome == "already_recorded":
            buy["already_recorded"] += 1
            buy["missing"] -= 1
    await db.commit()
    result["dry_run"] = False
    return result
