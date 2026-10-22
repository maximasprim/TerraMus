"""Customer receivables: credit sales, part payments, balances, ageing, write-offs.

Income is recognised in the finance ledger when CASH IS RECEIVED (the same basis the
shop uses: income posts when an order is paid). A credit sale therefore creates a
charge on the customer's account and no ledger income until payments arrive.
"""
import uuid
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.customers.models import Customer
from app.modules.finance.models import FinanceTransaction
from app.modules.receivables import schemas
from app.modules.receivables.models import AccountEntry

_CATEGORY = {"feedlot_sale": "livestock_sale", "training_enrolment": "training_revenue", "crop_sale": "crop_sale",
             "fodder_sale": "fodder_sale", "group_sale": "other_revenue", "order": "other_revenue", "manual": "other_revenue"}
_ACTIVITY = {"feedlot_sale": "feedlot", "training_enrolment": "training", "crop_sale": "crops", "fodder_sale": "fodder"}
BUCKETS = (("0-30", 0, 30), ("31-60", 31, 60), ("61-90", 61, 90), ("90+", 91, 10 ** 6))


def D(x) -> Decimal:
    return Decimal(str(x))


async def _customer(db: AsyncSession, org_id: uuid.UUID, customer_id: uuid.UUID) -> Customer:
    c = (await db.execute(select(Customer).where(Customer.id == customer_id, Customer.organization_id == org_id))).scalar_one_or_none()
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    return c


def fifo_open_items(entries: list[AccountEntry]) -> tuple[list[dict], Decimal]:
    """Apply all payments + write-offs to the oldest charges first.
    -> (charges with their outstanding amount, unapplied credit)."""
    charges = sorted((e for e in entries if e.entry_type == "charge"), key=lambda e: (e.entry_date, e.created_at))
    credit = sum((D(e.amount) for e in entries if e.entry_type in ("payment", "writeoff")), Decimal("0"))
    out = []
    for c in charges:
        applied = min(credit, D(c.amount))
        credit -= applied
        out.append({"charge_id": str(c.id), "date": c.entry_date, "description": c.description,
                    "reference_type": c.reference_type, "reference_id": str(c.reference_id) if c.reference_id else None,
                    "charged": float(c.amount), "paid": float(applied), "outstanding": float(D(c.amount) - applied)})
    return out, credit


def age_buckets(open_items: list[dict], as_of: date) -> dict[str, float]:
    b = {name: 0.0 for name, _, _ in BUCKETS}
    for it in open_items:
        if it["outstanding"] <= 0:
            continue
        age = max((as_of - it["date"]).days, 0)
        for name, lo, hi in BUCKETS:
            if lo <= age <= hi:
                b[name] += it["outstanding"]
                break
    return {k: round(v, 2) for k, v in b.items()}


def _entry_out(e: AccountEntry) -> dict:
    return {"id": str(e.id), "type": e.entry_type, "amount": float(e.amount), "date": e.entry_date.isoformat(),
            "description": e.description, "method": e.method, "receipt_ref": e.receipt_ref,
            "reference_type": e.reference_type, "reference_id": str(e.reference_id) if e.reference_id else None,
            "salesperson": e.salesperson, "activity": e.activity}


async def _entries(db, org_id, customer_id=None, as_of: date | None = None) -> list[AccountEntry]:
    q = select(AccountEntry).where(AccountEntry.organization_id == org_id)
    if customer_id:
        q = q.where(AccountEntry.customer_id == customer_id)
    if as_of:
        q = q.where(AccountEntry.entry_date <= as_of)
    return list((await db.execute(q.order_by(AccountEntry.entry_date, AccountEntry.created_at))).scalars())


async def add_charge(db, org_id, user_id, req: schemas.ChargeCreate) -> AccountEntry:
    await _customer(db, org_id, req.customer_id)
    e = AccountEntry(organization_id=org_id, customer_id=req.customer_id, entry_type="charge", amount=req.amount,
                     entry_date=req.entry_date, reference_type=req.reference_type, reference_id=req.reference_id,
                     description=req.description, farm_id=req.farm_id, activity=req.activity or _ACTIVITY.get(req.reference_type),
                     salesperson=req.salesperson, created_by=user_id)
    db.add(e)
    await db.commit()
    return e


