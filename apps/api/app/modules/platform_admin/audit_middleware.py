"""Generic audit logging for the platform-admin write surface.

The alternative to this file was adding a `service.record_admin_action(...)`
call inside every one of the ~50 mutating endpoints across router.py and
tenant_crud_router.py - mechanical, error-prone to keep consistent (easy to
add endpoint #51 later and forget the call), and it duplicates the
org_id/admin_id/action/entity_type bookkeeping every single time. A
middleware does it once, structurally, for every current and future write
endpoint under /api/v1/platform/organizations/{org_id}/... without the
endpoint author needing to remember anything.

Three endpoints keep their own hand-written record_admin_action() calls
instead (org suspend/reactivate in router.py, livestock create/update) -
they were built before this middleware existed and capture richer detail
(previous_value/new_value diffs) than this generic version does. This
middleware explicitly skips those three paths (see SKIP_PATTERNS below) to
avoid double-logging the same action twice.
"""
import re
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

# Matches /api/v1/platform/organizations/{org_id}/{rest...} and captures
# org_id plus the first path segment after it (used as entity_type - e.g.
# "livestock", "customers", "procurement").
_ORG_PATH_RE = re.compile(
    r"^/api/v1/platform/organizations/(?P<org_id>[0-9a-fA-F-]{36})(?:/(?P<entity_type>[a-zA-Z0-9_-]+))?"
)

# Paths with their own richer, hand-written audit call - see module
# docstring. Matched by suffix since org_id varies.
_SKIP_SUFFIXES = (
    "/status",  # organizations/{id}/status (suspend/reactivate) - router.py logs this itself
)
_SKIP_EXACT_ENTITY_TYPES_WITH_METHOD = {
    # (entity_type, method): the livestock create/update handlers in
    # router.py already call record_admin_action themselves.
    ("livestock", "POST"),
    ("livestock", "PATCH"),
}

_WRITE_METHODS = ("POST", "PATCH", "PUT", "DELETE")


class PlatformAuditMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        if request.method not in _WRITE_METHODS:
            return response
        if not (200 <= response.status_code < 300):
            return response  # failed writes aren't audited as actions taken

        match = _ORG_PATH_RE.match(request.url.path)
        if not match:
            return response  # not a platform organizations write - e.g. /admins, /billing/*

        admin_id = getattr(request.state, "platform_admin_id", None)
        if admin_id is None:
            # require_write_access wasn't on this route's dependency chain
            # for some reason, or the request never reached it - nothing
            # to attribute the action to, so nothing to log.
            return response

        org_id = match.group("org_id")
        entity_type = match.group("entity_type") or "organization"

        if request.url.path.endswith(_SKIP_SUFFIXES):
            return response
        if (entity_type, request.method) in _SKIP_EXACT_ENTITY_TYPES_WITH_METHOD:
            return response

        await self._write_audit_row(org_id, admin_id, entity_type, request.method, request.url.path)
        return response

    @staticmethod
    async def _write_audit_row(org_id: str, admin_id, entity_type: str, method: str, path: str) -> None:
        # Deliberately a brand-new, independent session rather than reusing
        # the request's own `Depends(get_db)` session - by the time
        # BaseHTTPMiddleware's call_next returns, that session's lifecycle
        # is tied to the ASGI response being fully sent, not yet guaranteed
        # complete here. A short-lived session opened and closed entirely
        # within this function has no such ambiguity.
        from app.core.database import AsyncSessionLocal
        from app.modules.identity.models import AuditLog

        try:
            async with AsyncSessionLocal() as db:
                db.add(AuditLog(
                    organization_id=uuid.UUID(org_id),
                    user_id=admin_id if isinstance(admin_id, uuid.UUID) else uuid.UUID(str(admin_id)),
                    action=f"platform_admin.{method.lower()}",
                    entity_type=entity_type,
                    entity_id=None,  # not reliably parseable from the path alone across ~50 differently-shaped routes
                    new_value={"path": path},
                ))
                await db.commit()
        except Exception:
            # Audit logging must never break the actual request - the
            # write it's trying to log already succeeded and already
            # returned to the caller by this point regardless.
            import logging
            logging.getLogger("app.platform_admin.audit").exception(
                "Failed to write platform-admin audit log for %s %s", method, path,
            )
