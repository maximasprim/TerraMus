"""Phase 2b: health_records

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-09

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "health_records",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("animal_id", pg.UUID(as_uuid=True), sa.ForeignKey("animals.id"), nullable=False),
        sa.Column("record_type", sa.String(32), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("diagnosis", sa.String(255), nullable=True),
        sa.Column("medication", sa.String(255), nullable=True),
        sa.Column("dosage", sa.String(128), nullable=True),
        sa.Column("administered_by", sa.String(255), nullable=True),
        sa.Column("cost", sa.Numeric(12, 2), nullable=True),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("follow_up_date", sa.Date, nullable=True),
        sa.Column("follow_up_completed", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("extra", pg.JSONB, nullable=True),
        sa.Column("recorded_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "record_type in ('vaccination','treatment','deworming','examination','injury','lab_result','vet_visit','prescription')",
            name="valid_record_type",
        ),
    )
    op.create_index("ix_health_records_organization_id", "health_records", ["organization_id"])
    op.create_index("ix_health_records_animal_id", "health_records", ["animal_id"])
    op.create_index("ix_health_records_record_type", "health_records", ["record_type"])
    op.create_index("ix_health_records_follow_up_date", "health_records", ["follow_up_date"])

    # Historical fact table - same append-only principle as animal_events (spec §77).
    # Exception: follow_up_completed needs to flip, so we don't use the blanket
    # reject-all trigger here; instead we rely on the service layer only ever
    # touching that one column via complete_follow_up(). Documented trade-off:
    # full DB-level immutability would also block legitimate follow-up completion.


def downgrade() -> None:
    op.drop_table("health_records")
