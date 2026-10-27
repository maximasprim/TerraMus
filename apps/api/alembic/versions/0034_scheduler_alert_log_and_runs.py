"""Scheduler support: alert de-duplication log and a once-per-day run claim.

Revision ID: 0034
Revises: 0033
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alert_log",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("alert_key", sa.String(200), nullable=False),
        sa.Column("last_sent_on", sa.Date, nullable=False),
        sa.Column("times_sent", sa.Integer, nullable=False, server_default="1"),
        sa.UniqueConstraint("organization_id", "alert_key"),
    )
    op.create_index("ix_alert_log_organization_id", "alert_log", ["organization_id"])
    op.create_table(
        "scheduler_runs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("job", sa.String(60), nullable=False),
        sa.Column("run_date", sa.Date, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(12), nullable=False, server_default="running"),
        sa.Column("summary", pg.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.UniqueConstraint("job", "run_date"),
        sa.CheckConstraint("status in ('running','ok','partial','failed')", name="valid_status"),
    )


def downgrade() -> None:
    op.drop_table("scheduler_runs")
    op.drop_table("alert_log")
