"""Phase 14: farm asset management (spec §15)

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-05

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_number", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("asset_type", sa.String(32), nullable=False),
        sa.Column("serial_number", sa.String(128), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="in_use"),
        sa.Column("condition", sa.String(16), nullable=False, server_default="good"),
        sa.Column("acquisition_date", sa.Date, nullable=True),
        sa.Column("acquisition_cost", sa.Numeric(12, 2), nullable=True),
        sa.Column("useful_life_years", sa.Integer, nullable=True),
        sa.Column("salvage_value", sa.Numeric(12, 2), nullable=True),
        sa.Column("warranty_expiry", sa.Date, nullable=True),
        sa.Column("assigned_farm_id", pg.UUID(as_uuid=True), sa.ForeignKey("farms.id"), nullable=True),
        sa.Column("assigned_location_id", pg.UUID(as_uuid=True), sa.ForeignKey("locations.id"), nullable=True),
        sa.Column("supplier_id", pg.UUID(as_uuid=True), sa.ForeignKey("suppliers.id"), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "asset_type in ('tractor','vehicle','pump','generator','milking_equipment',"
            "'water_system','building','fence','tool','machinery','other')",
            name="valid_asset_type",
        ),
        sa.CheckConstraint(
            "condition in ('excellent','good','fair','poor','out_of_service')",
            name="valid_asset_condition",
        ),
        sa.CheckConstraint(
            "status in ('in_use','in_storage','under_maintenance','disposed')",
            name="valid_asset_status",
        ),
    )
    op.create_index("ix_assets_organization_id", "assets", ["organization_id"])
    op.create_index("ix_assets_asset_number", "assets", ["asset_number"])
    op.create_index("ix_assets_asset_type", "assets", ["asset_type"])
    op.create_index("ix_assets_status", "assets", ["status"])

    op.create_table(
        "asset_maintenance_records",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("asset_id", pg.UUID(as_uuid=True), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("maintenance_type", sa.String(16), nullable=False),
        sa.Column("maintenance_date", sa.Date, nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("cost", sa.Numeric(12, 2), nullable=True),
        sa.Column("performed_by", sa.String(255), nullable=True),
        sa.Column("next_due_date", sa.Date, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "maintenance_type in ('service','repair','inspection')",
            name="valid_maintenance_type",
        ),
    )
    op.create_index("ix_asset_maintenance_records_asset_id", "asset_maintenance_records", ["asset_id"])
    op.create_index("ix_asset_maintenance_records_maintenance_date", "asset_maintenance_records", ["maintenance_date"])

    op.create_table(
        "asset_counters",
        sa.Column("organization_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("next_number", sa.Integer, nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_table("asset_counters")
    op.drop_table("asset_maintenance_records")
    op.drop_table("assets")
