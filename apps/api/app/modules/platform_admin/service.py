import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select, func

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_password, hash_password, generate_password_reset_token, hash_refresh_token
from app.modules.identity.models import Organization, User, AuditLog
from app.modules.billing.models import Subscription, SubscriptionTier
from app.modules.billing.service import ensure_default_tiers
from app.modules.platform_admin.models import PlatformAdmin, PlatformAdminPasswordResetToken
from app.modules.platform_admin.security import create_platform_admin_token
from app.modules.platform_admin import schemas


async def authenticate_platform_admin(db: AsyncSession, email: str, password: str) -> str:
    result = await db.execute(select(PlatformAdmin).where(PlatformAdmin.email == email))
    admin = result.scalar_one_or_none()
    if not admin or not admin.is_active or not verify_password(password, admin.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    return create_platform_admin_token(str(admin.id))


async def record_admin_action(
    db: AsyncSession, org_id: uuid.UUID, admin_id: uuid.UUID, action: str,
    entity_type: str, entity_id: uuid.UUID | None = None,
    previous_value: dict | None = None, new_value: dict | None = None,
) -> None:
    """Writes into the SAME AuditLog table tenant actions already use
    (identity.models.AuditLog), just with the platform admin's id as
    `user_id` - deliberately not a separate audit table, so a single query
    against `audit_logs` shows a tenant's full history including anything a
    superuser did to their org. Does not commit; callers commit as part of
    their existing transaction so the audit row and the actual change are
    atomic (both happen or neither does)."""
    db.add(AuditLog(
        organization_id=org_id, user_id=admin_id, action=action,
        entity_type=entity_type, entity_id=entity_id,
        previous_value=previous_value, new_value=new_value,
    ))


# --- platform admin account management --------------------------------------

async def list_platform_admins(db: AsyncSession) -> list[PlatformAdmin]:
    result = await db.execute(select(PlatformAdmin).order_by(PlatformAdmin.created_at))
    return list(result.scalars().all())


async def create_platform_admin(db: AsyncSession, email: str, full_name: str, password: str, role: str = "superadmin") -> PlatformAdmin:
    existing = await db.execute(select(PlatformAdmin).where(PlatformAdmin.email == email))
    if existing.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "A platform admin with this email already exists")
    admin = PlatformAdmin(email=email, full_name=full_name, password_hash=hash_password(password), role=role)
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    return admin


async def set_platform_admin_active(db: AsyncSession, admin_id: uuid.UUID, is_active: bool) -> PlatformAdmin:
    result = await db.execute(select(PlatformAdmin).where(PlatformAdmin.id == admin_id))
    admin = result.scalar_one_or_none()
    if not admin:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Platform admin not found")
    admin.is_active = is_active
    await db.commit()
    await db.refresh(admin)
    return admin


async def set_platform_admin_role(db: AsyncSession, admin_id: uuid.UUID, role: str) -> PlatformAdmin:
    result = await db.execute(select(PlatformAdmin).where(PlatformAdmin.id == admin_id))
    admin = result.scalar_one_or_none()
    if not admin:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Platform admin not found")
    admin.role = role
    await db.commit()
    await db.refresh(admin)
    return admin


async def _to_summary(db: AsyncSession, org: Organization) -> schemas.OrganizationSummaryOut:
    user_count = (await db.execute(
        select(func.count(User.id)).where(User.organization_id == org.id)
    )).scalar_one()

    sub_result = await db.execute(
        select(Subscription, SubscriptionTier)
        .join(SubscriptionTier, Subscription.tier_id == SubscriptionTier.id)
        .where(Subscription.organization_id == org.id)
    )
    row = sub_result.first()
    tier_name = row[1].name if row else None
    sub_status = row[0].status if row else None

    return schemas.OrganizationSummaryOut(
        id=org.id, name=org.name, slug=org.slug, currency=org.currency,
        is_suspended=org.is_suspended, user_count=user_count,
        subscription_tier=tier_name, subscription_status=sub_status,
        created_at=org.created_at,
    )


async def list_organizations(
    db: AsyncSession, search: str | None, page: int, page_size: int,
) -> list[schemas.OrganizationSummaryOut]:
    query = select(Organization).order_by(Organization.created_at.desc())
    if search:
        query = query.where(Organization.name.ilike(f"%{search}%"))
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    orgs = result.scalars().all()
    return [await _to_summary(db, org) for org in orgs]


async def get_organization(db: AsyncSession, org_id: uuid.UUID) -> Organization:
    """Deliberately looks the org up with NO organization_id filter at all -
    unlike every tenant-scoped service.get_*(db, id, org_id) function in the
    codebase, a platform admin's whole purpose is to reach any org by id.
    This is safe specifically because it's only ever reachable behind
    get_current_platform_admin (see deps.py), never behind get_tenant_context
    or require_permission - those two dependency chains are structurally
    disjoint (separate JWT "type" claims), so this function can never be
    called by an ordinary tenant user's request."""
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")
    return org


