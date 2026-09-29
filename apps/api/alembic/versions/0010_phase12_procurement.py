"""Phase 12: procurement (suppliers, purchase orders)

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-05

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "suppliers",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("contact_person", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("address", sa.String(255), nullable=True),
        sa.Column("tax_pin", sa.String(64), nullable=True),
        sa.Column("products_supplied", sa.Text, nullable=True),
        sa.Column("payment_terms", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_suppliers_organization_id", "suppliers", ["organization_id"])

    op.create_table(
        "purchase_order_counters",
        sa.Column("organization_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("next_number", sa.Integer, nullable=False, server_default="1"),
    )

    op.create_table(
        "purchase_orders",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("supplier_id", pg.UUID(as_uuid=True), sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("po_number", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="requested"),
        sa.Column("order_date", sa.Date, nullable=True),
        sa.Column("expected_delivery_date", sa.Date, nullable=True),
        sa.Column("notes", sa.String(255), nullable=True),
        sa.Column("requested_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in ('requested','approved','ordered','received','invoiced','paid','rejected','cancelled')",
            name="valid_purchase_order_status",
        ),
    )
    op.create_index("ix_purchase_orders_organization_id", "purchase_orders", ["organization_id"])
    op.create_index("ix_purchase_orders_supplier_id", "purchase_orders", ["supplier_id"])
    op.create_index("ix_purchase_orders_status", "purchase_orders", ["status"])
    op.create_index("ix_purchase_orders_po_number", "purchase_orders", ["po_number"])

    op.create_table(
        "purchase_order_items",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("purchase_order_id", pg.UUID(as_uuid=True), sa.ForeignKey("purchase_orders.id"), nullable=False),
        sa.Column("inventory_item_id", pg.UUID(as_uuid=True), sa.ForeignKey("inventory_items.id"), nullable=True),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 2), nullable=False),
        sa.Column("unit_cost", sa.Numeric(12, 2), nullable=False),
    )
    op.create_index("ix_purchase_order_items_purchase_order_id", "purchase_order_items", ["purchase_order_id"])
    op.create_index("ix_purchase_order_items_inventory_item_id", "purchase_order_items", ["inventory_item_id"])

    op.create_table(
        "purchase_order_status_events",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("purchase_order_id", pg.UUID(as_uuid=True), sa.ForeignKey("purchase_orders.id"), nullable=False),
        sa.Column("from_status", sa.String(16), nullable=True),
        sa.Column("to_status", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("changed_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_purchase_order_status_events_purchase_order_id",
        "purchase_order_status_events", ["purchase_order_id"],
    )
    # Same append-only guarantee as audit_logs/order_status_events (spec §28),
    # reusing the trigger function defined once in migration 0002.
    op.execute("""
        CREATE TRIGGER purchase_order_status_events_append_only
        BEFORE UPDATE OR DELETE ON purchase_order_status_events
        FOR EACH ROW EXECUTE FUNCTION reject_audit_log_mutation();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS purchase_order_status_events_append_only ON purchase_order_status_events;")
    op.drop_table("purchase_order_status_events")
    op.drop_table("purchase_order_items")
    op.drop_table("purchase_orders")
    op.drop_table("purchase_order_counters")
    op.drop_table("suppliers")
