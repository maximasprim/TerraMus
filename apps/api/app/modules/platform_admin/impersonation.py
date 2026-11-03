"""Superadmin "open this tenant's workspace".

Instead of re-building every tenant screen inside the platform console, a superadmin can open the tenant's own
admin app *as* that organization. Everything a tenant can do on every menu then works for the superadmin, and
stays correct automatically when new tenant menus or features are added.

How it works
  * POST /api/v1/platform/organizations/{org_id}/workspace-session (superadmin only - `require_write_access`
    refuses viewer admins for every non-GET request) mints a normal tenant access token for the organization's
    owner account, carrying an extra `imp` claim = the platform admin's id. Short lived, no refresh token.
  * identity.deps.get_current_user recognises `imp`: it re-checks on EVERY request that the platform admin still
    exists, is active and is a superadmin (so deactivating them cuts the session off at once), lets the session
    work even in a suspended organization, and marks the user so get_user_permissions grants every permission.
  * catalog.menu_guard ignores `imp` tokens, so menus hidden for the tenant never block the superadmin.
  * ImpersonationAuditMiddleware writes one audit row (attributed to the PLATFORM ADMIN, not the owner) for every
    successful write made with such a token. Issuing the session is audited by PlatformAuditMiddleware.

Nothing here changes how normal tenant tokens work: without an `imp` claim every code path is exactly as before.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

from app.core.database import get_db
from app.core.security import create_access_token, decode_token
from app.modules.identity.models import Organization, Role, User, user_roles
from app.modules.platform_admin.deps import require_write_access
from app.modules.platform_admin.models import PlatformAdmin

IMPERSONATION_CLAIM = "imp"
WORKSPACE_SESSION_MINUTES = 120
OWNER_ROLE_NAME = "Farm Owner"

_log = logging.getLogger("app.platform_admin.impersonation")

router = APIRouter(prefix="/api/v1/platform", tags=["platform-admin"])


class WorkspaceSessionOut(BaseModel):
    access_token: str
    expires_at: datetime
    organization_id: uuid.UUID
    organization_name: str
    acting_as: str  # the tenant account the session runs under (shown in the banner)


async def pick_acting_user(db: AsyncSession, org_id: uuid.UUID) -> User | None:
    """The account a workspace session runs under: the organization's Farm Owner if it has one, otherwise its
    oldest active staff account. Customer (shop) accounts are never used."""
    stmt = (
        select(User)
        .outerjoin(user_roles, user_roles.c.user_id == User.id)
        .outerjoin(Role, Role.id == user_roles.c.role_id)
        .where(User.organization_id == org_id, User.is_active.is_(True), User.customer_id.is_(None))
        .order_by((Role.name == OWNER_ROLE_NAME).desc(), User.created_at.asc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalars().first()


@router.post("/organizations/{org_id}/workspace-session", response_model=WorkspaceSessionOut)
async def open_workspace_session(
    org_id: uuid.UUID,
    admin: PlatformAdmin = Depends(require_write_access),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceSessionOut:
    org = (await db.execute(select(Organization).where(Organization.id == org_id))).scalar_one_or_none()
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")
    if admin.role != "superadmin":  # belt and braces: require_write_access already refuses non-GET for viewers
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only superadmins can open a tenant workspace")
    acting = await pick_acting_user(db, org_id)
    if acting is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This organization has no active staff account to open a workspace under. Create or reactivate one first.",
        )
    expires = datetime.now(timezone.utc) + timedelta(minutes=WORKSPACE_SESSION_MINUTES)
    token = create_access_token(
        subject=str(acting.id), org_id=str(org_id), extra={IMPERSONATION_CLAIM: str(admin.id), "exp": expires},
    )
    return WorkspaceSessionOut(
        access_token=token, expires_at=expires, organization_id=org_id,
        organization_name=org.name, acting_as=acting.full_name,
    )


_WRITE_METHODS = ("POST", "PATCH", "PUT", "DELETE")


class ImpersonationAuditMiddleware(BaseHTTPMiddleware):
    """One audit row per successful write made through a workspace session, attributed to the platform admin."""

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.method not in _WRITE_METHODS or not (200 <= response.status_code < 300):
            return response
        path = request.url.path
        if not path.startswith("/api/v1/") or path.startswith("/api/v1/platform"):
            return response
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token:
            return response
        try:
            payload = decode_token(token)
        except Exception:
            return response
        imp = payload.get(IMPERSONATION_CLAIM)
        if not imp or payload.get("type") != "access" or not payload.get("org"):
            return response
        await self._write_audit_row(str(payload["org"]), str(imp), str(payload.get("sub")), request.method, path)
        return response

    @staticmethod
    async def _write_audit_row(org_id: str, admin_id: str, acting_as: str, method: str, path: str) -> None:
        from app.core.database import AsyncSessionLocal
        from app.modules.identity.models import AuditLog

        parts = path.split("/")  # ['', 'api', 'v1', '<area>', ...]
        entity_type = parts[3] if len(parts) > 3 and parts[3] else "workspace"
        try:
            async with AsyncSessionLocal() as db:
                db.add(AuditLog(
                    organization_id=uuid.UUID(org_id),
                    user_id=uuid.UUID(admin_id),
                    action=f"platform_admin.workspace.{method.lower()}",
                    entity_type=entity_type[:128],
                    entity_id=None,
                    new_value={"path": path, "acting_as_user_id": acting_as},
                ))
                await db.commit()
        except Exception:
            _log.exception("Failed to write workspace-session audit log for %s %s", method, path)