async def add_payment(db, org_id, user_id, req: schemas.PaymentCreate) -> dict:
    await _customer(db, org_id, req.customer_id)
    farm_id, activity = req.farm_id, req.activity
    if req.reference_id and req.reference_type:     # inherit the dimensions of the sale being paid
        ch = (await db.execute(select(AccountEntry).where(
            AccountEntry.organization_id == org_id, AccountEntry.entry_type == "charge",
            AccountEntry.reference_type == req.reference_type, AccountEntry.reference_id == req.reference_id))).scalars().first()
        if ch:
            farm_id, activity = farm_id or ch.farm_id, activity or ch.activity
    activity = activity or _ACTIVITY.get(req.reference_type or "manual")
    before = await _entries(db, org_id, req.customer_id)
    bal_before = sum((D(e.amount) if e.entry_type == "charge" else -D(e.amount) for e in before), Decimal("0"))
    e = AccountEntry(organization_id=org_id, customer_id=req.customer_id, entry_type="payment", amount=req.amount,
                     entry_date=req.entry_date, reference_type=req.reference_type, reference_id=req.reference_id,
                     description=req.description, method=req.method, receipt_ref=req.receipt_ref, farm_id=farm_id,
                     activity=activity, created_by=user_id)
    db.add(e)
    await db.flush()
    txn = FinanceTransaction(organization_id=org_id, transaction_type="income",
                             category=_CATEGORY.get(req.reference_type or "manual", "other_revenue"), amount=req.amount,
                             transaction_date=req.entry_date, farm_id=farm_id, activity=activity,
                             description=(req.description or "Customer payment") + (f" [{req.receipt_ref}]" if req.receipt_ref else ""),
                             reference_type="account_payment", reference_id=e.id, created_by=user_id)
    db.add(txn)
    await db.commit()
    bal_after = bal_before - D(req.amount)
    out = {"entry": _entry_out(e), "finance_transaction_id": str(txn.id), "balance_before": float(bal_before),
           "balance_after": float(bal_after)}
    if bal_after < 0:
        out["warning"] = f"Customer is now in credit by {float(-bal_after):,.2f} (paid more than was owed)"
    return out


async def add_writeoff(db, org_id, user_id, req: schemas.WriteoffCreate) -> AccountEntry:
    await _customer(db, org_id, req.customer_id)
    entries = await _entries(db, org_id, req.customer_id)
    bal = sum((D(e.amount) if e.entry_type == "charge" else -D(e.amount) for e in entries), Decimal("0"))
    if D(req.amount) > bal:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Cannot write off {req.amount}: the customer only owes {bal}")
    e = AccountEntry(organization_id=org_id, customer_id=req.customer_id, entry_type="writeoff", amount=req.amount,
                     entry_date=req.entry_date, reference_type=req.reference_type, reference_id=req.reference_id,
                     description=req.description, created_by=user_id)
    db.add(e)
    await db.commit()
    return e


async def statement(db, org_id, customer_id, as_of: date | None = None) -> dict:
    cust = await _customer(db, org_id, customer_id)
    as_of = as_of or date.today()
    entries = await _entries(db, org_id, customer_id, as_of)
    open_items, credit = fifo_open_items(entries)
    charged = sum((D(e.amount) for e in entries if e.entry_type == "charge"), Decimal("0"))
    paid = sum((D(e.amount) for e in entries if e.entry_type == "payment"), Decimal("0"))
    wo = sum((D(e.amount) for e in entries if e.entry_type == "writeoff"), Decimal("0"))
    run, lines = Decimal("0"), []
    for e in entries:
        run += D(e.amount) if e.entry_type == "charge" else -D(e.amount)
        lines.append({**_entry_out(e), "running_balance": float(run)})
    return {"customer_id": str(cust.id), "customer_name": getattr(cust, "name", None), "as_of": as_of.isoformat(),
            "charged": float(charged), "paid": float(paid), "written_off": float(wo), "balance": float(charged - paid - wo),
            "credit_on_account": float(credit), "open_items": [i for i in open_items if i["outstanding"] > 0],
            "ageing": age_buckets(open_items, as_of), "entries": lines}


