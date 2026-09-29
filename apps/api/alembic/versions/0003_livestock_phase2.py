"""Phase 2: animals, animal_events (timeline), weight_records, movements

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-09

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "animals",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("farm_id", pg.UUID(as_uuid=True), sa.ForeignKey("farms.id"), nullable=False),
        sa.Column("location_id", pg.UUID(as_uuid=True), sa.ForeignKey("locations.id"), nullable=True),
        sa.Column("animal_number", sa.String(64), nullable=False),
        sa.Column("ear_tag", sa.String(64), nullable=True),
        sa.Column("rfid", sa.String(64), nullable=True),
        sa.Column("species", sa.String(32), nullable=False),
        sa.Column("breed", sa.String(64), nullable=True),
        sa.Column("category", sa.String(32), nullable=True),
        sa.Column("sex", sa.String(8), nullable=False),
        sa.Column("name", sa.String(128), nullable=True),
        sa.Column("date_of_birth", sa.Date, nullable=True),
        sa.Column("estimated_birth_date", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("acquisition_date", sa.Date, nullable=False),
        sa.Column("acquisition_method", sa.String(32), nullable=False),
        sa.Column("acquisition_cost", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("current_value", sa.Numeric(12, 2), nullable=True),
        sa.Column("expected_sale_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("current_weight", sa.Numeric(8, 2), nullable=True),
        sa.Column("target_weight", sa.Numeric(8, 2), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("health_status", sa.String(32), nullable=False, server_default="healthy"),
        sa.Column("reproductive_status", sa.String(32), nullable=True),
        sa.Column("source", sa.String(128), nullable=True),
        sa.Column("previous_owner", sa.String(128), nullable=True),
        sa.Column("supplier", sa.String(128), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("sex in ('male','female')", name="valid_sex"),
        sa.CheckConstraint(
            "status in ('active','for_sale','reserved','sold','transferred','deceased','missing','quarantined','archived')",
            name="valid_status",
        ),
    )
    op.create_index("ix_animals_organization_id", "animals", ["organization_id"])
    op.create_index("ix_animals_farm_id", "animals", ["farm_id"])
    op.create_index("ix_animals_animal_number", "animals", ["animal_number"])
    op.create_index("ix_animals_status", "animals", ["status"])
    # Business rule: animal_number must be unique per organization (spec §60).
    op.create_unique_constraint("uq_animals_org_animal_number", "animals", ["organization_id", "animal_number"])

    op.create_table(
        "animal_events",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("animal_id", pg.UUID(as_uuid=True), sa.ForeignKey("animals.id"), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", pg.JSONB, nullable=True),
        sa.Column("recorded_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_animal_events_animal_id", "animal_events", ["animal_id"])

    op.create_table(
        "weight_records",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("animal_id", pg.UUID(as_uuid=True), sa.ForeignKey("animals.id"), nullable=False),
        sa.Column("weight_kg", sa.Numeric(8, 2), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("notes", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_weight_records_animal_id", "weight_records", ["animal_id"])

    op.create_table(
        "movements",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("animal_id", pg.UUID(as_uuid=True), sa.ForeignKey("animals.id"), nullable=False),
        sa.Column("from_location_id", pg.UUID(as_uuid=True), sa.ForeignKey("locations.id"), nullable=True),
        sa.Column("to_location_id", pg.UUID(as_uuid=True), sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("moved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("authorized_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("notes", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_movements_animal_id", "movements", ["animal_id"])

    # Append-only timeline tables, same principle as audit_logs (spec §7, §28).
    for table in ("animal_events", "weight_records", "movements"):
        op.execute(f"""
            CREATE TRIGGER {table}_append_only
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION reject_audit_log_mutation();
        """)


def downgrade() -> None:
    for table in ("animal_events", "weight_records", "movements"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table};")
    op.drop_table("movements")
    op.drop_table("weight_records")
    op.drop_table("animal_events")
    op.drop_table("animals")
