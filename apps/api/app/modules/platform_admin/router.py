import uuid

from fastapi import APIRouter, Depends, Query, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.middleware import rate_limit_auth
from app.modules.platform_admin import schemas, service
from app.modules.platform_admin.deps import get_current_platform_admin, require_write_access
from app.modules.platform_admin.models import PlatformAdmin

# livestock reused as-is, unmodified, to prove the cross-tenant CRUD pattern -
# see the module docstring below for why this generalizes to every other
# module without duplicating business logic.
from app.modules.livestock import schemas as livestock_schemas, service as livestock_service
from app.modules.livestock.models import Animal
from app.modules.catalog import schemas as catalog_schemas, service as catalog_service
from app.modules.crops import schemas as crops_schemas, service as crops_service
from app.modules.crops.models import CropPlanting

router = APIRouter(prefix="/api/v1/platform", tags=["platform-admin"])

"""
Cross-tenant CRUD pattern used throughout this router
-------------------------------------------------------
Every tenant-facing service function in this codebase already takes
`org_id` as an explicit parameter (e.g. livestock.service.get_animal(db,
animal_id, org_id), .create_animal(db, org_id, user_id, req),
.update_animal(db, animal, req, user_id)) rather than pulling it from some
ambient/global context. That's what makes this router possible without
duplicating a single line of business logic: a normal tenant route derives
org_id from the caller's own JWT via get_tenant_context, and this router
instead takes org_id from the URL path (only reachable by an authenticated
platform admin - see get_current_platform_admin) and passes it to the exact
same service function. The livestock endpoints below are one fully worked
example; every other module's router.py follows the identical shape -
resolve org_id from the path instead of from TenantContext, then call the
same *.service functions - so extending this to health/breeding/dairy/
inventory/customers/finance/etc. is a mechanical copy of this pattern, not
new logic per module.
"""


@router.post("/auth/login", response_model=schemas.PlatformAdminTokenResponse)
async def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    # Same brute-force protection as tenant login (identity/router.py) -
    # reuses the identical dependency/limiter rather than a second one, so
    # there's one rate-limiting story to reason about, not two.
    await rate_limit_auth(request)
    token = await service.authenticate_platform_admin(db, form.username, form.password)
    return schemas.PlatformAdminTokenResponse(access_token=token)


@router.get("/auth/me", response_model=schemas.PlatformAdminOut)
async def me(admin: PlatformAdmin = Depends(get_current_platform_admin)):
    """Mirrors identity's GET /api/v1/auth/me - added for the UI (apps/web)
    to know who's logged in and, critically, their `role`, so it can hide
    write actions from a viewer client-side (the API enforces this
    regardless via require_write_access; this is purely so the UI doesn't
    show buttons that would just 403). Deliberately uses
    get_current_platform_admin, not require_write_access - reading your own
    identity is not a write, a viewer must be able to call this too."""
    return admin


@router.post("/auth/password-reset/request", status_code=200)
async def request_password_reset(
    request: Request, req: schemas.PlatformAdminPasswordResetRequest, db: AsyncSession = Depends(get_db),
):
    await rate_limit_auth(request)
    await service.request_platform_admin_password_reset(db, req.email)
    # Same generic response regardless of outcome as the tenant flow - never
    # reveals whether the email matches an account.
    return {"message": "If that email exists, a password reset link was sent."}


@router.post("/auth/password-reset/confirm", status_code=200)
async def confirm_password_reset(
    req: schemas.PlatformAdminPasswordResetConfirm, db: AsyncSession = Depends(get_db),
):
    await service.confirm_platform_admin_password_reset(db, req.token, req.new_password)
    return {"message": "Password has been reset."}


