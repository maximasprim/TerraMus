"""Phase 4: customers, listings, reservations, orders

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-10

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("customer_type", sa.String(32), nullable=False, server_default="individual"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "customer_type in ('individual','butcher','hotel','restaurant','institution','livestock_trader','wholesaler','farm','corporate')",
            name="valid_customer_type",
        ),
    )
    op.create_index("ix_customers_organization_id", "customers", ["organization_id"])
    op.create_index("ix_customers_email", "customers", ["email"])

    op.create_table(
        "listings",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("animal_id", pg.UUID(as_uuid=True), sa.ForeignKey("animals.id"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("pricing_type", sa.String(32), nullable=False, server_default="fixed"),
        sa.Column("price", sa.Numeric(12, 2), nullable=True),
        sa.Column("featured", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("pricing_type in ('fixed','negotiable','price_on_request')", name="valid_pricing_type"),
    )
    op.create_index("ix_listings_organization_id", "listings", ["organization_id"])
    op.create_index("ix_listings_animal_id", "listings", ["animal_id"])
    # Spec §17 - only one *active* listing per animal at a time (partial unique index).
    op.execute("""
        CREATE UNIQUE INDEX uq_listings_active_animal
        ON listings (animal_id)
        WHERE is_active = true;
    """)

    op.create_table(
        "reservations",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("animal_id", pg.UUID(as_uuid=True), sa.ForeignKey("animals.id"), nullable=False),
        sa.Column("customer_id", pg.UUID(as_uuid=True), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("reservation_date", sa.Date, nullable=False),
        sa.Column("expiry_date", sa.Date, nullable=False),
        sa.Column("deposit_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("notes", sa.String(255), nullable=True),
        sa.Column("created_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status in ('active','completed','expired','cancelled')", name="valid_reservation_status"),
    )
    op.create_index("ix_reservations_organization_id", "reservations", ["organization_id"])
    op.create_index("ix_reservations_animal_id", "reservations", ["animal_id"])
    op.create_index("ix_reservations_customer_id", "reservations", ["customer_id"])
    op.create_index("ix_reservations_status", "reservations", ["status"])
    # Spec §18/§52.2 - only one *active* reservation per animal at a time.
    op.execute("""
        CREATE UNIQUE INDEX uq_reservations_active_animal
        ON reservations (animal_id)
        WHERE status = 'active';
    """)

    op.create_table(
        "orders",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", pg.UUID(as_uuid=True), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("delivery_option", sa.String(16), nullable=False, server_default="pickup"),
        sa.Column("delivery_address", sa.String(255), nullable=True),
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("notes", sa.String(255), nullable=True),
        sa.Column("created_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in ('pending','payment_pending','paid','processing','ready_for_fulfillment',"
            "'dispatched','delivered','completed','cancelled','refunded','partially_refunded','failed')",
            name="valid_order_status",
        ),
    )
    op.create_index("ix_orders_organization_id", "orders", ["organization_id"])
    op.create_index("ix_orders_customer_id", "orders", ["customer_id"])
    op.create_index("ix_orders_status", "orders", ["status"])

    op.create_table(
        "order_items",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("order_id", pg.UUID(as_uuid=True), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("animal_id", pg.UUID(as_uuid=True), sa.ForeignKey("animals.id"), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])
    op.create_index("ix_order_items_animal_id", "order_items", ["animal_id"])

    op.create_table(
        "order_status_events",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("order_id", pg.UUID(as_uuid=True), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("from_status", sa.String(32), nullable=True),
        sa.Column("to_status", sa.String(32), nullable=False),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("changed_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_order_status_events_order_id", "order_status_events", ["order_id"])
    op.execute("""
        CREATE TRIGGER order_status_events_append_only
        BEFORE UPDATE OR DELETE ON order_status_events
        FOR EACH ROW EXECUTE FUNCTION reject_audit_log_mutation();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS order_status_events_append_only ON order_status_events;")
    op.drop_table("order_status_events")
    op.drop_table("order_items")
    op.drop_table("orders")
    op.execute("DROP INDEX IF EXISTS uq_reservations_active_animal;")
    op.drop_table("reservations")
    op.execute("DROP INDEX IF EXISTS uq_listings_active_animal;")
    op.drop_table("listings")
    op.drop_table("customers")
