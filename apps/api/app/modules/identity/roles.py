"""Owner-managed roles: the farm owner decides what each role in the organisation can do (and therefore see).

A role is just a named set of permission codes, and every request is already checked against those codes, so
changing a role's codes changes what its members can open - in the sidebar, on every page and on the API - at once.

Rules (each one enforced here, not in the UI):
  * only people with `users.manage` can use any of this, and only inside their own organisation
  * "Farm Owner" and "Customer" are locked: the first so an organisation can never lock itself out, the second
    because storefront customers are handled by ownership checks (the accounts module finds that role by name)
  * built-in roles keep their name (code looks some up by name) but their permissions can be changed, and put back
    to the shipped defaults with one call; custom roles can be created, edited and deleted
  * nobody can grant a permission they do not hold themselves (no promoting yourself or a friend past your own level)
  * an edit that would remove your own access to this screen is refused
  * a role still assigned to someone cannot be deleted
  * every change is written to the audit log and the permission cache is cleared straight away
"""
import uuid
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.modules.identity import service
from app.modules.identity.deps import require_permission
from app.modules.identity.models import AuditLog, Permission, Role, User, user_roles
from app.modules.identity.permissions import DEFAULT_ROLE_GRANTS, PERMISSIONS

roles_router = APIRouter(prefix="/api/v1/roles", tags=["roles"])

LOCKED_ROLES = {"Farm Owner", "Customer"}
MANAGE_CODE = "users.manage"

GROUP_LABELS = {
    "livestock": "Livestock", "health": "Animal health", "breeding": "Breeding", "dairy": "Dairy",
    "crops": "Crops", "finance": "Finance", "inventory": "Inventory", "procurement": "Procurement",
    "orders": "Orders", "listings": "Shop listings", "cms": "Website content", "payments": "Payments",
    "customers": "Customers", "users": "Team & roles", "farm": "Farms & settings", "reports": "Reports",
    "audit": "Audit log", "employees": "Employees", "assets": "Assets & fuel", "search": "Search",
    "feedlot": "Feedlot", "training": "Training", "groups": "Flocks, fish & rabbits", "fodder": "Fodder",
    "cycles": "Production cycles", "notifications": "Notifications", "animaltabs": "Tabs on an animal's page", "weighform": "Weigh form",
}
_KNOWN = {code for code, _ in PERMISSIONS}


# ---------------------------------------------------------------- schemas
class PermissionOut(BaseModel):
    code: str
    description: str
    group: str
    group_label: str


class RoleDetail(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    is_system: bool
    locked: bool                    # cannot be edited or deleted
    permissions: list[str]
    default_permissions: list[str] | None   # shipped defaults for a built-in role; None for custom roles
    differs_from_default: bool
    user_count: int


class RoleCatalog(BaseModel):
    permissions: list[PermissionOut]
    can_grant: list[str]            # the permissions the caller may hand out (those they hold)


class RoleCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=255)
    permissions: list[str] = []


class RoleUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=255)
    permissions: list[str] | None = None


# ---------------------------------------------------------------- helpers
def _group(code: str) -> str:
    return code.split(".", 1)[0]


def _err(code: int, msg: str) -> HTTPException:
    return HTTPException(code, msg)


async def _load_role(db: AsyncSession, org_id: uuid.UUID, role_id: uuid.UUID) -> Role:
    res = await db.execute(
        select(Role).options(selectinload(Role.permissions))
        .where(Role.id == role_id, Role.organization_id == org_id)    # tenant-scoped: other orgs' ids are a 404
    )
    role = res.scalar_one_or_none()
    if not role:
        raise _err(status.HTTP_404_NOT_FOUND, "Role not found")
    return role


async def _detail(db: AsyncSession, role: Role, user_count: int | None = None) -> RoleDetail:
    if user_count is None:
        user_count = (await db.execute(
            select(func.count()).select_from(user_roles).where(user_roles.c.role_id == role.id)
        )).scalar_one()
    codes = sorted(p.code for p in role.permissions)
    default = None
    if role.is_system and role.name in DEFAULT_ROLE_GRANTS:
        default = sorted(c for c in DEFAULT_ROLE_GRANTS[role.name] if c in _KNOWN)
    return RoleDetail(
        id=role.id, name=role.name, description=role.description, is_system=role.is_system,
        locked=role.is_system and role.name in LOCKED_ROLES,
        permissions=codes, default_permissions=default,
        differs_from_default=default is not None and default != codes, user_count=user_count,
    )


