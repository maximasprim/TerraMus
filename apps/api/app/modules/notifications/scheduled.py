"""Daily checks (spec §32: "Every morning: vaccination reminders, inventory alerts, overdue payments,
reservation expiry..."). `run_scheduled_checks` does one organisation's checks; scheduler/runner.py calls it
for every organisation once a day. It can still be triggered by hand (POST /notifications/run-scheduled-checks).

Two properties matter once this runs by itself every day:
  * NO REPEAT SPAM - every alert has a key and a cooldown (alert_log). A vaccination due in 5 days is announced once,
    then reminded weekly (every 3 days once overdue), not every morning.
  * READABLE - messages name animals by tag, not by internal id."""
import uuid
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.commerce.service import expire_stale_reservations
from app.modules.health.service import list_due_follow_ups
from app.modules.inventory.service import low_stock_items
from app.modules.livestock.models import Animal
from app.modules.notifications import schemas
from app.modules.notifications.service import notify_users_with_permission
from app.modules.scheduler.models import AlertLog

DAILY = 1
WEEKLY = 7


async def _is_due(db: AsyncSession, org_id: uuid.UUID, key: str, cooldown_days: int, today: date) -> bool:
    row = (await db.execute(select(AlertLog).where(AlertLog.organization_id == org_id, AlertLog.alert_key == key))).scalar_one_or_none()
    return row is None or (today - row.last_sent_on).days >= cooldown_days


async def _mark_sent(db: AsyncSession, org_id: uuid.UUID, key: str, today: date) -> None:
    row = (await db.execute(select(AlertLog).where(AlertLog.organization_id == org_id, AlertLog.alert_key == key))).scalar_one_or_none()
    if row:
        row.last_sent_on, row.times_sent = today, row.times_sent + 1
    else:
        db.add(AlertLog(organization_id=org_id, alert_key=key, last_sent_on=today, times_sent=1))
    await db.commit()


async def _alert(db, org_id, today, key, cooldown, permission, category, title, message, **ref) -> int:
    """Send one alert unless it was sent within its cooldown. Marked AFTER sending: a crash in between repeats an
    alert (harmless) rather than silently losing one."""
    if not await _is_due(db, org_id, key, cooldown, today):
        return 0
    await notify_users_with_permission(db, org_id, permission, category, title, message, **ref)
    await _mark_sent(db, org_id, key, today)
    return 1


def _list(tags: list[str], limit: int = 8) -> str:
    return ", ".join(tags[:limit]) + (f" and {len(tags) - limit} more" if len(tags) > limit else "")


