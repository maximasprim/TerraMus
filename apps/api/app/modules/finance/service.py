import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.finance.models import FinanceTransaction, Invoice, InvoiceCounter
from app.modules.finance import schemas


async def record_transaction(
    db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID | None, req: schemas.FinanceTransactionCreate,
    reference_type: str | None = None, reference_id: uuid.UUID | None = None,
) -> FinanceTransaction:
    txn = FinanceTransaction(
        organization_id=org_id, transaction_type=req.transaction_type, category=req.category,
        amount=req.amount, transaction_date=req.transaction_date, description=req.description,
        reference_type=reference_type, reference_id=reference_id, created_by=user_id,
        farm_id=getattr(req, "farm_id", None), activity=getattr(req, "activity", None),
    )
    db.add(txn)
    await db.commit()
    await db.refresh(txn)
    return txn


async def list_transactions(
    db: AsyncSession, org_id: uuid.UUID,
    start_date: date | None = None, end_date: date | None = None,
    transaction_type: str | None = None, category: str | None = None,
    farm_id: uuid.UUID | None = None, activity: str | None = None,
) -> list[FinanceTransaction]:
    query = select(FinanceTransaction).where(FinanceTransaction.organization_id == org_id)
    if start_date:
        query = query.where(FinanceTransaction.transaction_date >= start_date)
    if end_date:
        query = query.where(FinanceTransaction.transaction_date <= end_date)
    if transaction_type:
        query = query.where(FinanceTransaction.transaction_type == transaction_type)
    if category:
        query = query.where(FinanceTransaction.category == category)
    if farm_id:
        query = query.where(FinanceTransaction.farm_id == farm_id)
    if activity:
        query = query.where(FinanceTransaction.activity == activity)
    result = await db.execute(query.order_by(FinanceTransaction.transaction_date.desc()))
    return list(result.scalars().all())


async def get_summary(db: AsyncSession, org_id: uuid.UUID, start_date: date, end_date: date) -> schemas.FinanceSummary:
    """Spec §23/§24 - daily/monthly revenue, expenses, net income, expense breakdown."""
    rows = await db.execute(
        select(FinanceTransaction.transaction_type, FinanceTransaction.category, func.sum(FinanceTransaction.amount))
        .where(
            FinanceTransaction.organization_id == org_id,
            FinanceTransaction.transaction_date >= start_date,
            FinanceTransaction.transaction_date <= end_date,
        )
        .group_by(FinanceTransaction.transaction_type, FinanceTransaction.category)
    )
    income_by_category: dict[str, Decimal] = {}
    expense_by_category: dict[str, Decimal] = {}
    for txn_type, category, total in rows.all():
        if txn_type == "income":
            income_by_category[category] = Decimal(total)
        else:
            expense_by_category[category] = Decimal(total)

    total_income = sum(income_by_category.values(), Decimal("0"))
    total_expense = sum(expense_by_category.values(), Decimal("0"))

    return schemas.FinanceSummary(
        start_date=start_date, end_date=end_date,
        total_income=total_income, total_expense=total_expense, net_income=total_income - total_expense,
        income_by_category=income_by_category, expense_by_category=expense_by_category,
    )


async def _next_invoice_number(db: AsyncSession, org_id: uuid.UUID) -> str:
    result = await db.execute(
        select(InvoiceCounter).where(InvoiceCounter.organization_id == org_id).with_for_update()
    )
    counter = result.scalar_one_or_none()
    if not counter:
        counter = InvoiceCounter(organization_id=org_id, next_number=1)
        db.add(counter)
        await db.flush()
    number = counter.next_number
    counter.next_number += 1
    from app.modules.identity.service import get_organization
    org = await get_organization(db, org_id)
    return f"{org.invoice_prefix}-{number:06d}"  # spec §60 - prefix is now org-configurable


