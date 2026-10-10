import uuid

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.modules.crops.catalog import CROP_TYPE_CODES
from app.modules.livestock.catalog import SPECIES_CODES


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

    # An unknown code used to be stored as-is, so a typo silently locked the
    # tenant out of a species/crop type. Reject it, and drop duplicates.
    @field_validator("enabled_species")
    @classmethod
    def _known_species(cls, v: list[str] | None) -> list[str] | None:
        return _known_codes(v, SPECIES_CODES, "species")

    @field_validator("enabled_crop_types")
    @classmethod
    def _known_crop_types(cls, v: list[str] | None) -> list[str] | None:
        return _known_codes(v, CROP_TYPE_CODES, "crop types")

    @model_validator(mode="after")
    def _no_conflicting_instructions(self):
        # "clear the restriction" and "restrict to this list" in one request
        # used to resolve silently in favour of clear; make it explicit.
        if self.clear_species_restriction and self.enabled_species is not None:
            raise ValueError("Send either enabled_species or clear_species_restriction, not both")
        if self.clear_crop_type_restriction and self.enabled_crop_types is not None:
            raise ValueError("Send either enabled_crop_types or clear_crop_type_restriction, not both")
        return self


def _known_codes(values: list[str] | None, valid: tuple[str, ...], label: str) -> list[str] | None:
    if values is None:
        return None
    unknown = sorted({v for v in values if v not in valid})
    if unknown:
        raise ValueError(f"Unknown {label}: {', '.join(unknown)}")
    return list(dict.fromkeys(values))  # de-duplicate, keep order


class EffectiveCatalogOut(BaseModel):
    """What the tenant itself sees - resolved against the full reference
    catalog, for the frontend to build dropdowns/nav with. Served to any
    authenticated user of the org (read-only, no sensitive data)."""
    livestock_enabled: bool
    crops_enabled: bool
    species: list[SpeciesCatalogEntryOut]
    crop_types: list[CropTypeCatalogEntryOut]