@router.get("/organizations", response_model=list[schemas.OrganizationSummaryOut])
async def list_organizations(
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    admin: PlatformAdmin = Depends(require_write_access),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_organizations(db, search, page, page_size)


@router.get("/organizations/{org_id}", response_model=schemas.OrganizationSummaryOut)
async def get_organization(
    org_id: uuid.UUID,
    admin: PlatformAdmin = Depends(require_write_access),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_organization_detail(db, org_id)


@router.patch("/organizations/{org_id}/status", response_model=schemas.OrganizationSummaryOut)
async def set_organization_status(
    org_id: uuid.UUID,
    req: schemas.OrganizationStatusUpdate,
    admin: PlatformAdmin = Depends(require_write_access),
    db: AsyncSession = Depends(get_db),
):
    """Suspending an org blocks every user in it from logging in or making
    authenticated requests from the very next request onward - enforced in
    identity.deps.get_current_user, which every tenant route already
    depends on, so no other route needed to change for suspension to take
    effect everywhere at once."""
    return await service.set_organization_status(db, org_id, admin.id, req.is_suspended, req.reason)


# ------------------------------------------------------ catalog visibility --
# Superadmin control over what a tenant sees/can use (spec: "superadmin
# controls what tenants want visible"). Reference-list endpoints are plain
# reads (any authenticated platform admin, viewer included); the per-org
# settings PATCH is a write and goes through require_write_access like every
# other mutation in this router.
@router.get("/catalog/species", response_model=list[catalog_schemas.SpeciesCatalogEntryOut])
async def list_species_catalog(admin: PlatformAdmin = Depends(get_current_platform_admin)):
    """The full livestock species reference catalog - for building the
    per-tenant 'which species can this org use' checklist in the admin UI."""
    return catalog_service.full_species_reference()


@router.get("/catalog/crop-types", response_model=list[catalog_schemas.CropTypeCatalogEntryOut])
async def list_crop_type_catalog(admin: PlatformAdmin = Depends(get_current_platform_admin)):
    """The full crop-type reference catalog, same purpose as the species list above."""
    return catalog_service.full_crop_type_reference()


@router.get("/organizations/{org_id}/catalog-settings", response_model=catalog_schemas.TenantCatalogSettingsOut)
async def get_org_catalog_settings(
    org_id: uuid.UUID,
    admin: PlatformAdmin = Depends(get_current_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    return await catalog_service.get_or_create_settings(db, org_id)


@router.patch("/organizations/{org_id}/catalog-settings", response_model=catalog_schemas.TenantCatalogSettingsOut)
async def update_org_catalog_settings(
    org_id: uuid.UUID,
    req: catalog_schemas.TenantCatalogSettingsUpdate,
    admin: PlatformAdmin = Depends(require_write_access),
    db: AsyncSession = Depends(get_db),
):
    """Narrow (or restore) which species/crop types this one tenant can use.
    Omitted fields are left as-is; see TenantCatalogSettingsUpdate's
    docstring for the distinction between omitting a list, passing [], and
    the explicit clear_*_restriction flags."""
    return await catalog_service.update_settings(db, org_id, req)


@router.get("/dashboard", response_model=schemas.PlatformDashboardStats)
async def dashboard(
    admin: PlatformAdmin = Depends(require_write_access),
    db: AsyncSession = Depends(get_db),
):
    return await service.dashboard_stats(db)


# --- platform admin account management --------------------------------------
# Deliberately requires an existing, authenticated platform admin to create
# another one - there is no public/self-service signup for this role. The
# very first platform admin is created out-of-band by scripts/seed_platform_admin.py.

@router.get("/admins", response_model=list[schemas.PlatformAdminOut])
async def list_admins(
    admin: PlatformAdmin = Depends(require_write_access),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_platform_admins(db)


@router.post("/admins", response_model=schemas.PlatformAdminOut)
async def create_admin(
    req: schemas.PlatformAdminCreateRequest,
    admin: PlatformAdmin = Depends(require_write_access),
    db: AsyncSession = Depends(get_db),
):
    return await service.create_platform_admin(db, req.email, req.full_name, req.password, req.role)


@router.patch("/admins/{admin_id}/role", response_model=schemas.PlatformAdminOut)
async def set_admin_role(
    admin_id: uuid.UUID,
    req: schemas.PlatformAdminRoleUpdate,
    admin: PlatformAdmin = Depends(require_write_access),
    db: AsyncSession = Depends(get_db),
):
    return await service.set_platform_admin_role(db, admin_id, req.role)


@router.patch("/admins/{admin_id}/status", response_model=schemas.PlatformAdminOut)
async def set_admin_status(
    admin_id: uuid.UUID,
    req: schemas.PlatformAdminStatusUpdate,
    admin: PlatformAdmin = Depends(require_write_access),
    db: AsyncSession = Depends(get_db),
):
    return await service.set_platform_admin_active(db, admin_id, req.is_active)


# --- subscription lifecycle --------------------------------------------------
# There is no task scheduler/cron in this codebase (checked: no celery,
# no APScheduler, nothing under infrastructure/ that runs periodic jobs) -
# so rather than inventing new infrastructure, this is exposed as a
# manually/externally-triggerable endpoint. Point a real cron job, k8s
# CronJob, or GitHub Actions scheduled workflow at it (e.g. daily) to
# actually automate it; calling it by hand also works fine for testing.

@router.post("/billing/run-lifecycle-check", response_model=schemas.LifecycleCheckResult)
async def run_lifecycle_check(
    admin: PlatformAdmin = Depends(require_write_access),
    db: AsyncSession = Depends(get_db),
):
    from app.modules.billing.service import expire_overdue_subscriptions
    return await expire_overdue_subscriptions(db)


# --- Cross-tenant CRUD example: livestock (see module docstring above) -----

@router.get("/organizations/{org_id}/livestock", response_model=list[livestock_schemas.AnimalOut])
async def list_org_livestock(
    org_id: uuid.UUID,
    admin: PlatformAdmin = Depends(require_write_access),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Animal).where(Animal.organization_id == org_id))
    return list(result.scalars().all())


@router.get("/organizations/{org_id}/livestock/{animal_id}", response_model=livestock_schemas.AnimalOut)
async def get_org_animal(
    org_id: uuid.UUID, animal_id: uuid.UUID,
    admin: PlatformAdmin = Depends(require_write_access),
    db: AsyncSession = Depends(get_db),
):
    return await livestock_service.get_animal(db, animal_id, org_id)


@router.post("/organizations/{org_id}/livestock", response_model=livestock_schemas.AnimalOut)
async def create_org_animal(
    org_id: uuid.UUID, req: livestock_schemas.AnimalCreate,
    admin: PlatformAdmin = Depends(require_write_access),
    db: AsyncSession = Depends(get_db),
):
    animal = await livestock_service.create_animal(db, org_id, admin.id, req)
    await service.record_admin_action(
        db, org_id, admin.id, action="livestock.create", entity_type="animal", entity_id=animal.id,
        new_value=req.model_dump(mode="json"),
    )
    await db.commit()
    return animal


@router.patch("/organizations/{org_id}/livestock/{animal_id}", response_model=livestock_schemas.AnimalOut)
async def update_org_animal(
    org_id: uuid.UUID, animal_id: uuid.UUID, req: livestock_schemas.AnimalUpdate,
    admin: PlatformAdmin = Depends(require_write_access),
    db: AsyncSession = Depends(get_db),
):
    animal = await livestock_service.get_animal(db, animal_id, org_id)
    updated = await livestock_service.update_animal(db, animal, req, admin.id)
    await service.record_admin_action(
        db, org_id, admin.id, action="livestock.update", entity_type="animal", entity_id=animal_id,
        new_value=req.model_dump(mode="json", exclude_unset=True),
    )
    await db.commit()
    return updated


@router.post("/organizations/{org_id}/livestock/{animal_id}/status", response_model=livestock_schemas.AnimalOut)
async def change_org_animal_status(
    org_id: uuid.UUID, animal_id: uuid.UUID, req: livestock_schemas.StatusChangeRequest,
    admin: PlatformAdmin = Depends(require_write_access),
    db: AsyncSession = Depends(get_db),
):
    """The closest thing to "delete" this product has for livestock -
    setting status to "archived", "sold", "deceased", etc. (see
    ANIMAL_STATUSES in livestock/models.py; these are exactly what the
    tenant's own POST /{animal_id}/status does). There is no hard delete
    for animals anywhere in this codebase, tenant-side or platform-side -
    a farm's herd financials and history depend on animal rows never
    disappearing, only changing status. This mirrors that, on purpose.
    Deliberately skips the tenant router's extra "livestock.sell requires
    livestock.sell permission" RBAC check - a platform admin isn't a
    tenant user bound by tenant RBAC at all, same as every other endpoint
    in this file."""
    animal = await livestock_service.get_animal(db, animal_id, org_id)
    updated = await livestock_service.change_status(db, animal, req, admin.id)
    await service.record_admin_action(
        db, org_id, admin.id, action="livestock.change_status", entity_type="animal", entity_id=animal_id,
        new_value={"status": req.status, "reason": req.reason},
    )
    await db.commit()
    return updated


# --- Cross-tenant CRUD: crops (same pattern as livestock above) -----------

@router.get("/organizations/{org_id}/crops", response_model=list[crops_schemas.CropPlantingOut])
async def list_org_crop_plantings(
    org_id: uuid.UUID,
    admin: PlatformAdmin = Depends(require_write_access),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(CropPlanting).where(CropPlanting.organization_id == org_id))
    return list(result.scalars().all())


@router.get("/organizations/{org_id}/crops/{planting_id}", response_model=crops_schemas.CropPlantingOut)
async def get_org_crop_planting(
    org_id: uuid.UUID, planting_id: uuid.UUID,
    admin: PlatformAdmin = Depends(require_write_access),
    db: AsyncSession = Depends(get_db),
):
    return await crops_service.get_planting(db, planting_id, org_id)


@router.post("/organizations/{org_id}/crops", response_model=crops_schemas.CropPlantingOut)
async def create_org_crop_planting(
    org_id: uuid.UUID, req: crops_schemas.CropPlantingCreate,
    admin: PlatformAdmin = Depends(require_write_access),
    db: AsyncSession = Depends(get_db),
):
    planting = await crops_service.create_planting(db, org_id, admin.id, req)
    await service.record_admin_action(
        db, org_id, admin.id, action="crops.create", entity_type="crop_planting", entity_id=planting.id,
        new_value=req.model_dump(mode="json"),
    )
    await db.commit()
    return planting


@router.patch("/organizations/{org_id}/crops/{planting_id}", response_model=crops_schemas.CropPlantingOut)
async def update_org_crop_planting(
    org_id: uuid.UUID, planting_id: uuid.UUID, req: crops_schemas.CropPlantingUpdate,
    admin: PlatformAdmin = Depends(require_write_access),
    db: AsyncSession = Depends(get_db),
):
    planting = await crops_service.get_planting(db, planting_id, org_id)
    updated = await crops_service.update_planting(db, planting, req, admin.id)
    await service.record_admin_action(
        db, org_id, admin.id, action="crops.update", entity_type="crop_planting", entity_id=planting_id,
        new_value=req.model_dump(mode="json", exclude_unset=True),
    )
    await db.commit()
    return updated


@router.post("/organizations/{org_id}/crops/{planting_id}/status", response_model=crops_schemas.CropPlantingOut)
async def change_org_crop_planting_status(
    org_id: uuid.UUID, planting_id: uuid.UUID, req: crops_schemas.StatusChangeRequest,
    admin: PlatformAdmin = Depends(require_write_access),
    db: AsyncSession = Depends(get_db),
):
    """Same "closest thing to delete" reasoning as livestock's status
    endpoint above - "failed"/"archived" are crops' terminal states."""
    planting = await crops_service.get_planting(db, planting_id, org_id)
    updated = await crops_service.change_status(db, planting, req, admin.id)
    await service.record_admin_action(
        db, org_id, admin.id, action="crops.change_status", entity_type="crop_planting", entity_id=planting_id,
        new_value={"status": req.status, "reason": req.reason},
    )
    await db.commit()
    return updated