async def _check_codes(db: AsyncSession, codes: list[str]) -> list[Permission]:
    wanted = sorted(set(codes))
    unknown = [c for c in wanted if c not in _KNOWN]
    if unknown:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown permission: {', '.join(unknown)}")
    if not wanted:
        return []
    perm_map = await service.ensure_permission_catalog(db)       # rows already exist; this only fills any gap
    return [perm_map[c] for c in wanted]


async def _check_grantable(db: AsyncSession, caller: User, new_codes: set[str], current: set[str]) -> None:
    """You may only ADD permissions you hold yourself. Leaving one a role already has is always fine."""
    held = await service.get_user_permissions(db, caller)
    over = sorted(new_codes - current - held)
    if over:
        raise _err(status.HTTP_403_FORBIDDEN, f"You can't grant permissions you don't have: {', '.join(over)}")


async def _name_free(db: AsyncSession, org_id: uuid.UUID, name: str, exclude: uuid.UUID | None = None) -> None:
    q = select(Role.id).where(Role.organization_id == org_id, func.lower(Role.name) == name.lower())
    if exclude:
        q = q.where(Role.id != exclude)
    if (await db.execute(q)).first():
        raise _err(status.HTTP_409_CONFLICT, "A role with that name already exists")


def _audit(org_id, actor, action, role_id, before, after) -> AuditLog:
    return AuditLog(
        organization_id=org_id, user_id=actor, action=action, entity_type="role", entity_id=role_id,
        previous_value=before, new_value=after,
    )


async def _would_lock_self_out(db: AsyncSession, caller: User, role: Role, new_codes: set[str]) -> bool:
    """True if, after this edit, the caller would no longer hold users.manage through any of their roles."""
    if MANAGE_CODE in new_codes:
        return False
    if role.id not in {r.id for r in caller.roles}:
        return False
    other_ids = [r.id for r in caller.roles if r.id != role.id]
    if not other_ids:
        return True
    res = await db.execute(
        select(Permission.code).join(Role.permissions).where(Role.id.in_(other_ids), Permission.code == MANAGE_CODE)
    )
    return res.first() is None


# ---------------------------------------------------------------- routes
@roles_router.get("/catalog", response_model=RoleCatalog)
async def role_catalog(
    caller: User = Depends(require_permission(MANAGE_CODE)), db: AsyncSession = Depends(get_db),
):
    held = await service.get_user_permissions(db, caller)
    return RoleCatalog(
        permissions=[
            PermissionOut(code=c, description=d, group=_group(c), group_label=GROUP_LABELS.get(_group(c), _group(c).title()))
            for c, d in PERMISSIONS
        ],
        can_grant=sorted(held & _KNOWN),
    )


@roles_router.get("", response_model=list[RoleDetail])
async def list_role_details(
    caller: User = Depends(require_permission(MANAGE_CODE)), db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(Role).options(selectinload(Role.permissions))
        .where(Role.organization_id == caller.organization_id).order_by(Role.name)
    )
    roles = list(res.scalars().all())
    counts: dict[uuid.UUID, int] = defaultdict(int)
    rows = await db.execute(
        select(user_roles.c.role_id, func.count()).where(user_roles.c.role_id.in_([r.id for r in roles]))
        .group_by(user_roles.c.role_id)
    ) if roles else []
    for rid, n in rows:
        counts[rid] = n
    return [await _detail(db, r, counts[r.id]) for r in roles]


@roles_router.post("", response_model=RoleDetail, status_code=status.HTTP_201_CREATED)
async def create_role(
    req: RoleCreate, caller: User = Depends(require_permission(MANAGE_CODE)), db: AsyncSession = Depends(get_db),
):
    org_id = caller.organization_id
    await _name_free(db, org_id, req.name)
    perms = await _check_codes(db, req.permissions)
    await _check_grantable(db, caller, {p.code for p in perms}, set())
    role = Role(organization_id=org_id, name=req.name, description=req.description or None, is_system=False)
    role.permissions = perms
    db.add(role)
    await db.flush()
    db.add(_audit(org_id, caller.id, "role_created", role.id, None,
                  {"name": role.name, "permissions": sorted(p.code for p in perms)}))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise _err(status.HTTP_409_CONFLICT, "A role with that name already exists")
    service.invalidate_permission_cache()
    return await _detail(db, await _load_role(db, org_id, role.id), 0)


