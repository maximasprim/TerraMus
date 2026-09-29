"""Phase 5: payments, payment_webhook_events, finance_transactions, invoices

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-10

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payments",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", pg.UUID(as_uuid=True), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("provider_reference", sa.String(128), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="KES"),
        sa.Column("status", sa.String(16), nullable=False, server_default="initiated"),
        sa.Column("initiated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payment_metadata", pg.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("provider in ('mock','mpesa','stripe')", name="valid_provider"),
        sa.CheckConstraint(
            "status in ('initiated','pending','successful','failed','cancelled','refunded','partially_refunded')",
            name="valid_payment_status",
        ),
    )
    op.create_index("ix_payments_organization_id", "payments", ["organization_id"])
    op.create_index("ix_payments_order_id", "payments", ["order_id"])
    op.create_index("ix_payments_provider", "payments", ["provider"])
    op.create_index("ix_payments_provider_reference", "payments", ["provider_reference"])

    op.create_table(
        "payment_webhook_events",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("payment_id", pg.UUID(as_uuid=True), sa.ForeignKey("payments.id"), nullable=True),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("event_id", sa.String(255), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("raw_payload", pg.JSONB, nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        # The actual idempotency guarantee (spec §20: "never process the same callback twice").
        sa.UniqueConstraint("provider", "event_id", name="uq_payment_webhook_events_provider_event_id"),
    )
    op.create_index("ix_payment_webhook_events_payment_id", "payment_webhook_events", ["payment_id"])
    op.execute("""
        CREATE TRIGGER payment_webhook_events_append_only
        BEFORE UPDATE OR DELETE ON payment_webhook_events
        FOR EACH ROW EXECUTE FUNCTION reject_audit_log_mutation();
    """)

    op.create_table(
        "finance_transactions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("transaction_type", sa.String(16), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="KES"),
        sa.Column("reference_type", sa.String(32), nullable=True),
        sa.Column("reference_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("transaction_date", sa.Date, nullable=False),
        sa.Column("created_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("transaction_type in ('income','expense')", name="valid_transaction_type"),
        sa.CheckConstraint(
            "category in ('livestock_sale','milk_sale','other_revenue','livestock_acquisition','feed',"
            "'veterinary','labour','transport','utilities','maintenance','equipment','marketing',"
            "'payment_processing_fee','other_expense')",
            name="valid_category",
        ),
    )
    op.create_index("ix_finance_transactions_organization_id", "finance_transactions", ["organization_id"])
    op.create_index("ix_finance_transactions_transaction_type", "finance_transactions", ["transaction_type"])
    op.create_index("ix_finance_transactions_category", "finance_transactions", ["category"])
    op.create_index("ix_finance_transactions_transaction_date", "finance_transactions", ["transaction_date"])
    op.execute("""
        CREATE TRIGGER finance_transactions_append_only
        BEFORE UPDATE OR DELETE ON finance_transactions
        FOR EACH ROW EXECUTE FUNCTION reject_audit_log_mutation();
    """)

    op.create_table(
        "invoices",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_number", sa.String(32), nullable=False),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False),
        sa.Column("tax_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("total", sa.Numeric(12, 2), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("order_id", name="uq_invoices_order_id"),  # one invoice per order
        sa.UniqueConstraint("organization_id", "invoice_number", name="uq_invoices_org_invoice_number"),
    )
    op.create_index("ix_invoices_organization_id", "invoices", ["organization_id"])

    op.create_table(
        "invoice_counters",
        sa.Column("organization_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("next_number", sa.Integer, nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_table("invoice_counters")
    op.drop_table("invoices")
    op.execute("DROP TRIGGER IF EXISTS finance_transactions_append_only ON finance_transactions;")
    op.drop_table("finance_transactions")
    op.execute("DROP TRIGGER IF EXISTS payment_webhook_events_append_only ON payment_webhook_events;")
    op.drop_table("payment_webhook_events")
    op.drop_table("payments")
