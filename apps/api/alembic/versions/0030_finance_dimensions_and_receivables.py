"""Finance sub-farm/activity dimensions, extended categories, customer receivables ledger.

Additive only: two nullable columns on finance_transactions (existing rows and callers
are untouched), a wider category list, and a new account_entries table for credit sales.

Revision ID: 0030
Revises: 0029
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects import postgresql as pg

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None

OLD_CATS = ("'livestock_sale','milk_sale','other_revenue','livestock_acquisition','feed','veterinary','labour',"
            "'transport','utilities','maintenance','equipment','marketing','payment_processing_fee','other_expense'")
NEW_ONLY = ["crop_sale", "fodder_sale", "poultry_sale", "egg_sale", "fish_sale", "rabbit_sale", "training_revenue",
            "seed", "fertilizer", "chemicals", "fuel", "lease", "insurance"]
NEW_CATS = OLD_CATS + "," + ",".join(f"'{c}'" for c in NEW_ONLY)


def upgrade() -> None:
    op.add_column("finance_transactions", sa.Column("farm_id", pg.UUID(as_uuid=True), sa.ForeignKey("farms.id"), nullable=True))
    op.add_column("finance_transactions", sa.Column("activity", sa.String(24), nullable=True))
    op.create_index("ix_finance_transactions_farm_id", "finance_transactions", ["farm_id"])
    op.create_index("ix_finance_transactions_activity", "finance_transactions", ["activity"])
    op.drop_constraint("valid_category", "finance_transactions", type_="check")
    op.create_check_constraint("valid_category", "finance_transactions", f"category in ({NEW_CATS})")

    op.create_table(
        "account_entries",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", pg.UUID(as_uuid=True), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("entry_type", sa.String(12), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("entry_date", sa.Date, nullable=False),
        sa.Column("reference_type", sa.String(32), nullable=True),
        sa.Column("reference_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("method", sa.String(16), nullable=True),
        sa.Column("receipt_ref", sa.String(64), nullable=True),
        sa.Column("farm_id", pg.UUID(as_uuid=True), sa.ForeignKey("farms.id"), nullable=True),
        sa.Column("activity", sa.String(24), nullable=True),
        sa.Column("salesperson", sa.String(120), nullable=True),
        sa.Column("created_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("entry_type in ('charge','payment','writeoff')", name="valid_entry_type"),
        sa.CheckConstraint("amount > 0", name="positive_amount"),
    )
    op.create_index("ix_account_entries_organization_id", "account_entries", ["organization_id"])
    op.create_index("ix_account_entries_customer_id", "account_entries", ["customer_id"])
    op.create_index("ix_account_entries_entry_date", "account_entries", ["entry_date"])
    op.create_index("ix_account_entries_reference", "account_entries", ["reference_type", "reference_id"])


def downgrade() -> None:
    op.drop_table("account_entries")
    # The ledger is append-only (a trigger blocks UPDATE/DELETE), so rows that use the new
    # categories cannot be rewritten. Refuse rather than leave the ledger inconsistent.
    n = op.get_bind().execute(text("SELECT count(*) FROM finance_transactions WHERE category = ANY(:c)"), {"c": NEW_ONLY}).scalar()
    if n:
        raise RuntimeError(f"Cannot downgrade: {n} ledger row(s) use categories added in 0030 and the ledger is append-only.")
    op.drop_constraint("valid_category", "finance_transactions", type_="check")
    op.create_check_constraint("valid_category", "finance_transactions", f"category in ({OLD_CATS})")
    op.drop_index("ix_finance_transactions_activity", "finance_transactions")
    op.drop_index("ix_finance_transactions_farm_id", "finance_transactions")
    op.drop_column("finance_transactions", "activity")
    op.drop_column("finance_transactions", "farm_id")
