import re
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import (
    hash_password, verify_password, generate_refresh_token, hash_refresh_token, generate_password_reset_token,
)
from app.modules.identity.models import (
    Organization, User, Role, Permission, RefreshToken, PasswordResetToken, role_permissions, user_roles, AuditLog,
)
from app.modules.identity.permissions import PERMISSIONS, DEFAULT_ROLE_GRANTS
from app.modules.identity import schemas


def slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"{base}-{uuid.uuid4().hex[:6]}"


async def get_organization(db: AsyncSession, org_id: uuid.UUID) -> Organization:
    """Shared by every module's per-org counter function (finance, procurement,
    employees, assets) now that numbering prefixes are configurable (spec
    §60) instead of hard-coded - added this session so those four functions
    don't each duplicate the same lookup."""
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one()  # org_id always comes from the authenticated caller's own token
    return org


async def update_organization_settings(
    db: AsyncSession, org_id: uuid.UUID, req: schemas.OrganizationSettingsUpdate,
) -> Organization:
    org = await get_organization(db, org_id)
    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(org, field, value)
    await db.commit()
    await db.refresh(org)
    return org


# --- custom domains for tenant public storefronts ---------------------------
# See core/vercel_client.py's module docstring for the two-kinds-of-verified
# distinction this relies on.

def _dns_instructions_for(domain: str, token: str) -> "schemas.DnsInstructions":
    from app.modules.identity import schemas as _schemas
    # Root/apex domains need an A record (Vercel's stable anycast IP);
    # subdomains use a CNAME instead — both are shown so the tenant can use
    # whichever fits what they're pointing (most will use the CNAME, since
    # most tenants will use a subdomain like shop.theirfarm.com rather than
    # their bare root domain).
    return _schemas.DnsInstructions(
        a_record="76.76.21.21",
        cname_record="cname.vercel-dns.com",
        txt_record_name=f"_farmplatform-verify.{domain}",
        txt_record_value=token,
    )


