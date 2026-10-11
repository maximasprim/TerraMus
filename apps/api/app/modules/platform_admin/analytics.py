"""Platform-wide analytics for the superadmin console (GET /platform/analytics).

Honest limits worth knowing:
  * There is no stored MRR history, so there is deliberately no "MRR over time"
    series. What is charted over time is money actually *collected*
    (subscription payments) and tenant sales volume (GMV) - both real events.
  * Organizations that have never opened billing have no subscription row; the
    app treats them as being on the Free plan (billing lazily creates it), so
    they are counted under Free here to keep the tier split summing to the total.
  * Months are calendar months in the platform default timezone.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.timeseries import key_of, month_keys, month_start
from app.modules.billing.models import Subscription, SubscriptionPayment, SubscriptionTier
from app.modules.billing.service import ensure_default_tiers
from app.modules.commerce.models import Order
from app.modules.crops.models import CropPlanting
from app.modules.identity.models import Organization, User
from app.modules.livestock.models import INACTIVE_STATUSES, Animal
from app.modules.payments.models import Payment
from app.modules.platform_admin import analytics_schemas as s

ZERO = Decimal("0")
TWO_PLACES = Decimal("0.01")
TOP_TENANTS = 10


def _money(value) -> Decimal:
    return Decimal(value or 0).quantize(TWO_PLACES)


async def _platform_clock(db: AsyncSession) -> tuple[str, date]:
    for candidate in (get_settings().DEFAULT_TIMEZONE, "UTC"):
        known = (await db.execute(text("SELECT 1 FROM pg_timezone_names WHERE name = :n LIMIT 1"), {"n": candidate})).scalar_one_or_none()
        if known:
            today = (await db.execute(text("SELECT CAST(timezone(CAST(:tz AS text), now()) AS date)"), {"tz": candidate})).scalar_one()
            return candidate, today
    return "UTC", date.today()


def _ym(column, tz: str):
    local = func.timezone(tz, column)
    return func.extract("year", local), func.extract("month", local)


async def _monthly_money(db, tz, keys, lo, hi, amount_col, count_col, ts_col, *where) -> list[s.MonthlyMoney]:
    year, month = _ym(ts_col, tz)
    local = func.timezone(tz, ts_col)
    rows = (await db.execute(
        select(year, month, func.coalesce(func.sum(amount_col), 0), func.count(count_col))
        .where(*where, local >= lo, local < hi).group_by(year, month)
    )).all()
    amount = {k: ZERO for k in keys}
    count = {k: 0 for k in keys}
    for y, m, total, n in rows:
        amount[key_of(y, m)] += Decimal(total)
        count[key_of(y, m)] += n
    return [s.MonthlyMoney(month=k, amount=_money(amount[k]), payments=count[k]) for k in keys]


async def platform_analytics(db: AsyncSession, months: int) -> s.PlatformAnalytics:
    tz, today = await _platform_clock(db)
    keys = month_keys(today, months)
    start = month_start(keys[0])
    lo = datetime(start.year, start.month, start.day)
    hi = datetime(today.year, today.month, today.day) + timedelta(days=1)
    await ensure_default_tiers(db)
    await db.commit()  # ensure_default_tiers only flushes; make the seed durable like the tiers endpoint does

    # --- organizations ---
    org_rows = (await db.execute(select(Organization.id, Organization.name, Organization.is_suspended, Organization.created_at))).all()
    suspended = sum(1 for r in org_rows if r.is_suspended)
    by_status = [s.LabelCount(key="active", count=len(org_rows) - suspended), s.LabelCount(key="suspended", count=suspended)]

    year, month = _ym(Organization.created_at, tz)
    local_created = func.timezone(tz, Organization.created_at)
    signup_rows = (await db.execute(
        select(year, month, func.count(Organization.id)).where(local_created >= lo, local_created < hi).group_by(year, month)
    )).all()
    created = {k: 0 for k in keys}
    for y, m, c in signup_rows:
        created[key_of(y, m)] += c
    before_window = (await db.execute(select(func.count(Organization.id)).where(local_created < lo))).scalar_one()
    running, signups = before_window, []
    for k in keys:
        running += created[k]
        signups.append(s.MonthlySignups(month=k, count=created[k], cumulative=running))

    # --- subscriptions / plans ---
    tier_rows = (await db.execute(
        select(SubscriptionTier.name, SubscriptionTier.slug, func.count(Subscription.id),
               func.coalesce(func.sum(SubscriptionTier.monthly_price_kes).filter(Subscription.status == "active"), 0))
        .join(Subscription, Subscription.tier_id == SubscriptionTier.id).group_by(SubscriptionTier.name, SubscriptionTier.slug)
    )).all()
    tiers = {name: [slug, count, Decimal(mrr)] for name, slug, count, mrr in tier_rows}
    subscribed = sum(v[1] for v in tiers.values())
    unsubscribed = len(org_rows) - subscribed
    if unsubscribed > 0:  # see module docstring: no row == effectively Free
        free_name = (await db.execute(select(SubscriptionTier.name).where(SubscriptionTier.slug == "free"))).scalar_one_or_none() or "Free"
        entry = tiers.setdefault(free_name, ["free", 0, ZERO])
        entry[1] += unsubscribed
    by_tier = sorted((s.TierStat(key=n, count=v[1], mrr_kes=_money(v[2])) for n, v in tiers.items()), key=lambda t: (-t.count, t.key))
    sub_status = (await db.execute(
        select(Subscription.status, func.count(Subscription.id)).group_by(Subscription.status).order_by(func.count(Subscription.id).desc())
    )).all()
    mrr_total = sum((v[2] for v in tiers.values()), ZERO)

    # --- money over time ---
    sub_revenue = await _monthly_money(
        db, tz, keys, lo, hi, SubscriptionPayment.amount, SubscriptionPayment.id, SubscriptionPayment.completed_at,
        SubscriptionPayment.status == "successful",
    )
    gmv = await _monthly_money(
        db, tz, keys, lo, hi, Payment.amount, Payment.id, Payment.completed_at, Payment.status == "successful",
    )
    local_completed = func.timezone(tz, Payment.completed_at)
    provider_rows = (await db.execute(
        select(Payment.provider, func.coalesce(func.sum(Payment.amount), 0), func.count(Payment.id))
        .where(Payment.status == "successful", local_completed >= lo, local_completed < hi)
        .group_by(Payment.provider).order_by(func.sum(Payment.amount).desc())
    )).all()

    # --- usage ---
    species_rows = (await db.execute(
        select(Animal.species, func.count(Animal.id)).where(Animal.status.not_in(INACTIVE_STATUSES))
        .group_by(Animal.species).order_by(func.count(Animal.id).desc())
    )).all()
    users_by_org = dict((await db.execute(select(User.organization_id, func.count(User.id)).group_by(User.organization_id))).all())
    animals_by_org = dict((await db.execute(
        select(Animal.organization_id, func.count(Animal.id)).where(Animal.status.not_in(INACTIVE_STATUSES)).group_by(Animal.organization_id)
    )).all())
    plantings_by_org = dict((await db.execute(select(CropPlanting.organization_id, func.count(CropPlanting.id)).group_by(CropPlanting.organization_id))).all())
    orders_by_org = dict((await db.execute(select(Order.organization_id, func.count(Order.id)).group_by(Order.organization_id))).all())
    gmv_by_org = dict((await db.execute(
        select(Payment.organization_id, func.coalesce(func.sum(Payment.amount), 0))
        .where(Payment.status == "successful", local_completed >= lo, local_completed < hi).group_by(Payment.organization_id)
    )).all())

    ranked = sorted(org_rows, key=lambda o: (Decimal(gmv_by_org.get(o.id, 0)), animals_by_org.get(o.id, 0), users_by_org.get(o.id, 0)), reverse=True)[:TOP_TENANTS]
    top = [
        s.TopTenant(
            organization_id=o.id, name=o.name, is_suspended=o.is_suspended,
            users=users_by_org.get(o.id, 0), animals=animals_by_org.get(o.id, 0),
            crop_plantings=plantings_by_org.get(o.id, 0), orders=orders_by_org.get(o.id, 0), gmv=_money(gmv_by_org.get(o.id, 0)),
        )
        for o in ranked
    ]

    totals = s.PlatformTotals(
        organizations=len(org_rows), users=sum(users_by_org.values()), animals=sum(animals_by_org.values()),
        crop_plantings=sum(plantings_by_org.values()), orders=sum(orders_by_org.values()), mrr_kes=_money(mrr_total),
        subscription_revenue=_money(sum((m.amount for m in sub_revenue), ZERO)), gmv=_money(sum((m.amount for m in gmv), ZERO)),
    )
    return s.PlatformAnalytics(
        start_date=start, end_date=today, months=months, timezone=tz, totals=totals,
        signups_monthly=signups, organizations_by_status=by_status, organizations_by_tier=by_tier,
        subscriptions_by_status=[s.LabelCount(key=k, count=c) for k, c in sub_status],
        subscription_revenue_monthly=sub_revenue, tenant_gmv_monthly=gmv,
        tenant_payments_by_provider=[s.ProviderTotal(key=p, amount=_money(a), count=c) for p, a, c in provider_rows],
        species_distribution=[s.LabelCount(key=k, count=c) for k, c in species_rows], top_tenants=top,
    )
