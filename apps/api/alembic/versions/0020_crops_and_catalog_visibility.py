"""Crop/plant production module + superadmin-controlled tenant catalog
visibility (species/crop-type gating).

Adds:
  - crop_plantings, crop_events, harvest_records (plant-production mirror of
    animals/animal_events/weight_records)
  - tenant_catalog_settings (per-org superadmin-controlled visibility of
    which livestock species / crop types are enabled)

Also backfills the new crops.* permissions onto every EXISTING
organization's system roles (Farm Owner, Farm Manager, Farm Worker) per the
updated DEFAULT_ROLE_GRANTS in identity/permissions.py, and creates the new
"Crop Manager" system role for every existing organization - without this,
an org created before this migration would never see the new permissions
show up on their existing roles (roles are seeded once, at org-registration
time, in application code - see identity/service.py register_organization).
Purely additive: no existing row is modified or removed, only new rows
inserted.

Revision ID: 0020
Revises: 0019
Create Date: 2026-09-26
"""
import uuid
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql as pg

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


NEW_PERMISSIONS = [
    ("crops.read", "View crop/plant planting records"),
    ("crops.create", "Register new crop plantings"),
    ("crops.update", "Update crop planting records"),
    ("crops.delete", "Delete/archive crop planting records"),
    ("crops.harvest", "Record crop harvests"),
]

# role name -> crops.* (and other newly-needed) permission codes to grant on
# every EXISTING organization's matching system role, mirroring
# identity/permissions.py DEFAULT_ROLE_GRANTS.
ROLE_PERMISSION_BACKFILL: dict[str, list[str]] = {
    "Farm Owner": [code for code, _ in NEW_PERMISSIONS],  # full access, as always
    "Farm Manager": ["crops.read", "crops.create", "crops.update", "crops.harvest"],
    "Farm Worker": ["crops.read", "crops.harvest"],
}

CROP_MANAGER_ROLE_NAME = "Crop Manager"
CROP_MANAGER_PERMISSIONS = ["crops.read", "crops.create", "crops.update", "crops.harvest", "reports.view", "search.use"]