async def set_organization_domain(db: AsyncSession, org_id: uuid.UUID, domain: str) -> "schemas.DomainStatusOut":
    """Registers `domain` against this org and against the Vercel project
    (if VERCEL_API_TOKEN is configured), and issues a fresh ownership
    verification token. Does NOT mark the domain verified — that only
    happens in verify_organization_domain, once the TXT record is actually
    found published. Overwrites any previous domain/token this org had,
    resetting verified to False — switching domains means re-proving
    ownership of the new one."""
    import secrets
    from app.core import vercel_client
    from app.modules.identity import schemas as _schemas

    domain = domain.strip().lower()
    existing = await db.execute(
        select(Organization).where(Organization.custom_domain == domain, Organization.id != org_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "This domain is already in use by another organization")

    org = await get_organization(db, org_id)
    org.custom_domain = domain
    org.domain_verification_token = secrets.token_urlsafe(24)
    org.domain_verified = False
    org.domain_added_at = datetime.now(timezone.utc)

    vercel_status = None
    try:
        await vercel_client.add_domain_to_project(domain)
        vercel_status = "added"
    except vercel_client.VercelNotConfigured:
        vercel_status = "vercel_not_configured"
    except Exception as exc:  # noqa: BLE001 — surfaced to the caller, not swallowed
        vercel_status = f"vercel_error: {exc}"

    await db.commit()
    await db.refresh(org)

    return _schemas.DomainStatusOut(
        domain=org.custom_domain, verified=org.domain_verified,
        dns_instructions=_dns_instructions_for(org.custom_domain, org.domain_verification_token),
        vercel_status=vercel_status,
    )


async def get_organization_domain_status(db: AsyncSession, org_id: uuid.UUID) -> "schemas.DomainStatusOut":
    from app.modules.identity import schemas as _schemas

    org = await get_organization(db, org_id)
    if not org.custom_domain:
        return _schemas.DomainStatusOut(domain=None, verified=False)
    return _schemas.DomainStatusOut(
        domain=org.custom_domain, verified=org.domain_verified,
        dns_instructions=_dns_instructions_for(org.custom_domain, org.domain_verification_token)
        if not org.domain_verified else None,
    )


async def verify_organization_domain(db: AsyncSession, org_id: uuid.UUID) -> "schemas.DomainStatusOut":
    """Checks the TXT record independently — this is OUR ownership proof,
    separate from whatever Vercel itself thinks about the domain (see
    vercel_client.py's docstring). Runs the (synchronous) dnspython lookup
    in a thread so it doesn't block the event loop."""
    import asyncio
    from app.modules.identity import schemas as _schemas

    org = await get_organization(db, org_id)
    if not org.custom_domain:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No domain has been set for this organization")

    def _check_txt() -> bool:
        import dns.resolver
        try:
            answers = dns.resolver.resolve(f"_farmplatform-verify.{org.custom_domain}", "TXT")
            for rdata in answers:
                # dnspython wraps each TXT string; str(rdata) includes
                # surrounding quotes, so strip them for a clean compare.
                value = str(rdata).strip('"')
                if value == org.domain_verification_token:
                    return True
            return False
        except Exception:
            return False

    verified = await asyncio.to_thread(_check_txt)
    if verified:
        org.domain_verified = True
        await db.commit()
        await db.refresh(org)

    return _schemas.DomainStatusOut(
        domain=org.custom_domain, verified=org.domain_verified,
        dns_instructions=None if org.domain_verified else _dns_instructions_for(org.custom_domain, org.domain_verification_token),
    )


async def remove_organization_domain(db: AsyncSession, org_id: uuid.UUID) -> None:
    from app.core import vercel_client

    org = await get_organization(db, org_id)
    if org.custom_domain:
        try:
            await vercel_client.remove_domain_from_project(org.custom_domain)
        except vercel_client.VercelNotConfigured:
            pass
        except Exception:
            pass  # domain removal from our own DB should still proceed even if the Vercel API call fails
    org.custom_domain = None
    org.domain_verification_token = None
    org.domain_verified = False
    org.domain_added_at = None
    await db.commit()


async def get_organization_by_verified_domain(db: AsyncSession, domain: str) -> Organization | None:
    """Used by the public domain-resolution endpoint (public/router.py) that
    the frontend's Next.js middleware calls on every request to a non-app
    hostname. Only ever matches a domain with domain_verified == True —
    an org that added a domain but hasn't proven DNS control yet must not
    be reachable at that domain."""
    result = await db.execute(
        select(Organization).where(Organization.custom_domain == domain.lower(), Organization.domain_verified.is_(True))
    )
    return result.scalar_one_or_none()


async def ensure_permission_catalog(db: AsyncSession) -> dict[str, Permission]:
    """Idempotently ensure the global permission catalog exists; returns code->Permission."""
    result = await db.execute(select(Permission))
    existing = {p.code: p for p in result.scalars().all()}
    for code, description in PERMISSIONS:
        if code not in existing:
            perm = Permission(code=code, description=description)
            db.add(perm)
            existing[code] = perm
    await db.flush()
    return existing


async def register_organization(db: AsyncSession, req: schemas.RegisterRequest) -> tuple[Organization, User]:
    existing = await db.execute(select(User).where(User.email == req.email))
    if existing.scalar_one_or_none():
        raise ValueError("email_already_registered")

    org = Organization(name=req.organization_name, slug=slugify(req.organization_name))
    db.add(org)
    await db.flush()

    perm_catalog = await ensure_permission_catalog(db)

    roles_by_name: dict[str, Role] = {}
    for role_name, perm_codes in DEFAULT_ROLE_GRANTS.items():
        role = Role(organization_id=org.id, name=role_name, is_system=True)
        role.permissions = [perm_catalog[c] for c in perm_codes if c in perm_catalog]
        db.add(role)
        roles_by_name[role_name] = role
    await db.flush()

    owner = User(
        organization_id=org.id,
        email=req.email,
        phone=req.phone,
        full_name=req.full_name,
        password_hash=hash_password(req.password),
    )
    owner.roles = [roles_by_name["Farm Owner"]]
    db.add(owner)
    await db.commit()
    await db.refresh(owner)
    await db.refresh(org)
    return org, owner


async def authenticate(db: AsyncSession, email: str, password: str) -> User | None:
    result = await db.execute(
        select(User).options(selectinload(User.roles)).where(User.email == email)
    )
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


async def issue_refresh_token(db: AsyncSession, user_id: uuid.UUID) -> str:
    raw, token_hash, expires_at = generate_refresh_token()
    db.add(RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at))
    await db.commit()
    return raw