@roles_router.put("/{role_id}", response_model=RoleDetail)
async def update_role(
    role_id: uuid.UUID, req: RoleUpdate,
    caller: User = Depends(require_permission(MANAGE_CODE)), db: AsyncSession = Depends(get_db),
):
    org_id = caller.organization_id
    role = await _load_role(db, org_id, role_id)
    if role.is_system and role.name in LOCKED_ROLES:
        raise _err(status.HTTP_403_FORBIDDEN, f"The {role.name} role can't be changed")
    before = {"name": role.name, "description": role.description, "permissions": sorted(p.code for p in role.permissions)}

    if req.name is not None and req.name != role.name:
        if role.is_system:
            raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "Built-in roles can't be renamed")
        await _name_free(db, org_id, req.name, exclude=role.id)
        role.name = req.name
    if req.description is not None:
        role.description = req.description or None
    if req.permissions is not None:
        perms = await _check_codes(db, req.permissions)
        new_codes = {p.code for p in perms}
        await _check_grantable(db, caller, new_codes, {p.code for p in role.permissions})
        if await _would_lock_self_out(db, caller, role, new_codes):
            raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY,
                       "That change would remove your own access to Team & roles. Give yourself another role first.")
        role.permissions = perms

    after = {"name": role.name, "description": role.description, "permissions": sorted(p.code for p in role.permissions)}
    if after != before:
        db.add(_audit(org_id, caller.id, "role_updated", role.id, before, after))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise _err(status.HTTP_409_CONFLICT, "A role with that name already exists")
    service.invalidate_permission_cache()
    return await _detail(db, await _load_role(db, org_id, role.id))


@roles_router.post("/{role_id}/reset", response_model=RoleDetail)
async def reset_role(
    role_id: uuid.UUID, caller: User = Depends(require_permission(MANAGE_CODE)), db: AsyncSession = Depends(get_db),
):
    """Put a built-in role back to the permissions it shipped with."""
    org_id = caller.organization_id
    role = await _load_role(db, org_id, role_id)
    if not role.is_system or role.name not in DEFAULT_ROLE_GRANTS:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "Only built-in roles have defaults to restore")
    if role.name in LOCKED_ROLES:
        raise _err(status.HTTP_403_FORBIDDEN, f"The {role.name} role can't be changed")
    perms = await _check_codes(db, [c for c in DEFAULT_ROLE_GRANTS[role.name] if c in _KNOWN])
    new_codes = {p.code for p in perms}
    before_codes = sorted(p.code for p in role.permissions)
    await _check_grantable(db, caller, new_codes, set(before_codes))
    if await _would_lock_self_out(db, caller, role, new_codes):
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY,
                   "That change would remove your own access to Team & roles. Give yourself another role first.")
    role.permissions = perms
    db.add(_audit(org_id, caller.id, "role_reset", role.id, {"permissions": before_codes},
                  {"permissions": sorted(new_codes)}))
    await db.commit()
    service.invalidate_permission_cache()
    return await _detail(db, await _load_role(db, org_id, role.id))


@roles_router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: uuid.UUID, caller: User = Depends(require_permission(MANAGE_CODE)), db: AsyncSession = Depends(get_db),
):
    org_id = caller.organization_id
    role = await _load_role(db, org_id, role_id)
    if role.is_system:
        raise _err(status.HTTP_403_FORBIDDEN, "Built-in roles can't be deleted")
    in_use = (await db.execute(
        select(func.count()).select_from(user_roles).where(user_roles.c.role_id == role.id)
    )).scalar_one()
    if in_use:
        raise _err(status.HTTP_409_CONFLICT, f"{in_use} team member(s) still have this role. Move them to another role first.")
    db.add(_audit(org_id, caller.id, "role_deleted", role.id,
                  {"name": role.name, "permissions": sorted(p.code for p in role.permissions)}, None))
    role.permissions = []
    await db.flush()
    await db.delete(role)
    await db.commit()
    service.invalidate_permission_cache()