def upgrade() -> None:
    # ---------------------------------------------------------------- tables --
    op.create_table(
        "crop_plantings",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("farm_id", pg.UUID(as_uuid=True), sa.ForeignKey("farms.id"), nullable=False),
        sa.Column("location_id", pg.UUID(as_uuid=True), sa.ForeignKey("locations.id"), nullable=True),
        sa.Column("planting_number", sa.String(64), nullable=False),
        sa.Column("crop_type", sa.String(32), nullable=False),
        sa.Column("variety", sa.String(64), nullable=True),
        sa.Column("is_perennial", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("area_size", sa.Numeric(10, 2), nullable=True),
        sa.Column("area_unit", sa.String(16), nullable=False, server_default="acres"),
        sa.Column("planting_date", sa.Date, nullable=False),
        sa.Column("planting_method", sa.String(32), nullable=True),
        sa.Column("expected_harvest_date", sa.Date, nullable=True),
        sa.Column("acquisition_cost", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("current_value", sa.Numeric(12, 2), nullable=True),
        sa.Column("expected_yield", sa.Numeric(12, 2), nullable=True),
        sa.Column("yield_unit", sa.String(16), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="growing"),
        sa.Column("health_status", sa.String(32), nullable=False, server_default="healthy"),
        sa.Column("source", sa.String(128), nullable=True),
        sa.Column("supplier", sa.String(128), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in ('growing','ready_for_harvest','harvesting','harvested','fallow','failed','archived')",
            name="valid_planting_status",
        ),
    )
    op.create_index("ix_crop_plantings_organization_id", "crop_plantings", ["organization_id"])
    op.create_index("ix_crop_plantings_farm_id", "crop_plantings", ["farm_id"])
    op.create_index("ix_crop_plantings_planting_number", "crop_plantings", ["planting_number"])
    op.create_index("ix_crop_plantings_status", "crop_plantings", ["status"])
    op.create_unique_constraint(
        "uq_crop_plantings_org_planting_number", "crop_plantings", ["organization_id", "planting_number"]
    )

    op.create_table(
        "crop_events",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("planting_id", pg.UUID(as_uuid=True), sa.ForeignKey("crop_plantings.id"), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", pg.JSONB, nullable=True),
        sa.Column("recorded_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_crop_events_planting_id", "crop_events", ["planting_id"])

    op.create_table(
        "harvest_records",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("planting_id", pg.UUID(as_uuid=True), sa.ForeignKey("crop_plantings.id"), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 2), nullable=False),
        sa.Column("unit", sa.String(16), nullable=False),
        sa.Column("quality_grade", sa.String(32), nullable=True),
        sa.Column("harvested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("notes", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_harvest_records_planting_id", "harvest_records", ["planting_id"])

    # Append-only timeline tables, same principle as animal_events/weight_records.
    for table in ("crop_events", "harvest_records"):
        op.execute(f"""
            CREATE TRIGGER {table}_append_only
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION reject_audit_log_mutation();
        """)

    op.create_table(
        "tenant_catalog_settings",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("livestock_enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("crops_enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("enabled_species", pg.JSONB, nullable=True),
        sa.Column("enabled_crop_types", pg.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tenant_catalog_settings_organization_id", "tenant_catalog_settings", ["organization_id"])
    op.create_unique_constraint(
        "uq_tenant_catalog_settings_organization_id", "tenant_catalog_settings", ["organization_id"]
    )

    # ------------------------------------------------------- permission backfill --
    bind = op.get_bind()
    now = datetime.now(timezone.utc)

    # 1. Insert the new permission codes into the global catalog (idempotent).
    existing_codes = {
        row[0] for row in bind.execute(text("SELECT code FROM permissions")).fetchall()
    }
    for code, description in NEW_PERMISSIONS:
        if code in existing_codes:
            continue
        bind.execute(
            text("INSERT INTO permissions (id, code, description) VALUES (:id, :code, :description)"),
            {"id": str(uuid.uuid4()), "code": code, "description": description},
        )

    # Re-fetch the full code->id map (covers both pre-existing codes like
    # reports.view/search.use, needed for the Crop Manager role below, and
    # the ones just inserted).
    perm_rows = bind.execute(text("SELECT id, code FROM permissions")).fetchall()
    perm_id_by_code = {code: str(pid) for pid, code in perm_rows}

    # 2. Grant the new crops.* permissions onto matching EXISTING system roles.
    role_rows = bind.execute(
        text("SELECT id, organization_id, name FROM roles WHERE is_system = true")
    ).fetchall()
    for role_id, org_id, role_name in role_rows:
        codes_to_grant = ROLE_PERMISSION_BACKFILL.get(role_name)
        if not codes_to_grant:
            continue
        for code in codes_to_grant:
            perm_id = perm_id_by_code.get(code)
            if not perm_id:
                continue
            bind.execute(
                text(
                    "INSERT INTO role_permissions (role_id, permission_id) VALUES (:role_id, :permission_id) "
                    "ON CONFLICT (role_id, permission_id) DO NOTHING"
                ),
                {"role_id": str(role_id), "permission_id": perm_id},
            )

    # 3. Create the new "Crop Manager" system role for every existing org that
    # doesn't already have one (fresh orgs get it automatically going forward
    # via identity/permissions.py DEFAULT_ROLE_GRANTS at registration time).
    org_rows = bind.execute(text("SELECT id FROM organizations")).fetchall()
    orgs_with_crop_manager = {
        org_id
        for org_id, in bind.execute(
            text("SELECT organization_id FROM roles WHERE name = :name"), {"name": CROP_MANAGER_ROLE_NAME}
        ).fetchall()
    }
    for org_id, in org_rows:
        if org_id in orgs_with_crop_manager:
            continue
        new_role_id = str(uuid.uuid4())
        bind.execute(
            text(
                "INSERT INTO roles (id, organization_id, name, description, is_system, created_at, updated_at) "
                "VALUES (:id, :org_id, :name, :description, true, :now, :now)"
            ),
            {
                "id": new_role_id, "org_id": str(org_id), "name": CROP_MANAGER_ROLE_NAME,
                "description": "Manages crop/plant production records", "now": now,
            },
        )
        for code in CROP_MANAGER_PERMISSIONS:
            perm_id = perm_id_by_code.get(code)
            if perm_id:
                bind.execute(
                    text("INSERT INTO role_permissions (role_id, permission_id) VALUES (:role_id, :permission_id)"),
                    {"role_id": new_role_id, "permission_id": perm_id},
                )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(text("DELETE FROM role_permissions WHERE permission_id IN "
                       "(SELECT id FROM permissions WHERE code LIKE 'crops.%')"))
    bind.execute(text("DELETE FROM roles WHERE name = :name"), {"name": CROP_MANAGER_ROLE_NAME})
    bind.execute(text("DELETE FROM permissions WHERE code LIKE 'crops.%'"))

    for table in ("crop_events", "harvest_records"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table};")
    op.drop_table("tenant_catalog_settings")
    op.drop_table("harvest_records")
    op.drop_table("crop_events")
    op.drop_table("crop_plantings")
