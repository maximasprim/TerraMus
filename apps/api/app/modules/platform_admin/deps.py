import uuid

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_token
from app.modules.platform_admin.models import PlatformAdmin

# A distinct tokenUrl from the tenant scheme (app/modules/identity/deps.py's
# oauth2_scheme) purely for OpenAPI/docs clarity in Swagger UI - the actual
# enforcement is the "type" claim check below, not this URL.
platform_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/platform/auth/login", auto_error=False)


async def get_current_platform_admin(
    token: str | None = Depends(platform_oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> PlatformAdmin:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = decode_token(token)
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    # This is the actual security boundary: a normal tenant user's token has
    # type == "access" and is rejected here regardless of anything else in
    # the payload, and a platform-admin token is equally rejected by the
    # tenant-side get_current_user (which requires type == "access"). See
    # security.py's module docstring for the full reasoning.
    if payload.get("type") != "platform_admin":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token type")

    admin_id = payload.get("sub")
    result = await db.execute(select(PlatformAdmin).where(PlatformAdmin.id == uuid.UUID(admin_id)))
    admin = result.scalar_one_or_none()
    if not admin or not admin.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Platform admin not found or inactive")
    return admin


async def require_write_access(
    request: Request,
    admin: PlatformAdmin = Depends(get_current_platform_admin),
) -> PlatformAdmin:
    """Any authenticated platform admin (superadmin or viewer) can GET/HEAD/
    OPTIONS. Only "superadmin" can do anything else. This is checked by
    HTTP method, not per-endpoint, which is what makes it practical to
    apply to tenant_crud_router.py's ~50 endpoints in one place (its
    router-level `dependencies=[...]`) instead of adding a role check to
    every individual function - new endpoints added there later are
    automatically covered too, with no extra step required."""
    if request.method not in ("GET", "HEAD", "OPTIONS") and admin.role != "superadmin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Viewer admins cannot perform write operations")
    # Stashed here (not just returned) so PlatformAuditMiddleware can read
    # who made the request without needing its own auth/token-decoding
    # logic - this dependency has already done that work once.
    request.state.platform_admin_id = admin.id
    return admin