async def rotate_refresh_token(db: AsyncSession, raw_token: str) -> tuple[User, str] | None:
    token_hash = hash_refresh_token(raw_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    token = result.scalar_one_or_none()
    if not token or token.revoked or token.expires_at < datetime.now(timezone.utc):
        return None
    token.revoked = True
    user_result = await db.execute(
        select(User).options(selectinload(User.roles)).where(User.id == token.user_id)
    )
    user = user_result.scalar_one_or_none()
    if not user or not user.is_active:
        return None
    new_raw = await issue_refresh_token(db, user.id)
    return user, new_raw


async def revoke_refresh_token(db: AsyncSession, raw_token: str) -> None:
    token_hash = hash_refresh_token(raw_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    token = result.scalar_one_or_none()
    if token:
        token.revoked = True
        await db.commit()


async def get_users_with_permission(db: AsyncSession, org_id: uuid.UUID, permission_code: str) -> list[User]:
    """Used by notifications/handlers.py (spec §55) to derive 'who should be
    notified about X' from RBAC rather than a separate subscription list -
    e.g. everyone with health.read gets vaccination-due notices."""
    result = await db.execute(
        select(User)
        .distinct()
        .join(user_roles, user_roles.c.user_id == User.id)
        .join(role_permissions, role_permissions.c.role_id == user_roles.c.role_id)
        .join(Permission, Permission.id == role_permissions.c.permission_id)
        .where(
            User.organization_id == org_id,
            User.is_active.is_(True),
            Permission.code == permission_code,
        )
    )
    return list(result.scalars().all())


async def get_user_permissions(db: AsyncSession, user: User) -> set[str]:
    if not user.roles:
        return set()
    role_ids = [role.id for role in user.roles]
    result = await db.execute(
        select(Permission.code)
        .join(role_permissions, role_permissions.c.permission_id == Permission.id)
        .where(role_permissions.c.role_id.in_(role_ids))
        .distinct()
    )
    return set(result.scalars().all())


async def update_user_roles(
    db: AsyncSession, org_id: uuid.UUID, target_user_id: uuid.UUID,
    role_ids: list[uuid.UUID], changed_by: uuid.UUID,
) -> User:
    """Closes a gap flagged since Phase 1: role_ids could only be set at
    user-creation time, with no way to change them afterward. Also the first
    real write to AuditLog anywhere in the codebase - every other phase built
    its own domain-specific append-only event trail (AnimalEvent,
    OrderStatusEvent, etc.) instead, since AuditLog was designed for exactly
    this kind of cross-cutting admin action that doesn't belong to one
    domain (spec §28: 'user role changed' is explicitly named as an example)."""
    result = await db.execute(
        select(User).options(selectinload(User.roles)).where(
            User.id == target_user_id, User.organization_id == org_id,
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError("user_not_found")

    previous_role_ids = sorted(str(r.id) for r in user.roles)

    roles: list[Role] = []
    if role_ids:
        role_result = await db.execute(
            select(Role).where(Role.id.in_(role_ids), Role.organization_id == org_id)  # tenant-scoped
        )
        roles = list(role_result.scalars().all())
    user.roles = roles

    db.add(AuditLog(
        organization_id=org_id, user_id=changed_by, action="user_roles_changed",
        entity_type="user", entity_id=target_user_id,
        previous_value={"role_ids": previous_role_ids},
        new_value={"role_ids": sorted(str(r.id) for r in roles)},
    ))

    await db.commit()
    await db.refresh(user)
    return user


async def request_password_reset(db: AsyncSession, email: str) -> None:
    """Spec §5: 'password reset.' Deliberately returns None (never a
    'no such user' signal) regardless of whether the email matches an
    account - a different response for 'unknown email' vs 'email sent'
    would let an attacker enumerate registered accounts by trying emails
    against this endpoint, one of the more common real-world auth-flow
    mistakes. The router (identity/router.py) always replies with an
    identical generic 'if that email exists, a reset link was sent'
    message no matter what this function actually did internally."""
    result = await db.execute(select(User).where(User.email == email, User.is_active.is_(True)))
    user = result.scalar_one_or_none()
    if not user:
        return

    raw_token, token_hash, expires_at = generate_password_reset_token()
    db.add(PasswordResetToken(user_id=user.id, token_hash=token_hash, expires_at=expires_at))
    await db.commit()

    from app.core.config import get_settings
    from app.modules.notifications.service import send_email
    settings = get_settings()
    reset_link = f"{settings.PUBLIC_SITE_BASE_URL}/reset-password?token={raw_token}"
    await send_email(
        db, to=user.email, subject="Reset your password",
        body_text=(
            f"Someone requested a password reset for this account. If this was you, "
            f"use this link within {settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minutes:\n\n{reset_link}\n\n"
            f"If you didn't request this, you can ignore this email."
        ),
        organization_id=user.organization_id, related_user_id=user.id,
    )


async def confirm_password_reset(db: AsyncSession, raw_token: str, new_password: str) -> None:
    token_hash = hash_refresh_token(raw_token)  # same SHA-256 helper - hashing mechanism, not meaning, is shared
    result = await db.execute(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash))
    reset_token = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if not reset_token or reset_token.used_at is not None or reset_token.expires_at < now:
        raise ValueError("invalid_or_expired_token")

    user_result = await db.execute(select(User).where(User.id == reset_token.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise ValueError("invalid_or_expired_token")  # same generic error - never confirm a user id is real

    user.password_hash = hash_password(new_password)
    reset_token.used_at = now
    await db.commit()
