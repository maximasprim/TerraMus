"""Event-driven notifications (spec §55) - turns events already being
published by other modules since Phase 2 into actual delivered (in-app)
notifications. Same fire-and-forget-with-own-session pattern as
finance/handlers.py, including the same test-loop-safety fix (module
attribute lookup on db_module, not a bound import - see conftest.py)."""
import logging
import uuid

from sqlalchemy import select

from app.core import database as db_module
from app.core.events import subscribe
from app.modules.notifications.service import notify_users_with_permission, send_email

logger = logging.getLogger("notifications.handlers")


async def on_vaccination_due(payload: dict) -> None:
    async with db_module.AsyncSessionLocal() as db:
        await notify_users_with_permission(
            db, uuid.UUID(payload["organization_id"]), "health.read", "health",
            "Vaccination due", f"Animal {payload['animal_id']} has a vaccination due {payload['due_date']}.",
            related_entity_type="animal", related_entity_id=uuid.UUID(payload["animal_id"]),
        )


async def on_health_follow_up_due(payload: dict) -> None:
    async with db_module.AsyncSessionLocal() as db:
        await notify_users_with_permission(
            db, uuid.UUID(payload["organization_id"]), "health.read", "health",
            "Health follow-up due", f"Animal {payload['animal_id']} has a follow-up due {payload['due_date']}.",
            related_entity_type="animal", related_entity_id=uuid.UUID(payload["animal_id"]),
        )


async def on_inventory_low(payload: dict) -> None:
    async with db_module.AsyncSessionLocal() as db:
        await notify_users_with_permission(
            db, uuid.UUID(payload["organization_id"]), "inventory.read", "inventory",
            "Low stock", f"{payload['item_name']} is low: {payload['current_stock']} left "
                         f"(reorder level {payload['reorder_level']}).",
            related_entity_type="inventory_item", related_entity_id=uuid.UUID(payload["item_id"]),
        )


async def on_inventory_expiring(payload: dict) -> None:
    async with db_module.AsyncSessionLocal() as db:
        await notify_users_with_permission(
            db, uuid.UUID(payload["organization_id"]), "inventory.read", "inventory",
            "Stock expiring", f"A batch expires on {payload['expiry_date']}.",
            related_entity_type="inventory_item", related_entity_id=uuid.UUID(payload["item_id"]),
        )


async def on_payment_failed(payload: dict) -> None:
    async with db_module.AsyncSessionLocal() as db:
        await notify_users_with_permission(
            db, uuid.UUID(payload["organization_id"]), "payments.manage", "payments",
            "Payment failed", f"Payment {payload['payment_id']} failed.",
            related_entity_type="payment", related_entity_id=uuid.UUID(payload["payment_id"]),
        )


async def on_payment_succeeded(payload: dict) -> None:
    """Spec §55 lists 'order shipped'/'payment received' as customer-facing
    notification categories - the in-app Notification model (above) is
    staff-only (it's keyed by user_id on this org's own users), so a
    payment confirmation reaching the *customer* has to go out over email
    instead. Added this session alongside the email channel itself; this
    handler didn't exist before there was anywhere for it to actually send."""
    async with db_module.AsyncSessionLocal() as db:
        from app.modules.commerce.models import Order
        from app.modules.customers.models import Customer

        result = await db.execute(
            select(Order, Customer).join(Customer, Customer.id == Order.customer_id)
            .where(Order.id == uuid.UUID(payload["order_id"]))
        )
        row = result.first()
        if not row:
            return
        order, customer = row
        if not customer.email:
            return  # spec §69 allows a phone-only guest checkout - nothing to email in that case

        await send_email(
            db, to=customer.email, subject="Payment received - order confirmed",
            body_text=(
                f"Thanks, {customer.name}! We've received your payment of "
                f"{payload['amount']} for your order. We'll be in touch about next steps."
            ),
            organization_id=order.organization_id,
        )


async def on_order_created(payload: dict) -> None:
    async with db_module.AsyncSessionLocal() as db:
        await notify_users_with_permission(
            db, uuid.UUID(payload["organization_id"]), "orders.manage", "orders",
            "New order", f"New order {payload['order_id']} received.",
            related_entity_type="order", related_entity_id=uuid.UUID(payload["order_id"]),
        )


async def on_pregnancy_confirmed(payload: dict) -> None:
    async with db_module.AsyncSessionLocal() as db:
        await notify_users_with_permission(
            db, uuid.UUID(payload["organization_id"]), "breeding.read", "breeding",
            "Pregnancy confirmed", f"Animal {payload['animal_id']} confirmed pregnant"
                                   f"{' - expected ' + payload['expected_delivery_date'] if payload.get('expected_delivery_date') else ''}.",
            related_entity_type="animal", related_entity_id=uuid.UUID(payload["animal_id"]),
        )


async def on_birth_recorded(payload: dict) -> None:
    async with db_module.AsyncSessionLocal() as db:
        await notify_users_with_permission(
            db, uuid.UUID(payload["organization_id"]), "breeding.read", "breeding",
            "Birth recorded", f"Animal {payload['dam_id']} gave birth "
                               f"({len(payload.get('offspring_ids', []))} offspring).",
            related_entity_type="animal", related_entity_id=uuid.UUID(payload["dam_id"]),
        )


async def on_reservation_expired(payload: dict) -> None:
    async with db_module.AsyncSessionLocal() as db:
        await notify_users_with_permission(
            db, uuid.UUID(payload["organization_id"]), "orders.manage", "orders",
            "Reservation expired", f"Reservation {payload['reservation_id']} expired and was released.",
            related_entity_type="reservation", related_entity_id=uuid.UUID(payload["reservation_id"]),
        )


def register_notification_event_handlers() -> None:
    subscribe("VaccinationDue", on_vaccination_due)
    subscribe("HealthFollowUpDue", on_health_follow_up_due)
    subscribe("InventoryLow", on_inventory_low)
    subscribe("InventoryExpiring", on_inventory_expiring)
    subscribe("PaymentFailed", on_payment_failed)
    subscribe("PaymentSucceeded", on_payment_succeeded)
    subscribe("OrderCreated", on_order_created)
    subscribe("PregnancyConfirmed", on_pregnancy_confirmed)
    subscribe("BirthRecorded", on_birth_recorded)
    subscribe("ReservationExpired", on_reservation_expired)
