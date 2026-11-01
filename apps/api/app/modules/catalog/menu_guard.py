"""Backend enforcement of the menus a platform admin has hidden for a tenant.

Same approach as the Livestock / Crops switches (catalog/service.py): when a section is switched off for an
organization, NEW records can't be added to it and existing ones can't be changed through the API - but reading stays
open, so nothing already there disappears and other pages that happen to show a little of the same data keep working.

One shared check instead of one per module: a request is refused only when ALL of these hold
  * it is a write (POST / PUT / PATCH / DELETE);
  * it carries a valid tenant access token (public storefront calls, payment-provider webhooks, login/refresh and
    platform-admin calls have none, so they are never touched);
  * its path falls in an API area listed in AREAS below;
  * every menu that area belongs to is hidden for that tenant. Most areas belong to one menu; the few shared by two
    menus (production cycles: Cycles + Feedlot) stay open while at least one of them is visible.

Anything not listed in AREAS is never blocked - the check fails open, as does a missing settings row, an unreadable
token, or MENU_ENFORCEMENT=false in the environment (an instant off-switch). Existing organizations hide nothing, so
this changes nothing for them until a platform admin hides a menu.

KEEP IN SYNC with the admin pages: AREAS was derived from the API calls each admin page makes
(scripts/contract_audit); tests/test_menu_visibility.py checks every prefix here is a real route and every menu is real.
"""
from __future__ import annotations

import os
import uuid

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_token
from app.modules.catalog.menus import HIDEABLE_KEYS
from app.modules.catalog.models import TenantCatalogSettings

# API path prefix -> the menu(s) that use it. Longest matching prefix wins.
AREAS: dict[str, tuple[str, ...]] = {
    "/api/v1/livestock": ("/admin/livestock",),   # also covers .../breeding, .../dairy, .../health, .../photo
    "/api/v1/health": ("/admin/livestock",),
    "/api/v1/breeding": ("/admin/livestock",),
    "/api/v1/dairy": ("/admin/livestock",),
    "/api/v1/crops": ("/admin/crops",),
    "/api/v1/feedlot": ("/admin/feedlot",),
    "/api/v1/groups": ("/admin/groups",),
    "/api/v1/fodder": ("/admin/fodder",),
    "/api/v1/production-cycles": ("/admin/cycles", "/admin/feedlot"),  # Feedlot adopts/assigns records to cycles too
    "/api/v1/listings": ("/admin/listings",),
    "/api/v1/reservations": ("/admin/reservations",),
    "/api/v1/inventory": ("/admin/inventory",),
    "/api/v1/procurement": ("/admin/procurement",),
    "/api/v1/finance": ("/admin/finance",),
    "/api/v1/receivables": ("/admin/receivables",),
    "/api/v1/billing": ("/admin/billing",),
    "/api/v1/farms": ("/admin/farms",),
    "/api/v1/employees": ("/admin/employees",),
    "/api/v1/assets": ("/admin/assets",),
    "/api/v1/fuel": ("/admin/fuel",),
    "/api/v1/customers": ("/admin/customers",),
    "/api/v1/training": ("/admin/training",),
    "/api/v1/orders": ("/admin/orders",),
    "/api/v1/payments": ("/admin/orders",),       # recording a payment on an order (provider webhooks carry no token)
    "/api/v1/inquiries": ("/admin/inquiries",),
    "/api/v1/cms": ("/admin/cms",),
    "/api/v1/feedback": ("/admin/reviews",),
    "/api/v1/users": ("/admin/users",),
    "/api/v1/organization": ("/admin/settings",),
    # bulk import is one router serving several pages
    "/api/v1/bulk-import/livestock": ("/admin/livestock",),
    "/api/v1/bulk-import/crops": ("/admin/crops",),
    "/api/v1/bulk-import/customers": ("/admin/customers",),
    "/api/v1/bulk-import/suppliers": ("/admin/procurement",),
    "/api/v1/bulk-import/inventory-items": ("/admin/inventory",),
}
# deliberately NOT listed (never blocked): auth, account (customer portal), catalog, notifications, audit-logs, search,
# reports, media, public, platform.

WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
MESSAGE = "This section isn't available for your organization. Contact your platform administrator to have it enabled."


def enforcement_enabled() -> bool:
    return os.getenv("MENU_ENFORCEMENT", "true").strip().lower() not in ("0", "false", "no", "off")


def area_menus(path: str) -> tuple[str, ...] | None:
    """The menus that own `path`, or None if it isn't in a listed area. Longest prefix wins, on a path boundary."""
    best: str | None = None
    for prefix in AREAS:
        if (path == prefix or path.startswith(prefix + "/")) and (best is None or len(prefix) > len(best)):
            best = prefix
    return AREAS[best] if best else None


def is_blocked(path: str, method: str, hidden: list[str] | None) -> bool:
    """Pure decision (no I/O): would a `method` request to `path` be refused for a tenant hiding `hidden`?"""
    if method.upper() not in WRITE_METHODS or not hidden:
        return False
    menus = area_menus(path)
    if not menus:
        return False
    hidden_now = {m for m in hidden if m in HIDEABLE_KEYS}
    return all(menu in hidden_now for menu in menus)


def _tenant_org(request: Request) -> uuid.UUID | None:
    """The organization in a valid tenant access token, or None (no token, bad token, platform token, ...)."""
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    try:
        payload = decode_token(token)
        if payload.get("type") != "access" or not payload.get("org"):
            return None
        return uuid.UUID(str(payload["org"]))
    except Exception:
        return None


async def enforce_menu_visibility(request: Request, db: AsyncSession = Depends(get_db)) -> None:
    """App-wide dependency (see main.py). Does nothing - and touches no database - for reads and for any path that
    isn't in AREAS, which is nearly every request."""
    if request.method not in WRITE_METHODS or not enforcement_enabled() or area_menus(request.url.path) is None:
        return
    org_id = _tenant_org(request)
    if org_id is None:
        return
    try:
        hidden = (await db.execute(
            select(TenantCatalogSettings.hidden_menus).where(TenantCatalogSettings.organization_id == org_id)
        )).scalar_one_or_none()
    except Exception:
        return  # can't tell -> don't block; the route's own checks still apply
    if is_blocked(request.url.path, request.method, hidden):
        raise HTTPException(status.HTTP_403_FORBIDDEN, MESSAGE)
