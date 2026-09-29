"""Spec §32 - 'Every morning: vaccination reminders, inventory alerts,
overdue payments, reservation expiry...' There is no task scheduler in this
build (Celery beat / cron is Phase 9 DevOps territory); this module is the
extraction point a real scheduler would call once a day per organization.
Exposed here as an admin-triggerable endpoint so the logic is real and
testable now rather than a TODO with no code behind it."""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.health.service import list_due_follow_ups
from app.modules.inventory.service import low_stock_items
from app.modules.commerce.service import expire_stale_reservations
from app.modules.notifications.service import notify_users_with_permission
from app.modules.notifications import schemas


async def run_scheduled_checks(db: AsyncSession, org_id: uuid.UUID) -> schemas.ScheduledChecksResult:
    due = await list_due_follow_ups(db, org_id, within_days=7)
    vaccinations_notified = 0
    for item in due:
        await notify_users_with_permission(
            db, org_id, "health.read", "health",
            "Vaccination/follow-up due" if item.record_type != "vaccination" else "Vaccination due",
            f"{item.title} for animal {item.animal_id} - due {item.follow_up_date}"
            f"{' (OVERDUE)' if item.is_overdue else ''}.",
            related_entity_type="animal", related_entity_id=item.animal_id,
        )
        vaccinations_notified += 1

    low_stock = await low_stock_items(db, org_id)
    low_stock_notified = 0
    for item in low_stock:
        await notify_users_with_permission(
            db, org_id, "inventory.read", "inventory",
            "Low stock", f"{item.name}: {item.current_stock} {item.unit} left (reorder level {item.reorder_level}).",
            related_entity_type="inventory_item", related_entity_id=item.item_id,
        )
        low_stock_notified += 1

    expired_ids = await expire_stale_reservations(db, org_id)  # publishes ReservationExpired itself

    return schemas.ScheduledChecksResult(
        vaccinations_due_notified=vaccinations_notified,
        low_stock_notified=low_stock_notified,
        reservations_expired=len(expired_ids),
    )
