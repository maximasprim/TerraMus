import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import create_access_token
from app.core.middleware import rate_limit_auth
from app.modules.identity import schemas, service
from app.modules.identity.deps import get_current_user, require_permission
from app.modules.identity.models import User, Organization, Role

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
users_router = APIRouter(prefix="/api/v1/users", tags=["users"])
organization_router = APIRouter(prefix="/api/v1/organization", tags=["organization"])


@router.post("/register", response_model=schemas.TokenPair, status_code=status.HTTP_201_CREATED)
async def register(req: schemas.RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    await rate_limit_auth(request)
    try:
        org, user = await service.register_organization(db, req)
    except ValueError as exc:
        if str(exc) == "email_already_registered":
            raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
        raise
    access_token = create_access_token(str(user.id), str(org.id))
    refresh_token = await service.issue_refresh_token(db, user.id)
    return schemas.TokenPair(access_token=access_token, refresh_token=refresh_token)


@router.post("/login", response_model=schemas.TokenPair)
async def login(req: schemas.LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    await rate_limit_auth(request)
    user = await service.authenticate(db, req.email, req.password)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    access_token = create_access_token(str(user.id), str(user.organization_id))
    refresh_token = await service.issue_refresh_token(db, user.id)
    return schemas.TokenPair(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=schemas.TokenPair)
async def refresh(req: schemas.RefreshRequest, db: AsyncSession = Depends(get_db)):
    result = await service.rotate_refresh_token(db, req.refresh_token)
    if not result:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired refresh token")
    user, new_raw = result
    access_token = create_access_token(str(user.id), str(user.organization_id))
    return schemas.TokenPair(access_token=access_token, refresh_token=new_raw)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(req: schemas.RefreshRequest, db: AsyncSession = Depends(get_db)):
    await service.revoke_refresh_token(db, req.refresh_token)


@router.get("/me", response_model=schemas.MeResponse)
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    org_result = await db.execute(select(Organization).where(Organization.id == user.organization_id))
    org = org_result.scalar_one()
    perms = await service.get_user_permissions(db, user)
    return schemas.MeResponse(
        user=schemas.UserOut.model_validate(user),
        organization=schemas.OrganizationOut.model_validate(org),
        permissions=sorted(perms),
    )


@users_router.get("", response_model=list[schemas.UserOut])
async def list_users(
    user: User = Depends(require_permission("users.manage")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User)
        .options(selectinload(User.roles))
        .where(User.organization_id == user.organization_id)
    )
    return result.scalars().all()


@users_router.get("/roles", response_model=list[schemas.RoleOut])
async def list_roles(
    user: User = Depends(require_permission("users.manage")),
    db: AsyncSession = Depends(get_db),
):
    """No endpoint exposed this before - every org's roles have existed
    since Phase 1 (register_organization seeds one row per
    DEFAULT_ROLE_GRANTS entry), but nothing ever let a caller list them,
    which silently blocked any UI for assigning a role by name rather than
    a hand-typed UUID. Added alongside the Users admin page that needs it."""
    result = await db.execute(select(Role).where(Role.organization_id == user.organization_id).order_by(Role.name))
    return result.scalars().all()


@users_router.post("", response_model=schemas.UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    req: schemas.CreateUserRequest,
    current_user: User = Depends(require_permission("users.manage")),
    db: AsyncSession = Depends(get_db),
):
    from app.core.security import hash_password

    existing = await db.execute(select(User).where(User.email == req.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    from app.modules.billing.service import check_user_limit
    await check_user_limit(db, current_user.organization_id)

    roles: list[Role] = []
    if req.role_ids:
        role_result = await db.execute(
            select(Role).where(
                Role.id.in_(req.role_ids),
                Role.organization_id == current_user.organization_id,  # tenant-scoped
            )
        )
        roles = list(role_result.scalars().all())

    new_user = User(
        organization_id=current_user.organization_id,
        email=req.email,
        phone=req.phone,
        full_name=req.full_name,
        password_hash=hash_password(req.password),
        roles=roles,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user


@users_router.patch("/{user_id}/roles", response_model=schemas.UserOut)
async def update_user_roles(
    user_id: uuid.UUID,
    req: schemas.UpdateUserRolesRequest,
    current_user: User = Depends(require_permission("users.manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await service.update_user_roles(
            db, current_user.organization_id, user_id, req.role_ids, current_user.id,
        )
    except ValueError as exc:
        if str(exc) == "user_not_found":
            raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
        raise


audit_router = APIRouter(prefix="/api/v1/audit-logs", tags=["audit"])


@audit_router.get("", response_model=list[schemas.AuditLogOut])
async def list_audit_logs(
    current_user: User = Depends(require_permission("audit.view")),
    db: AsyncSession = Depends(get_db),
):
    """First real consumer of AuditLog (see service.update_user_roles).
    Deliberately minimal - no pagination/filtering yet, since this is the
    only writer so far and org-scale audit volume is still low."""
    from app.modules.identity.models import AuditLog
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.organization_id == current_user.organization_id)
        .order_by(AuditLog.created_at.desc())
        .limit(200)
    )
    return result.scalars().all()


@organization_router.get("/settings", response_model=schemas.OrganizationOut)
async def get_organization_settings(
    user: User = Depends(require_permission("farm.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_organization(db, user.organization_id)


@organization_router.patch("/settings", response_model=schemas.OrganizationOut)
async def update_organization_settings(
    req: schemas.OrganizationSettingsUpdate,
    user: User = Depends(require_permission("farm.manage")),
    db: AsyncSession = Depends(get_db),
):
    """Spec §56/§57/§60 - currency, timezone, invoice/PO/employee/asset
    numbering prefixes, tax rate, default measurement units, all editable
    per organization instead of the fixed defaults every org previously
    launched with (KES/Africa/Nairobi/INV-/PO-/EMP-/AST-/0% tax/kg/L)."""
    return await service.update_organization_settings(db, user.organization_id, req)


@organization_router.post("/domain", response_model=schemas.DomainStatusOut)
async def set_organization_domain(
    req: schemas.DomainSetRequest,
    user: User = Depends(require_permission("farm.manage")),
    db: AsyncSession = Depends(get_db),
):
    """Sets/replaces this org's custom storefront domain and issues a fresh
    DNS TXT ownership-verification token. Does not mark it verified — call
    POST /domain/verify once the TXT record is published."""
    return await service.set_organization_domain(db, user.organization_id, req.domain)


@organization_router.get("/domain", response_model=schemas.DomainStatusOut)
async def get_organization_domain(
    user: User = Depends(require_permission("farm.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_organization_domain_status(db, user.organization_id)


@organization_router.post("/domain/verify", response_model=schemas.DomainStatusOut)
async def verify_organization_domain(
    user: User = Depends(require_permission("farm.manage")),
    db: AsyncSession = Depends(get_db),
):
    """Checks the DNS TXT record and flips domain_verified to True if it
    matches — safe to call repeatedly while waiting for DNS propagation."""
    return await service.verify_organization_domain(db, user.organization_id)


@organization_router.delete("/domain", status_code=status.HTTP_204_NO_CONTENT)
async def remove_organization_domain(
    user: User = Depends(require_permission("farm.manage")),
    db: AsyncSession = Depends(get_db),
):
    await service.remove_organization_domain(db, user.organization_id)


@router.post("/password-reset/request", status_code=status.HTTP_200_OK)
async def request_password_reset(
    req: schemas.PasswordResetRequest, request: Request, db: AsyncSession = Depends(get_db),
):
    """Same brute-force-relevant limiter as /register - a reset-request
    endpoint is exactly the kind of thing worth throttling (spec §29)."""
    await rate_limit_auth(request)
    await service.request_password_reset(db, req.email)
    # Identical message whether or not the email matched an account - see
    # service.request_password_reset's docstring for why that's deliberate.
    return {"detail": "If that email is registered, a password reset link has been sent."}


@router.post("/password-reset/confirm", status_code=status.HTTP_200_OK)
async def confirm_password_reset(req: schemas.PasswordResetConfirm, db: AsyncSession = Depends(get_db)):
    try:
        await service.confirm_password_reset(db, req.token, req.new_password)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired reset token")
    return {"detail": "Password updated. You can now log in with your new password."}
