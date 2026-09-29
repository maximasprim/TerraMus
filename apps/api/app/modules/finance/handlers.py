"""Subscribes to events published by other modules (spec §31) to
auto-generate finance ledger entries and invoices - the payoff for having
built core/events.py back in Phase 2 instead of importing modules directly
into each other.

Each handler opens its OWN database session: events fire fire-and-forget
*after* the triggering transaction has already committed (see
core/events.py), so there is no session to reuse, and a failure here must
never roll back the transaction that triggered it - logged, not raised."""
import logging
import uuid
from datetime import date, timezone

from app.core import database as db_module
from app.core.events import subscribe
from app.modules.finance import schemas, service

logger = logging.getLogger("finance.handlers")


async def on_animal_acquired(payload: dict) -> None:
    """Spec §52.6 - 'Animal acquisition must create an acquisition cost.'"""
    acquisition_cost = payload.get("acquisition_cost")
    if not acquisition_cost or float(acquisition_cost) <= 0:
        return
    async with db_module.AsyncSessionLocal() as db:
        await service.record_transaction(
            db, uuid.UUID(payload["organization_id"]), None,
            schemas.FinanceTransactionCreate(
                transaction_type="expense", category="livestock_acquisition",
                amount=acquisition_cost, transaction_date=date.today(),
                description=f"Acquisition cost for animal {payload['animal_id']}",
            ),
            reference_type="animal", reference_id=uuid.UUID(payload["animal_id"]),
        )


async def on_payment_succeeded(payload: dict) -> None:
    """Spec §52.4 - 'Animal sale must create a financial transaction.' Also
    generates the order's invoice (spec §59) at the same time, since both are
    triggered by the same confirmed-payment event."""
    async with db_module.AsyncSessionLocal() as db:
        org_id = uuid.UUID(payload["organization_id"])
        order_id = uuid.UUID(payload["order_id"])
        amount = payload["amount"]

        await service.record_transaction(
            db, org_id, None,
            schemas.FinanceTransactionCreate(
                transaction_type="income", category="livestock_sale",
                amount=amount, transaction_date=date.today(),
                description=f"Payment received for order {order_id}",
            ),
            reference_type="order", reference_id=order_id,
        )

        # Need the customer_id to invoice - fetch the order directly rather
        # than importing commerce.service here to avoid a handler-time
        # circular import; a plain SELECT is enough for this one field.
        from sqlalchemy import select
        from app.modules.commerce.models import Order
        result = await db.execute(select(Order).where(Order.id == order_id))
        order = result.scalar_one_or_none()
        if order:
            try:
                await service.generate_invoice(db, org_id, order_id, order.customer_id, order.total_amount)
            except Exception:
                logger.exception("invoice generation failed for order %s", order_id)


async def on_health_cost_incurred(payload: dict) -> None:
    """Spec §23 - veterinary costs belong in the finance ledger, closing the
    gap where the profitability report (reporting/service.py) could show a
    health cost that the ledger itself never recorded."""
    cost = payload.get("cost")
    if not cost or float(cost) <= 0:
        return
    async with db_module.AsyncSessionLocal() as db:
        await service.record_transaction(
            db, uuid.UUID(payload["organization_id"]), None,
            schemas.FinanceTransactionCreate(
                transaction_type="expense", category="veterinary",
                amount=cost, transaction_date=date.today(),
                description=f"Health record {payload['health_record_id']} ({payload['record_type']}) "
                             f"for animal {payload['animal_id']}",
            ),
            reference_type="animal", reference_id=uuid.UUID(payload["animal_id"]),
        )


async def on_inventory_spend(payload: dict) -> None:
    """Spec §23 - same gap as above, for feed/medicine/supply consumption."""
    category_map = {"feed": "feed", "medicine": "veterinary", "vaccine": "veterinary"}
    category = category_map.get(payload.get("item_category"), "other_expense")
    async with db_module.AsyncSessionLocal() as db:
        await service.record_transaction(
            db, uuid.UUID(payload["organization_id"]), None,
            schemas.FinanceTransactionCreate(
                transaction_type="expense", category=category,
                amount=payload["cost"], transaction_date=date.today(),
                description=f"{payload['movement_type']} of {payload['item_name']}",
            ),
            reference_type="animal" if payload.get("animal_id") else "manual",
            reference_id=uuid.UUID(payload["animal_id"]) if payload.get("animal_id") else None,
        )


def register_finance_event_handlers() -> None:
    subscribe("AnimalAcquired", on_animal_acquired)
    subscribe("PaymentSucceeded", on_payment_succeeded)
    subscribe("HealthRecordCreated", on_health_cost_incurred)
    subscribe("InventorySpend", on_inventory_spend)
