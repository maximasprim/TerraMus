import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.database import get_db
from app.core.security import decode_token
from app.modules.identity.models import User
from app.modules.identity.service import get_user_permissions

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = decode_token(token)
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    if payload.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token type")

    user_id = payload.get("sub")
    # One round trip (user + organization + roles joined) instead of three; the result is identical.
    result = await db.execute(
        select(User)
        .options(joinedload(User.roles), joinedload(User.organization))
        .where(User.id == uuid.UUID(user_id))
    )
    user = result.unique().scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    imp = payload.get("imp")
    if imp:
        # A superadmin's workspace session (platform_admin/impersonation.py). Re-checked on every request, so
        # deactivating or demoting the platform admin ends the session immediately. It may work inside a
        # suspended organization (that is how a superadmin sorts one out); `impersonated_by` makes
        # get_user_permissions grant every permission.
        from app.modules.platform_admin.models import PlatformAdmin

        try:
            admin = await db.get(PlatformAdmin, uuid.UUID(str(imp)))
        except ValueError:
            admin = None
        if not admin or not admin.is_active or admin.role != "superadmin":
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Workspace session is no longer valid")
        user.impersonated_by = admin.id
        return user
    # Platform-admin superuser feature: a suspended organization's users
    # are rejected here, which every tenant route already depends on via
    # this same function - so suspension takes effect everywhere at once
    # with no other route needing to change.
    if user.organization and user.organization.is_suspended:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This organization has been suspended")
    return user


class TenantContext:
    """Resolved on every authenticated request. All Phase 1+ queries must filter by
    `organization_id` - never trust a client-supplied org id (spec §4, §52.13)."""

    def __init__(self, user: User):
        self.user = user
        self.organization_id = user.organization_id


async def get_tenant_context(user: User = Depends(get_current_user)) -> TenantContext:
    return TenantContext(user)


def require_permission(permission_code: str):
    """Dependency factory: enforces permission-based RBAC (spec §5), not role-name checks."""

    async def _checker(
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        perms = await get_user_permissions(db, user)
        if permission_code not in perms:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Missing required permission: {permission_code}",
            )
        return user

    return _checker