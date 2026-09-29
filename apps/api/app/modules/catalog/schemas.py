import uuid

from pydantic import BaseModel, ConfigDict


class SpeciesCatalogEntryOut(BaseModel):
    code: str
    label: str
    suggested_categories: list[str]


class CropTypeCatalogEntryOut(BaseModel):
    code: str
    label: str
    category: str
    is_perennial: bool
    typical_yield_unit: str


class TenantCatalogSettingsOut(BaseModel):
    """Raw superadmin-set restrictions for one org - None means unrestricted."""
    model_config = ConfigDict(from_attributes=True)
    organization_id: uuid.UUID
    livestock_enabled: bool
    crops_enabled: bool
    enabled_species: list[str] | None
    enabled_crop_types: list[str] | None


class TenantCatalogSettingsUpdate(BaseModel):
    """Platform-admin-only update. Omitted fields are left unchanged; passing
    an empty list ([]) for enabled_species/enabled_crop_types means "nothing
    visible" (distinct from omitting the field, which leaves the existing
    setting untouched, and from explicit null, which clears back to
    'unrestricted - show everything')."""
    livestock_enabled: bool | None = None
    crops_enabled: bool | None = None
    enabled_species: list[str] | None = None
    enabled_crop_types: list[str] | None = None
    clear_species_restriction: bool = False
    clear_crop_type_restriction: bool = False


class EffectiveCatalogOut(BaseModel):
    """What the tenant itself sees - resolved against the full reference
    catalog, for the frontend to build dropdowns/nav with. Served to any
    authenticated user of the org (read-only, no sensitive data)."""
    livestock_enabled: bool
    crops_enabled: bool
    species: list[SpeciesCatalogEntryOut]
    crop_types: list[CropTypeCatalogEntryOut]