async def balances(db, org_id, as_of: date | None = None) -> dict:
    as_of = as_of or date.today()
    entries = await _entries(db, org_id, None, as_of)
    by_c: dict[uuid.UUID, list[AccountEntry]] = defaultdict(list)
    for e in entries:
        by_c[e.customer_id].append(e)
    names = {c.id: c for c in (await db.execute(select(Customer).where(Customer.organization_id == org_id))).scalars()}
    rows, total_ageing = [], {n: 0.0 for n, _, _ in BUCKETS}
    for cid, es in by_c.items():
        items, credit = fifo_open_items(es)
        owed = round(sum(i["outstanding"] for i in items), 2)
        if owed <= 0:
            continue
        ag = age_buckets(items, as_of)
        for k, v in ag.items():
            total_ageing[k] += v
        oldest = min((i["date"] for i in items if i["outstanding"] > 0), default=None)
        rows.append({"customer_id": str(cid), "customer_name": getattr(names.get(cid), "name", None),
                     "phone": getattr(names.get(cid), "phone", None), "balance": owed, "ageing": ag,
                     "oldest_unpaid": oldest.isoformat() if oldest else None,
                     "days_outstanding": (as_of - oldest).days if oldest else 0})
    rows.sort(key=lambda r: -r["balance"])
    return {"as_of": as_of.isoformat(), "total_outstanding": round(sum(r["balance"] for r in rows), 2),
            "customers_owing": len(rows), "ageing": {k: round(v, 2) for k, v in total_ageing.items()}, "customers": rows}


async def sales_by_salesperson(db, org_id, start: date, end: date) -> list[dict]:
    from app.modules.feedlot.models import FeedlotExit
    agg: dict[str, dict] = defaultdict(lambda: {"sales": 0, "amount": Decimal("0")})
    for e in (await db.execute(select(FeedlotExit).where(FeedlotExit.organization_id == org_id, FeedlotExit.exit_type == "sold",
                                                          FeedlotExit.exit_date >= start, FeedlotExit.exit_date <= end))).scalars():
        k = e.salesperson or "(not recorded)"
        agg[k]["sales"] += 1; agg[k]["amount"] += D(e.amount)
    # other credit sales recorded straight on accounts (feedlot sales are already counted above)
    for e in (await db.execute(select(AccountEntry).where(
            AccountEntry.organization_id == org_id, AccountEntry.entry_type == "charge",
            AccountEntry.reference_type != "feedlot_sale", AccountEntry.entry_date >= start, AccountEntry.entry_date <= end))).scalars():
        k = e.salesperson or "(not recorded)"
        agg[k]["sales"] += 1; agg[k]["amount"] += D(e.amount)
    return sorted(({"salesperson": k, "sales": v["sales"], "amount": float(v["amount"])} for k, v in agg.items()), key=lambda r: -r["amount"])


async def stage_feedlot_sale(db: AsyncSession, org_id, user_id, ex, animal) -> None:
    """Called inside the sale's own transaction (NO commit here): a sale can never exist without its ledger entry.
    With a customer: a charge on their account (income posts as they pay). Without: a cash sale, income now."""
    desc = f"Sale of {animal.animal_number} {float(ex.exit_weight_kg):g}kg @ {float(ex.price_per_kg):g}/kg"
    if ex.customer_id:
        db.add(AccountEntry(organization_id=org_id, customer_id=ex.customer_id, entry_type="charge", amount=ex.amount,
                            entry_date=ex.exit_date, reference_type="feedlot_sale", reference_id=ex.id, description=desc,
                            farm_id=animal.farm_id, activity="feedlot", salesperson=ex.salesperson, created_by=user_id))
    else:
        db.add(FinanceTransaction(organization_id=org_id, transaction_type="income", category="livestock_sale", amount=ex.amount,
                                  transaction_date=ex.exit_date, farm_id=animal.farm_id, activity="feedlot", description=desc,
                                  reference_type="feedlot_sale", reference_id=ex.id, created_by=user_id))
