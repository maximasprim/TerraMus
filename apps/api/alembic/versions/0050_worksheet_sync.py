"""Automatic import of the Google Sheet worksheet.

Revision ID: 0050
Revises: 0049

Adds worksheet_syncs: one optional row per organisation holding the sheet link and the result of the last run.
Nothing existing is touched; with no row (or enabled = false) nothing runs. Downgrade drops the table.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "worksheet_syncs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sheet_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("production_cycle_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("post_to_finance", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("include_costing", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("configured_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(16), nullable=True),
        sa.Column("last_message", sa.Text(), nullable=True),
        sa.Column("last_hash", sa.String(64), nullable=True),
        sa.Column("last_report", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_worksheet_syncs_organization_id", "worksheet_syncs", ["organization_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_worksheet_syncs_organization_id", table_name="worksheet_syncs")
    op.drop_table("worksheet_syncs")
