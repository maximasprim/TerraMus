"""Permanent deletion of a SUSPENDED organization (superadmin only).

How the data is found: nearly every tenant table carries an `organization_id` column, and a few child tables
(order items, weight records, user roles, ...) have none but point at a parent that does. Rather than hand-maintain a
list of ~90 tables that would silently go stale the next time a module is added, the plan is derived from the
SQLAlchemy metadata at request time: a table is "in scope" if it has `organization_id`, or foreign-keys a table that
is in scope. Rows are deleted children-first in one transaction, then the organization row itself, so a failure part
way (for example another organization's data still pointing at this one) rolls everything back untouched.

Left alone on purpose: global tables (permissions, subscription tiers, platform admins, scheduler state), and the
whole of `audit_logs`. It is append-only at the database level (a trigger rejects every DELETE) and has no foreign
key to organizations, so its rows simply outlive the organization - which also keeps the trail of what platform staff
did to it, plus the deletion entry written here.

Thirteen other tables (the finance and stock ledgers, animal / crop / employee / order history, ...) are append-only
the same way. Migration 0043 gives their trigger functions one narrow exception: a DELETE is allowed when the
transaction has set `app.org_purge = 'on'`, which this module does with SET LOCAL after all its checks pass. The flag
disappears when the transaction ends, UPDATEs stay forbidden, and nothing else in the app ever sets it.

Files in the storage bucket (listing photos, site images) are removed after the database commit, best effort.
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import and_, delete, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base, get_db
from app.core.middleware import rate_limit_auth
from app.core.security import verify_password
from app.modules.commerce import storage
from app.modules.identity.models import Organization
from app.modules.platform_admin import service
from app.modules.platform_admin.deps import get_current_platform_admin, require_write_access
from app.modules.platform_admin.models import PlatformAdmin

_log = logging.getLogger("app.platform_admin.org_deletion")

router = APIRouter(prefix="/api/v1/platform", tags=["platform-admin"])

# (table, columns holding bucket object keys) - cleaned up after the database commit when a bucket is configured.
_FILE_COLUMNS = (("listing_images", ("storage_key", "thumb_key")), ("site_images", ("storage_key",)))


class DeletionPreviewOut(BaseModel):
    organization_id: uuid.UUID
    organization_name: str
    is_suspended: bool
    total_records: int
    counts: dict[str, int]  # table -> rows that would be deleted (only tables with rows)


class DeleteOrganizationIn(BaseModel):
    confirm_name: str
    password: str


class DeleteOrganizationOut(BaseModel):
    deleted: bool
    organization_name: str
    total_records: int
    files_removed: int


def build_deletion_plan(org_id: uuid.UUID) -> list[tuple]:
    """[(table, where-clause)] in the order the deletes must run: children before the parents they point at."""
    tables = list(Base.metadata.sorted_tables)  # parents first
    scope: dict = {}
    for t in tables:
        if t.name != "organizations" and "organization_id" in t.c:
            scope[t] = t.c.organization_id == org_id
    changed = True
    while changed:  # child tables with no organization_id: in scope through a foreign key to a scoped table
        changed = False
        for t in tables:
            if t in scope or t.name == "organizations":
                continue
            for fk in t.foreign_keys:
                parent = fk.column.table
                if parent is t or parent not in scope:
                    continue
                scope[t] = fk.parent.in_(select(fk.column).where(scope[parent]))
                changed = True
                break
    # A few child tables point at several scoped parents (movements, order items, user roles, ...). Matching on just
    # one of them could, if a row ever linked two organizations, delete a row that belongs to ANOTHER organization.
    # So such a row is only deleted when EVERY link it has into the tenant tables points inside this organization;
    # otherwise it is left alone, which makes the deletion of its parent fail and the whole thing roll back safely.
    for t in tables:
        if t.name == "organizations" or "organization_id" in t.c or t not in scope:
            continue
        links = [fk for fk in t.foreign_keys if fk.column.table is not t and fk.column.table in scope]
        inside = [fk.parent.in_(select(fk.column).where(scope[fk.column.table])) for fk in links]
        scope[t] = or_(*inside) & and_(*[or_(fk.parent.is_(None), cond) for fk, cond in zip(links, inside)])
    plan = []
    for t in reversed(tables):
        if t not in scope:
            continue
        if t.name == "audit_logs":  # append-only, no FK to organizations: retained (see module docstring)
            continue
        plan.append((t, scope[t]))
    return plan


async def _load_org_for_superadmin(db: AsyncSession, org_id: uuid.UUID, admin: PlatformAdmin) -> Organization:
    if admin.role != "superadmin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only superadmins can delete an organization")
    org = (await db.execute(select(Organization).where(Organization.id == org_id))).scalar_one_or_none()
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")
    return org


async def _count_plan(db: AsyncSession, plan: list[tuple]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table, clause in plan:
        n = (await db.execute(select(func.count()).select_from(table).where(clause))).scalar_one()
        if n:
            counts[table.name] = int(n)
    return counts


@router.get("/organizations/{org_id}/deletion-preview", response_model=DeletionPreviewOut)
async def deletion_preview(
    org_id: uuid.UUID,
    admin: PlatformAdmin = Depends(get_current_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> DeletionPreviewOut:
    org = await _load_org_for_superadmin(db, org_id, admin)
    counts = await _count_plan(db, build_deletion_plan(org_id))
    counts["organizations"] = 1
    return DeletionPreviewOut(
        organization_id=org.id, organization_name=org.name, is_suspended=org.is_suspended,
        total_records=sum(counts.values()), counts=dict(sorted(counts.items(), key=lambda kv: -kv[1])),
    )


@router.post("/organizations/{org_id}/permanent-delete", response_model=DeleteOrganizationOut)
async def permanent_delete_organization(
    org_id: uuid.UUID,
    body: DeleteOrganizationIn,
    request: Request,
    admin: PlatformAdmin = Depends(require_write_access),
    db: AsyncSession = Depends(get_db),
) -> DeleteOrganizationOut:
    await rate_limit_auth(request)  # password guesses are limited like logins
    org = await _load_org_for_superadmin(db, org_id, admin)
    if not org.is_suspended:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a suspended organization can be deleted. Suspend it first.")
    if body.confirm_name.strip() != org.name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The name you typed does not match the organization's name")
    # 403 not 401: the console treats a 401 as "session expired" and signs the admin out.
    if not verify_password(body.password, admin.password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Incorrect password")

    org_name, org_slug = org.name, org.slug
    plan = build_deletion_plan(org_id)
    scope = {t.name: clause for t, clause in plan}

    file_keys: list[str] = []
    for table_name, columns in _FILE_COLUMNS:
        if table_name in scope:
            table = Base.metadata.tables[table_name]
            rows = await db.execute(select(*[table.c[c] for c in columns]).where(scope[table_name]))
            file_keys.extend(k for row in rows for k in row if k)

    counts = await _count_plan(db, plan)
    total = sum(counts.values()) + 1  # + the organization row
    try:
        # Transaction-local: lets the append-only triggers (migration 0043) allow DELETE for this transaction only.
        await db.execute(text("SET LOCAL app.org_purge = 'on'"))
        prefs = Base.metadata.tables.get("notification_preferences")
        users = Base.metadata.tables.get("users")
        if prefs is not None and users is not None and "user_id" in prefs.c and "users" in scope:
            # keyed by user id with no foreign key, so the generic plan cannot reach it
            await db.execute(delete(prefs).where(prefs.c.user_id.in_(select(users.c.id).where(scope["users"]))))
        for table, clause in plan:
            await db.execute(delete(table).where(clause))
        await db.execute(delete(Organization).where(Organization.id == org_id))
        # Written AFTER the deletes so it is not swept up by them; no foreign key, so it outlives the organization.
        await service.record_admin_action(
            db, org_id, admin.id, "platform_admin.organization.deleted", "organization", org_id,
            previous_value={"name": org_name, "slug": org_slug, "is_suspended": True},
            new_value={"records_deleted": total, "tables": counts},
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        _log.exception("Organization %s could not be deleted (rows elsewhere still refer to it)", org_id)
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Nothing was deleted: records elsewhere in the system still refer to this organization's data.",
        )
    except Exception:
        await db.rollback()
        _log.exception("Organization %s deletion failed", org_id)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Nothing was deleted: the deletion failed and was undone.")

    removed = 0
    cfg = storage.config_from_settings()
    if file_keys and cfg.use_bucket and cfg.configured:
        await storage.delete_objects(cfg, file_keys)
        removed = len(file_keys)
    return DeleteOrganizationOut(deleted=True, organization_name=org_name, total_records=total, files_removed=removed)