async def run_scheduled_checks(db: AsyncSession, org_id: uuid.UUID, today: date | None = None) -> schemas.ScheduledChecksResult:
    today = today or date.today()
    out = schemas.ScheduledChecksResult(vaccinations_due_notified=0, low_stock_notified=0, reservations_expired=0)

    # --- vaccinations / follow-ups (7 days ahead; weekly reminder, every 3 days once overdue)
    due = await list_due_follow_ups(db, org_id, within_days=7)
    ids = list({d.animal_id for d in due})
    labels = {a.id: (a.animal_number + (f" ({a.name})" if a.name else "")) for a in (
        await db.execute(select(Animal).where(Animal.id.in_(ids or [None])))).scalars()}
    for item in due:
        vacc = item.record_type == "vaccination"
        out.vaccinations_due_notified += await _alert(
            db, org_id, today, f"followup:{item.animal_id}:{item.follow_up_date}", 3 if item.is_overdue else WEEKLY,
            "health.read", "health", "Vaccination due" if vacc else "Vaccination/follow-up due",
            f"{item.title} for {labels.get(item.animal_id, 'an animal')} - due {item.follow_up_date}{' (OVERDUE)' if item.is_overdue else ''}.",
            related_entity_type="animal", related_entity_id=item.animal_id)

    # --- inventory
    for item in await low_stock_items(db, org_id):
        out.low_stock_notified += await _alert(
            db, org_id, today, f"lowstock:{item.item_id}", 3, "inventory.read", "inventory", "Low stock",
            f"{item.name}: {item.current_stock} {item.unit} left (reorder level {item.reorder_level}).",
            related_entity_type="inventory_item", related_entity_id=item.item_id)

    out.reservations_expired = len(await expire_stale_reservations(db, org_id))   # publishes ReservationExpired itself

    # --- feedlot: animals overdue for a weigh-in, and animals that reached market weight
    from app.modules.feedlot import service as feedlot
    perf = await feedlot.performance(db, org_id, today)
    if perf["summary"]["head"]:
        stale = perf["summary"]["no_recent_weight"]
        if stale:
            out.feedlot_unweighed_notified = await _alert(
                db, org_id, today, "feedlot:unweighed", WEEKLY, "feedlot.read", "system", "Animals overdue for weighing",
                f"{len(stale)} animal(s) have not been weighed in over 45 days: {_list(stale)}.")
        ready = [a["tag"] for a in perf["animals"] if a["status"] == "active" and a["market_ready"]]
        if ready:
            out.feedlot_market_ready_notified = await _alert(
                db, org_id, today, "feedlot:market_ready", WEEKLY, "feedlot.read", "system", "Animals ready for market",
                f"{len(ready)} animal(s) are at or above market weight: {_list(ready)}.")

    # --- receivables: debts older than 30 days
    from app.modules.receivables import service as receivables
    owing = await receivables.balances(db, org_id, today)
    old = [c for c in owing["customers"] if c["days_outstanding"] > 30]
    if old:
        top = max(old, key=lambda c: c["balance"])
        out.receivables_notified = await _alert(
            db, org_id, today, "receivables:overdue", WEEKLY, "finance.read", "payments", "Overdue customer balances",
            f"{len(old)} customer(s) owe money for over 30 days, KES {sum(c['balance'] for c in old):,.0f} in total. "
            f"Largest: {top['customer_name'] or 'a customer'} (KES {top['balance']:,.0f}, {top['days_outstanding']} days).")

    # --- payments waiting for a person to decide
    from app.modules.payments.models import Payment
    waiting = (await db.execute(select(func.count()).select_from(Payment).where(
        Payment.organization_id == org_id, Payment.status == "needs_review"))).scalar_one()
    if waiting:
        out.payments_review_notified = await _alert(
            db, org_id, today, "payments:review", DAILY, "payments.manage", "payments", "Payments waiting for review",
            f"{waiting} payment(s) need a decision: money may have been received that could not be matched to an order.")

    # --- training starting in the next 3 days
    from app.modules.training.models import TrainingCourse, TrainingEnrolment, TrainingSession
    soon = (await db.execute(
        select(TrainingSession, TrainingCourse.title, func.count(TrainingEnrolment.id))
        .join(TrainingCourse, TrainingCourse.id == TrainingSession.course_id)
        .join(TrainingEnrolment, (TrainingEnrolment.session_id == TrainingSession.id) & (TrainingEnrolment.status != "cancelled"))
        .where(TrainingSession.organization_id == org_id, TrainingSession.status == "scheduled",
               TrainingSession.start_date >= today, TrainingSession.start_date <= today + timedelta(days=3))
        .group_by(TrainingSession.id, TrainingCourse.title))).all()
    for sess, title, n in soon:
        out.training_notified += await _alert(
            db, org_id, today, f"training:{sess.id}", 365, "training.read", "system", "Training starting soon",
            f"{title} starts {sess.start_date:%d %b} with {n} participant(s) enrolled.",
            related_entity_type="training_session", related_entity_id=sess.id)

    # --- fodder cover (added with the fodder module)
    try:
        from app.modules.fodder.alerts import low_cover_alerts
    except ImportError:
        low_cover_alerts = None
    if low_cover_alerts:
        for key, title, message in await low_cover_alerts(db, org_id, today):
            out.fodder_notified += await _alert(db, org_id, today, key, 3, "fodder.read", "inventory", title, message)
    return out
