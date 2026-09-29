import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.models import TenantCatalogSettings
from app.modules.catalog import schemas
from app.modules.livestock.catalog import LIVESTOCK_SPECIES, SPECIES_CODES
from app.modules.crops.catalog import CROP_TYPES, CROP_TYPE_CODES


async def get_or_create_settings(db: AsyncSession, org_id: uuid.UUID) -> TenantCatalogSettings:
    """Lazy-creation, same pattern as billing.service.get_or_create_subscription:
    a row only starts existing once someone (a platform admin, or a tenant
    checking their own catalog) actually looks at it. Until then, every org
    behaves as if fully unrestricted - so this feature ships with zero effect
    on any existing organization."""
    result = await db.execute(
        select(TenantCatalogSettings).where(TenantCatalogSettings.organization_id == org_id)
    )
    settings = result.scalar_one_or_none()
    if settings:
        return settings
    settings = TenantCatalogSettings(organization_id=org_id)
    db.add(settings)
    await db.commit()
    await db.refresh(settings)
    return settings


async def update_settings(
    db: AsyncSession, org_id: uuid.UUID, req: schemas.TenantCatalogSettingsUpdate,
) -> TenantCatalogSettings:
    settings = await get_or_create_settings(db, org_id)
    if req.livestock_enabled is not None:
        settings.livestock_enabled = req.livestock_enabled
    if req.crops_enabled is not None:
        settings.crops_enabled = req.crops_enabled
    if req.clear_species_restriction:
        settings.enabled_species = None
    elif req.enabled_species is not None:
        settings.enabled_species = req.enabled_species
    if req.clear_crop_type_restriction:
        settings.enabled_crop_types = None
    elif req.enabled_crop_types is not None:
        settings.enabled_crop_types = req.enabled_crop_types
    await db.commit()
    await db.refresh(settings)
    return settings


async def is_species_allowed(db: AsyncSession, org_id: uuid.UUID, species: str) -> bool:
    settings = await get_or_create_settings(db, org_id)
    if not settings.livestock_enabled:
        return False
    if settings.enabled_species is None:
        return True  # unrestricted
    return species in settings.enabled_species


async def is_crop_type_allowed(db: AsyncSession, org_id: uuid.UUID, crop_type: str) -> bool:
    settings = await get_or_create_settings(db, org_id)
    if not settings.crops_enabled:
        return False
    if settings.enabled_crop_types is None:
        return True  # unrestricted
    return crop_type in settings.enabled_crop_types


async def get_effective_catalog(db: AsyncSession, org_id: uuid.UUID) -> schemas.EffectiveCatalogOut:
    """What this org's own users should see when building species/crop-type
    dropdowns - the reference catalog filtered down by whatever a platform
    admin has restricted for this tenant."""
    settings = await get_or_create_settings(db, org_id)

    species = [
        schemas.SpeciesCatalogEntryOut(code=code, label=label, suggested_categories=list(categories))
        for code, label, categories in LIVESTOCK_SPECIES
        if settings.enabled_species is None or code in settings.enabled_species
    ]
    crop_types = [
        schemas.CropTypeCatalogEntryOut(code=code, label=label, category=category, is_perennial=is_perennial, typical_yield_unit=unit)
        for code, label, category, is_perennial, unit in CROP_TYPES
        if settings.enabled_crop_types is None or code in settings.enabled_crop_types
    ]
    return schemas.EffectiveCatalogOut(
        livestock_enabled=settings.livestock_enabled,
        crops_enabled=settings.crops_enabled,
        species=species if settings.livestock_enabled else [],
        crop_types=crop_types if settings.crops_enabled else [],
    )


def full_species_reference() -> list[schemas.SpeciesCatalogEntryOut]:
    """The entire species catalog, unfiltered - for the platform-admin UI to
    build a "select which species this tenant can use" checklist."""
    return [
        schemas.SpeciesCatalogEntryOut(code=code, label=label, suggested_categories=list(categories))
        for code, label, categories in LIVESTOCK_SPECIES
    ]


def full_crop_type_reference() -> list[schemas.CropTypeCatalogEntryOut]:
    """The entire crop-type catalog, unfiltered - platform-admin equivalent
    of full_species_reference()."""
    return [
        schemas.CropTypeCatalogEntryOut(code=code, label=label, category=category, is_perennial=is_perennial, typical_yield_unit=unit)
        for code, label, category, is_perennial, unit in CROP_TYPES
    ]
