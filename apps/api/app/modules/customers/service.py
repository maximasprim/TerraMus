import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.customers.models import Customer
from app.modules.customers import schemas


async def create_customer(db: AsyncSession, org_id: uuid.UUID, req: schemas.CustomerCreate) -> Customer:
    customer = Customer(organization_id=org_id, **req.model_dump())
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    return customer


async def get_customer(db: AsyncSession, org_id: uuid.UUID, customer_id: uuid.UUID) -> Customer:
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id, Customer.organization_id == org_id)
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    return customer


async def list_customers(
    db: AsyncSession, org_id: uuid.UUID, customer_type: str | None = None, search: str | None = None,
) -> list[Customer]:
    query = select(Customer).where(Customer.organization_id == org_id)
    if customer_type:
        query = query.where(Customer.customer_type == customer_type)
    if search:
        like = f"%{search}%"
        query = query.where((Customer.name.ilike(like)) | (Customer.email.ilike(like)) | (Customer.phone.ilike(like)))
    result = await db.execute(query.order_by(Customer.created_at.desc()))
    return list(result.scalars().all())


async def update_customer(
    db: AsyncSession, org_id: uuid.UUID, customer_id: uuid.UUID, req: schemas.CustomerUpdate,
) -> Customer:
    customer = await get_customer(db, org_id, customer_id)
    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(customer, field, value)
    await db.commit()
    await db.refresh(customer)
    return customer


async def find_or_create_by_contact(
    db: AsyncSession, org_id: uuid.UUID, name: str, email: str | None, phone: str | None,
) -> Customer:
    """Supports guest-checkout-style flows later (spec §69) without requiring a
    customer login: match an existing CRM record by email/phone, or create one."""
    if email:
        existing = await db.execute(
            select(Customer).where(Customer.organization_id == org_id, func.lower(Customer.email) == email.strip().lower())
            .order_by(Customer.created_at)          # the same address may legitimately be on several CRM rows: use the oldest
        )
        found = existing.scalars().first()
        if found:
            return found
    customer = Customer(organization_id=org_id, name=name, email=email, phone=phone, customer_type="individual")
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    return customer
