"""Crop sales (made outside the web shop) and per-planting costs.

Until now a crop planting recorded only a purchase/acquisition cost and its harvests, so produce sold
off the web (to a trader, a co-operative, at the market) had nowhere to live and profit per planting
could not be worked out. These two tables hold that data. Both are append-only in spirit: a wrong entry
is VOIDED (kept, flagged, with a reason, and reversed in the ledger), never edited or deleted.

`import_key` makes spreadsheet imports idempotent: the same row can never be imported twice.

The finance ledger is append-only, so a duplicate posting can never be undone. The partial unique
indexes below make a duplicate impossible at the database level (see also feedlot migration 0036).
Each index is only created when existing data has no duplicates for that key.

Additive only; nothing existing is modified or deleted.

Revision ID: 0037
Revises: 0036
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None

COST_CATEGORIES = ("seed", "fertilizer", "chemicals", "labour", "fuel", "transport", "equipment",
                   "maintenance", "lease", "insurance", "utilities", "other_expense")


def upgrade() -> None:
    op.create_table(
        "crop_sales",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("planting_id", pg.UUID(as_uuid=True), sa.ForeignKey("crop_plantings.id"), nullable=False),
        sa.Column("sale_date", sa.Date, nullable=False),
        sa.Column("quantity", sa.Numeric(12, 2), nullable=False),
        sa.Column("unit", sa.String(16), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("customer_id", pg.UUID(as_uuid=True), sa.ForeignKey("customers.id"), nullable=True),
        sa.Column("buyer_name", sa.String(128), nullable=True),
        sa.Column("notes", sa.String(255), nullable=True),
        sa.Column("source", sa.String(16), nullable=False, server_default="manual"),
        sa.Column("import_key", sa.String(64), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("void_reason", sa.String(255), nullable=True),
        sa.Column("voided_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity > 0", name="crop_sale_positive_quantity"),
        sa.CheckConstraint("unit_price >= 0 AND amount >= 0", name="crop_sale_non_negative_money"),
        sa.CheckConstraint("source in ('manual','import')", name="crop_sale_valid_source"),
    )
    op.create_index("ix_crop_sales_organization_id", "crop_sales", ["organization_id"])
    op.create_index("ix_crop_sales_planting_id", "crop_sales", ["planting_id"])
    op.create_index("ix_crop_sales_sale_date", "crop_sales", ["sale_date"])
    op.execute("CREATE UNIQUE INDEX uq_crop_sales_import_key ON crop_sales (organization_id, import_key) "
               "WHERE import_key IS NOT NULL")

    op.create_table(
        "crop_costs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("planting_id", pg.UUID(as_uuid=True), sa.ForeignKey("crop_plantings.id"), nullable=False),
        sa.Column("cost_date", sa.Date, nullable=False),
        sa.Column("category", sa.String(24), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("source", sa.String(16), nullable=False, server_default="manual"),
        sa.Column("import_key", sa.String(64), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("void_reason", sa.String(255), nullable=True),
        sa.Column("voided_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount > 0", name="crop_cost_positive_amount"),
        sa.CheckConstraint("category in (" + ",".join(f"'{c}'" for c in COST_CATEGORIES) + ")", name="crop_cost_valid_category"),
        sa.CheckConstraint("source in ('manual','import')", name="crop_cost_valid_source"),
    )
    op.create_index("ix_crop_costs_organization_id", "crop_costs", ["organization_id"])
    op.create_index("ix_crop_costs_planting_id", "crop_costs", ["planting_id"])
    op.create_index("ix_crop_costs_cost_date", "crop_costs", ["cost_date"])
    op.execute("CREATE UNIQUE INDEX uq_crop_costs_import_key ON crop_costs (organization_id, import_key) "
               "WHERE import_key IS NOT NULL")

    # One ledger posting per crop sale / cost / planting purchase (and one reversal per voided sale / cost).
    op.execute("""
        DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM finance_transactions
                         WHERE reference_type IN ('crop_sale','crop_sale_void','crop_cost','crop_cost_void','crop_planting')
                         GROUP BY organization_id, reference_type, reference_id HAVING count(*) > 1) THEN
            CREATE UNIQUE INDEX IF NOT EXISTS uq_fin_tx_crop_refs
              ON finance_transactions (organization_id, reference_type, reference_id)
              WHERE reference_type IN ('crop_sale','crop_sale_void','crop_cost','crop_cost_void','crop_planting');
          END IF;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM account_entries WHERE reference_type = 'crop_sale' AND entry_type = 'charge'
                         GROUP BY organization_id, reference_id HAVING count(*) > 1) THEN
            CREATE UNIQUE INDEX IF NOT EXISTS uq_acct_entry_crop_sale_charge
              ON account_entries (organization_id, reference_id)
              WHERE reference_type = 'crop_sale' AND entry_type = 'charge';
          END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_acct_entry_crop_sale_charge;")
    op.execute("DROP INDEX IF EXISTS uq_fin_tx_crop_refs;")
    op.drop_table("crop_costs")
    op.drop_table("crop_sales")
