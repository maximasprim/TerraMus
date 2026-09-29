"""Phase 3: animal lineage columns, breeding, dairy, inventory

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-10

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Lineage columns on the existing animals table (spec §7: family trees) ---
    op.add_column("animals", sa.Column("dam_id", pg.UUID(as_uuid=True), sa.ForeignKey("animals.id"), nullable=True))
    op.add_column("animals", sa.Column("sire_id", pg.UUID(as_uuid=True), sa.ForeignKey("animals.id"), nullable=True))
    op.create_index("ix_animals_dam_id", "animals", ["dam_id"])
    op.create_index("ix_animals_sire_id", "animals", ["sire_id"])

    # --- Breeding & Genetics ---
    op.create_table(
        "breeding_records",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("dam_id", pg.UUID(as_uuid=True), sa.ForeignKey("animals.id"), nullable=False),
        sa.Column("sire_id", pg.UUID(as_uuid=True), sa.ForeignKey("animals.id"), nullable=True),
        sa.Column("sire_external", sa.String(255), nullable=True),
        sa.Column("method", sa.String(32), nullable=False),
        sa.Column("mating_date", sa.Date, nullable=False),
        sa.Column("expected_delivery_date", sa.Date, nullable=True),
        sa.Column("pregnancy_status", sa.String(32), nullable=False, server_default="bred"),
        sa.Column("actual_delivery_date", sa.Date, nullable=True),
        sa.Column("offspring_count", sa.Integer, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("recorded_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("method in ('natural','artificial_insemination')", name="valid_method"),
        sa.CheckConstraint(
            "pregnancy_status in ('bred','confirmed_pregnant','not_pregnant','delivered','aborted')",
            name="valid_pregnancy_status",
        ),
    )
    op.create_index("ix_breeding_records_organization_id", "breeding_records", ["organization_id"])
    op.create_index("ix_breeding_records_dam_id", "breeding_records", ["dam_id"])
    op.create_index("ix_breeding_records_pregnancy_status", "breeding_records", ["pregnancy_status"])

    op.create_table(
        "pregnancy_checks",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("breeding_record_id", pg.UUID(as_uuid=True), sa.ForeignKey("breeding_records.id"), nullable=False),
        sa.Column("check_date", sa.Date, nullable=False),
        sa.Column("result", sa.String(16), nullable=False),
        sa.Column("notes", sa.String(255), nullable=True),
        sa.Column("performed_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("result in ('confirmed','not_pregnant','inconclusive')", name="valid_result"),
    )
    op.create_index("ix_pregnancy_checks_breeding_record_id", "pregnancy_checks", ["breeding_record_id"])
    op.execute("""
        CREATE TRIGGER pregnancy_checks_append_only
        BEFORE UPDATE OR DELETE ON pregnancy_checks
        FOR EACH ROW EXECUTE FUNCTION reject_audit_log_mutation();
    """)

    # --- Dairy Production ---
    op.create_table(
        "lactation_cycles",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("animal_id", pg.UUID(as_uuid=True), sa.ForeignKey("animals.id"), nullable=False),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_lactation_cycles_organization_id", "lactation_cycles", ["organization_id"])
    op.create_index("ix_lactation_cycles_animal_id", "lactation_cycles", ["animal_id"])
    op.create_index("ix_lactation_cycles_is_active", "lactation_cycles", ["is_active"])

    op.create_table(
        "milk_production_records",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("animal_id", pg.UUID(as_uuid=True), sa.ForeignKey("animals.id"), nullable=False),
        sa.Column("lactation_cycle_id", pg.UUID(as_uuid=True), sa.ForeignKey("lactation_cycles.id"), nullable=True),
        sa.Column("production_date", sa.Date, nullable=False),
        sa.Column("session", sa.String(16), nullable=False),
        sa.Column("quantity_liters", sa.Numeric(6, 2), nullable=False),
        sa.Column("rejected", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("rejection_reason", sa.String(255), nullable=True),
        sa.Column("recorded_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("session in ('morning','midday','evening')", name="valid_session"),
        sa.UniqueConstraint("animal_id", "production_date", "session", name="uq_milk_animal_date_session"),
    )
    op.create_index("ix_milk_records_organization_id", "milk_production_records", ["organization_id"])
    op.create_index("ix_milk_records_animal_id", "milk_production_records", ["animal_id"])
    op.create_index("ix_milk_records_production_date", "milk_production_records", ["production_date"])
    op.execute("""
        CREATE TRIGGER milk_production_records_append_only
        BEFORE UPDATE OR DELETE ON milk_production_records
        FOR EACH ROW EXECUTE FUNCTION reject_audit_log_mutation();
    """)

    # --- Feed & Inventory ---
    op.create_table(
        "inventory_items",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("farm_id", pg.UUID(as_uuid=True), sa.ForeignKey("farms.id"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("unit", sa.String(16), nullable=False),
        sa.Column("reorder_level", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("allow_negative_stock", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "category in ('feed','medicine','vaccine','supply','equipment','consumable')",
            name="valid_category",
        ),
    )
    op.create_index("ix_inventory_items_organization_id", "inventory_items", ["organization_id"])
    op.create_index("ix_inventory_items_category", "inventory_items", ["category"])

    op.create_table(
        "stock_movements",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("item_id", pg.UUID(as_uuid=True), sa.ForeignKey("inventory_items.id"), nullable=False),
        sa.Column("movement_type", sa.String(32), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 2), nullable=False),
        sa.Column("unit_cost", sa.Numeric(12, 2), nullable=True),
        sa.Column("batch_number", sa.String(64), nullable=True),
        sa.Column("expiry_date", sa.Date, nullable=True),
        sa.Column("animal_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("reference", sa.String(255), nullable=True),
        sa.Column("notes", sa.String(255), nullable=True),
        sa.Column("performed_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("moved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "movement_type in ('purchase','sale','consumption','transfer','adjustment','wastage','return','expired','opening_balance')",
            name="valid_movement_type",
        ),
    )
    op.create_index("ix_stock_movements_organization_id", "stock_movements", ["organization_id"])
    op.create_index("ix_stock_movements_item_id", "stock_movements", ["item_id"])
    op.create_index("ix_stock_movements_movement_type", "stock_movements", ["movement_type"])
    # Append-only ledger - corrections are new movements (e.g. 'adjustment'), never edits.
    op.execute("""
        CREATE TRIGGER stock_movements_append_only
        BEFORE UPDATE OR DELETE ON stock_movements
        FOR EACH ROW EXECUTE FUNCTION reject_audit_log_mutation();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS stock_movements_append_only ON stock_movements;")
    op.drop_table("stock_movements")
    op.drop_table("inventory_items")
    op.execute("DROP TRIGGER IF EXISTS milk_production_records_append_only ON milk_production_records;")
    op.drop_table("milk_production_records")
    op.drop_table("lactation_cycles")
    op.execute("DROP TRIGGER IF EXISTS pregnancy_checks_append_only ON pregnancy_checks;")
    op.drop_table("pregnancy_checks")
    op.drop_table("breeding_records")
    op.drop_index("ix_animals_sire_id", table_name="animals")
    op.drop_index("ix_animals_dam_id", table_name="animals")
    op.drop_column("animals", "sire_id")
    op.drop_column("animals", "dam_id")