async def get_organization_detail(db: AsyncSession, org_id: uuid.UUID) -> schemas.OrganizationSummaryOut:
    org = await get_organization(db, org_id)
    return await _to_summary(db, org)


async def set_organization_status(
    db: AsyncSession, org_id: uuid.UUID, admin_id: uuid.UUID, is_suspended: bool, reason: str | None,
) -> schemas.OrganizationSummaryOut:
    org = await get_organization(db, org_id)
    previous = {"is_suspended": org.is_suspended}
    org.is_suspended = is_suspended
    await record_admin_action(
        db, org_id, admin_id, action="organization.suspend" if is_suspended else "organization.reactivate",
        entity_type="organization", entity_id=org_id,
        previous_value=previous, new_value={"is_suspended": is_suspended, "reason": reason},
    )
    await db.commit()
    await db.refresh(org)
    return await _to_summary(db, org)


async def dashboard_stats(db: AsyncSession) -> schemas.PlatformDashboardStats:
    total = (await db.execute(select(func.count(Organization.id)))).scalar_one()
    suspended = (await db.execute(
        select(func.count(Organization.id)).where(Organization.is_suspended.is_(True))
    )).scalar_one()
    total_users = (await db.execute(select(func.count(User.id)))).scalar_one()

    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    signups = (await db.execute(
        select(func.count(Organization.id)).where(Organization.created_at >= thirty_days_ago)
    )).scalar_one()

    await ensure_default_tiers(db)
    tier_rows = (await db.execute(
        select(SubscriptionTier.name, func.count(Subscription.id))
        .join(Subscription, Subscription.tier_id == SubscriptionTier.id)
        .group_by(SubscriptionTier.name)
    )).all()
    by_tier = {name: count for name, count in tier_rows}

    mrr_rows = (await db.execute(
        select(func.coalesce(func.sum(SubscriptionTier.monthly_price_kes), 0))
        .select_from(Subscription)
        .join(SubscriptionTier, Subscription.tier_id == SubscriptionTier.id)
        .where(Subscription.status == "active")
    )).scalar_one()

    return schemas.PlatformDashboardStats(
        total_organizations=total,
        active_organizations=total - suspended,
        suspended_organizations=suspended,
        total_users=total_users,
        organizations_by_tier=by_tier,
        mrr_kes=float(mrr_rows),
        signups_last_30_days=signups,
    )


# --- platform admin password reset -------------------------------------------
# Mirrors identity.service.request_password_reset / confirm_password_reset
# exactly (same never-reveal-whether-the-email-exists behavior, same
# hashed-token-at-rest pattern) against the separate
# PlatformAdminPasswordResetToken table instead of PasswordResetToken.

async def request_platform_admin_password_reset(db: AsyncSession, email: str) -> None:
    result = await db.execute(
        select(PlatformAdmin).where(PlatformAdmin.email == email, PlatformAdmin.is_active.is_(True))
    )
    admin = result.scalar_one_or_none()
    if not admin:
        return  # never reveal whether the email exists - same reasoning as the tenant flow

    raw_token, token_hash, expires_at = generate_password_reset_token()
    db.add(PlatformAdminPasswordResetToken(
        platform_admin_id=admin.id, token_hash=token_hash, expires_at=expires_at,
    ))
    await db.commit()

    from app.core.config import get_settings
    from app.modules.notifications.service import send_email
    settings = get_settings()
    reset_link = f"{settings.PUBLIC_SITE_BASE_URL}/platform/reset-password?token={raw_token}"
    await send_email(
        db, to=admin.email, subject="Reset your platform admin password",
        body_text=(
            f"A password reset was requested for this platform admin account. If this "
            f"was you, use this link within {settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minutes:"
            f"\n\n{reset_link}\n\nIf you didn't request this, you can ignore this email."
        ),
        organization_id=None, related_user_id=None,
    )


async def confirm_platform_admin_password_reset(db: AsyncSession, raw_token: str, new_password: str) -> None:
    token_hash = hash_refresh_token(raw_token)  # same SHA-256 helper as the tenant flow, hashing only
    result = await db.execute(
        select(PlatformAdminPasswordResetToken).where(PlatformAdminPasswordResetToken.token_hash == token_hash)
    )
    token = result.scalar_one_or_none()
    if not token or token.used_at is not None or token.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired reset token")

    admin_result = await db.execute(select(PlatformAdmin).where(PlatformAdmin.id == token.platform_admin_id))
    admin = admin_result.scalar_one()
    admin.password_hash = hash_password(new_password)
    token.used_at = datetime.now(timezone.utc)
    await db.commit()