async def generate_invoice(
    db: AsyncSession, org_id: uuid.UUID, order_id: uuid.UUID, customer_id: uuid.UUID, subtotal: Decimal,
) -> Invoice:
    existing = await db.execute(select(Invoice).where(Invoice.order_id == order_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "An invoice already exists for this order")

    from app.modules.identity.service import get_organization
    org = await get_organization(db, org_id)
    # Spec §57: "Do not hard-code tax rates. Make tax rules configurable."
    # org.tax_rate is a flat percentage (0 by default - every existing org
    # created before this session has 0%, so this is a no-op for them until
    # they explicitly set one via PATCH /api/v1/organization/settings).
    tax_amount = (subtotal * Decimal(str(org.tax_rate)) / Decimal("100")).quantize(Decimal("0.01"))

    invoice_number = await _next_invoice_number(db, org_id)
    invoice = Invoice(
        organization_id=org_id, order_id=order_id, customer_id=customer_id,
        invoice_number=invoice_number, subtotal=subtotal, tax_amount=tax_amount, total=subtotal + tax_amount,
        issued_at=datetime.now(timezone.utc),
    )
    db.add(invoice)
    await db.commit()
    await db.refresh(invoice)
    return invoice


async def get_invoice_for_order(db: AsyncSession, org_id: uuid.UUID, order_id: uuid.UUID) -> Invoice:
    result = await db.execute(
        select(Invoice).where(Invoice.organization_id == org_id, Invoice.order_id == order_id)
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No invoice exists for this order")
    return invoice


async def render_invoice_pdf_bytes(db: AsyncSession, org_id: uuid.UUID, order_id: uuid.UUID) -> bytes:
    """Gathers exactly what finance/pdf.py's render_invoice_pdf needs and
    hands off to it - kept here (not in pdf.py) so pdf.py stays a pure
    rendering function with no DB session, easier to reuse/test on its own
    once this sandbox can actually install reportlab and exercise it."""
    from app.modules.commerce.service import get_order
    from app.modules.customers.models import Customer
    from app.modules.identity.models import Organization
    from app.modules.finance.pdf import render_invoice_pdf

    invoice = await get_invoice_for_order(db, org_id, order_id)
    order = await get_order(db, org_id, order_id)
    customer_result = await db.execute(select(Customer).where(Customer.id == invoice.customer_id))
    customer = customer_result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer for this invoice not found")
    org_result = await db.execute(select(Organization).where(Organization.id == org_id))
    organization = org_result.scalar_one()  # org_id always exists - it's the authenticated caller's own org

    return render_invoice_pdf(invoice, order, customer, organization)


# Activity assumed for ledger rows that never recorded one, inferred from their category.
_ACTIVITY_BY_CATEGORY = {
    "livestock_sale": "livestock", "livestock_acquisition": "livestock", "milk_sale": "dairy", "crop_sale": "crops",
    "fodder_sale": "fodder", "poultry_sale": "poultry", "egg_sale": "poultry", "fish_sale": "fish",
    "rabbit_sale": "rabbits", "training_revenue": "training", "seed": "crops", "fertilizer": "crops", "chemicals": "crops",
}


async def get_profitability(db: AsyncSession, org_id: uuid.UUID, start_date: date, end_date: date,
                            farm_id: uuid.UUID | None = None, activity: str | None = None) -> dict:
    """Income/expense/net by activity, by sub-farm, by category and by month. Rows with no recorded
    activity use a category-based default (livestock_sale -> livestock ...), else 'unassigned'."""
    from app.modules.farm.models import Farm
    T = FinanceTransaction
    month = func.to_char(T.transaction_date, "YYYY-MM")
    q = (select(T.transaction_type, T.activity, T.farm_id, T.category, month, func.sum(T.amount))
         .where(T.organization_id == org_id, T.transaction_date >= start_date, T.transaction_date <= end_date)
         .group_by(T.transaction_type, T.activity, T.farm_id, T.category, month))
    if farm_id:
        q = q.where(T.farm_id == farm_id)
    rows = (await db.execute(q)).all()
    names = {f.id: f.name for f in (await db.execute(select(Farm).where(Farm.organization_id == org_id))).scalars()}

    def bucket():
        return {"income": Decimal("0"), "expense": Decimal("0")}
    by_act, by_farm, by_cat, by_month = {}, {}, {}, {}
    for ttype, act, fid, cat, mon, total in rows:
        eff = act or _ACTIVITY_BY_CATEGORY.get(cat, "unassigned")
        if activity and eff != activity:
            continue
        amt = Decimal(total)
        by_act.setdefault(eff, bucket())[ttype] += amt
        by_farm.setdefault(fid, bucket())[ttype] += amt
        by_cat.setdefault((ttype, cat), Decimal("0"))
        by_cat[(ttype, cat)] += amt
        by_month.setdefault(mon, bucket())[ttype] += amt

    def fmt(b):
        net = b["income"] - b["expense"]
        return {"income": float(b["income"]), "expense": float(b["expense"]), "net": float(net),
                "margin_pct": round(float(net / b["income"] * 100), 1) if b["income"] else None}
    tot = bucket()
    for b in by_act.values():
        tot["income"] += b["income"]; tot["expense"] += b["expense"]
    return {
        "start_date": start_date, "end_date": end_date, "farm_id": farm_id, "activity": activity,
        "totals": fmt(tot),
        "by_activity": [{"activity": k, **fmt(v)} for k, v in sorted(by_act.items(), key=lambda x: -(x[1]["income"] - x[1]["expense"]))],
        "by_farm": [{"farm_id": k, "farm_name": names.get(k, "Unassigned (no sub-farm recorded)"), **fmt(v)} for k, v in by_farm.items()],
        "by_category": [{"type": t, "category": c, "amount": float(a)} for (t, c), a in sorted(by_cat.items())],
        "by_month": [{"month": m, **fmt(v)} for m, v in sorted(by_month.items())],
    }
