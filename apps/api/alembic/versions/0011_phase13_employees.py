"""Phase 13: employee management (spec §27)

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-05

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "employees",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("employee_number", sa.String(32), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("department", sa.String(128), nullable=True),
        sa.Column("job_title", sa.String(128), nullable=True),
        sa.Column("employment_type", sa.String(32), nullable=False, server_default="full_time"),
        sa.Column("employment_status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("assigned_farm_id", pg.UUID(as_uuid=True), sa.ForeignKey("farms.id"), nullable=True),
        sa.Column("assigned_location_id", pg.UUID(as_uuid=True), sa.ForeignKey("locations.id"), nullable=True),
        sa.Column("hire_date", sa.Date, nullable=True),
        sa.Column("termination_date", sa.Date, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "employment_status in ('active','on_leave','suspended','terminated')",
            name="valid_employment_status",
        ),
        sa.CheckConstraint(
            "employment_type in ('full_time','part_time','casual','contract')",
            name="valid_employment_type",
        ),
    )
    op.create_index("ix_employees_organization_id", "employees", ["organization_id"])
    op.create_index("ix_employees_employee_number", "employees", ["employee_number"])
    op.create_index("ix_employees_employment_status", "employees", ["employment_status"])

    op.create_table(
        "employee_status_events",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("employee_id", pg.UUID(as_uuid=True), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("from_status", sa.String(16), nullable=True),
        sa.Column("to_status", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("changed_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_employee_status_events_employee_id", "employee_status_events", ["employee_id"])
    # Same append-only guarantee reused across every status trail in this
    # codebase (spec §28); trigger function itself defined once in 0002.
    op.execute("""
        CREATE TRIGGER employee_status_events_append_only
        BEFORE UPDATE OR DELETE ON employee_status_events
        FOR EACH ROW EXECUTE FUNCTION reject_audit_log_mutation();
    """)

    op.create_table(
        "work_shifts",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("employee_id", pg.UUID(as_uuid=True), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("shift_date", sa.Date, nullable=False),
        sa.Column("start_time", sa.Time, nullable=True),
        sa.Column("end_time", sa.Time, nullable=True),
        sa.Column("location_id", pg.UUID(as_uuid=True), sa.ForeignKey("locations.id"), nullable=True),
        sa.Column("notes", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_work_shifts_employee_id", "work_shifts", ["employee_id"])
    op.create_index("ix_work_shifts_shift_date", "work_shifts", ["shift_date"])

    op.create_table(
        "employee_counters",
        sa.Column("organization_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("next_number", sa.Integer, nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_table("employee_counters")
    op.drop_table("work_shifts")
    op.execute("DROP TRIGGER IF EXISTS employee_status_events_append_only ON employee_status_events;")
    op.drop_table("employee_status_events")
    op.drop_table("employees")
