"""Enforce append-only audit_logs at the DB level (spec §28: "Audit logs should
not be editable" / append-only).

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-09

"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

FUNC_SQL = """
CREATE OR REPLACE FUNCTION reject_audit_log_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'audit_logs is append-only: % not permitted', TG_OP;
END;
$$ LANGUAGE plpgsql;
"""

TRIGGER_SQL = """
CREATE TRIGGER audit_logs_append_only
BEFORE UPDATE OR DELETE ON audit_logs
FOR EACH ROW EXECUTE FUNCTION reject_audit_log_mutation();
"""


def upgrade() -> None:
    op.execute(FUNC_SQL)
    op.execute(TRIGGER_SQL)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_logs_append_only ON audit_logs;")
    op.execute("DROP FUNCTION IF EXISTS reject_audit_log_mutation;")
