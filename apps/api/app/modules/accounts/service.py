import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.modules.identity.models import User, Role
from app.modules.customers.models import Customer
from app.modules.customers.service import find_or_create_by_contact
from app.modules.commerce.models import Order
from app.modules.commerce.service import list_orders as commerce_list_orders, get_order as commerce_get_order
from app.modules.accounts import schemas


async def register_customer_account(db: AsyncSession, org_id: uuid.UUID, req: schemas.CustomerRegisterRequest) -> User:
    """Spec §69/§70: self-service account creation. Reuses
    find_or_create_by_contact (the exact seam Phase 4 built and Phase 11's
    guest checkout already reuses) so a customer who previously checked out
    as a guest with this email gets their existing order history linked to
    the new login, rather than a disconnected duplicate CRM record."""
    existing = await db.execute(select(User).where(User.email == req.email))
    if existing.scalar_one_or_none():
        raise ValueError("email_already_registered")

    role_result = await db.execute(
        select(Role).where(Role.organization_id == org_id, Role.name == "Customer")
    )
    customer_role = role_result.scalar_one_or_none()
    if not customer_role:
        # Only possible if an organization predates the "Customer" role
        # existing in DEFAULT_ROLE_GRANTS - not reachable for orgs created
        # by the current register_organization, but checked rather than
        # assumed, per this codebase's general stance on trusting invariants
        # across phases it didn't verify together.
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Customer role not configured for this organization")

    customer = await find_or_create_by_contact(db, org_id, req.full_name, req.email, req.phone)

    user = User(
        organization_id=org_id, email=req.email, phone=req.phone, full_name=req.full_name,
        password_hash=hash_password(req.password), customer_id=customer.id, roles=[customer_role],
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def get_my_account(db: AsyncSession, user: User) -> schemas.MyAccountOut:
    result = await db.execute(select(Customer).where(Customer.id == user.customer_id))
    customer = result.scalar_one_or_none()
    if not customer:
        # Shouldn't happen for a properly-linked account, but the FK is
        # nullable and customer rows aren't protected from deletion, so this
        # is checked rather than assumed (same reasoning as the missing-role
        # check in register_customer_account above).
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Linked customer record not found")
    return schemas.MyAccountOut(
        user_id=user.id, customer_id=customer.id, full_name=customer.name, email=customer.email or user.email,
        phone=customer.phone, location=customer.location, customer_type=customer.customer_type,
        created_at=customer.created_at,
    )


async def list_my_orders(db: AsyncSession, org_id: uuid.UUID, customer_id: uuid.UUID) -> list[Order]:
    return await commerce_list_orders(db, org_id, customer_id=customer_id)


async def get_my_order(db: AsyncSession, org_id: uuid.UUID, customer_id: uuid.UUID, order_id: uuid.UUID) -> schemas.MyOrderDetailOut:
    """Same 404-not-403 ownership-check convention as public.service
    .get_guest_order - an order that exists but isn't yours reads as 'not
    found', not 'forbidden', so the URL alone never confirms an order id is
    real for someone else's account.

    Also surfaces invoice + payment history (spec §16: 'payments, invoices'
    alongside orders) - a documented gap from Phase 15 ('order status/items
    only'), closed this session now that the customer portal has somewhere
    to show it."""
    order = await commerce_get_order(db, org_id, order_id)
    if order.customer_id != customer_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")

    from app.modules.finance.models import Invoice
    from app.modules.payments.models import Payment

    invoice_result = await db.execute(select(Invoice).where(Invoice.order_id == order_id))
    invoice = invoice_result.scalar_one_or_none()

    payments_result = await db.execute(
        select(Payment).where(Payment.order_id == order_id).order_by(Payment.initiated_at)
    )
    payments = list(payments_result.scalars().all())

    return schemas.MyOrderDetailOut(
        id=order.id, status=order.status, total_amount=order.total_amount,
        delivery_option=order.delivery_option, created_at=order.created_at, items=list(order.items),
        invoice=schemas.MyInvoiceOut.model_validate(invoice) if invoice else None,
        payments=[schemas.MyPaymentOut.model_validate(p) for p in payments],
    )
