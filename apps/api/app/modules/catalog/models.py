import uuid

from sqlalchemy import Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UUIDPKMixin, TimestampMixin


class TenantCatalogSettings(Base, UUIDPKMixin, TimestampMixin):
    """Per-tenant product-catalog visibility, set by a platform admin
    (spec: "superadmin controls what tenants want visible"). Entirely
    additive - one row per organization, created lazily the first time it's
    looked at (same pattern as billing.models.Subscription), so nothing
    about existing organizations or their queries changes.

    `enabled_species` / `enabled_crop_types` being NULL means "no
    restriction - show the entire current catalog", which is the default a
    newly-created row gets. This is deliberate: it means a brand new species
    or crop type added to livestock/catalog.py or crops/catalog.py in a
    future release is automatically visible to every tenant that hasn't been
    explicitly restricted, with no data migration needed to "backfill" the
    new option into every org's row.

    A platform admin narrows visibility by setting an explicit list (e.g.
    a poultry-only tenant might get `enabled_species=["poultry"]`), or turns
    an entire module off for a tenant that doesn't use it at all via the
    `*_enabled` flags.
    """
    __tablename__ = "tenant_catalog_settings"
    __table_args__ = (UniqueConstraint("organization_id", name="uq_tenant_catalog_settings_organization_id"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    livestock_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    crops_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Each is either None ("all") or an explicit JSON list of catalog codes.
    enabled_species: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    enabled_crop_types: Mapped[list | None] = mapped_column(JSONB, nullable=True)
