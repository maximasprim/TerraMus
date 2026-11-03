"""Let a platform superadmin's permanent organization deletion remove rows from the append-only tables.

Revision ID: 0043
Revises: 0042

14 tables are guarded by BEFORE UPDATE/DELETE triggers (audit_logs, the finance and stock ledgers, animal / crop /
employee / order history, ...), so deleting an organization's data fails on the first guarded table that holds a
row. Those guarantees are deliberate and stay exactly as they are for everything else. This migration adds ONE narrow
exception to the two trigger functions: a DELETE is allowed when the transaction has set the transaction-local flag
`app.org_purge = 'on'` (platform_admin/org_deletion.py does so, only after its suspended + typed name + password
checks). The flag vanishes when that transaction ends. UPDATE is still always rejected, and `audit_logs` can never be
deleted, with or without the flag.

No data changes; downgrade restores the original function bodies.
"""
from alembic import op

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None

REJECT_NEW = """
CREATE OR REPLACE FUNCTION reject_audit_log_mutation()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' AND TG_TABLE_NAME <> 'audit_logs'
       AND coalesce(current_setting('app.org_purge', true), '') = 'on' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'audit_logs is append-only: % not permitted', TG_OP;
END;
$$ LANGUAGE plpgsql;
"""

REJECT_OLD = """
CREATE OR REPLACE FUNCTION reject_audit_log_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'audit_logs is append-only: % not permitted', TG_OP;
END;
$$ LANGUAGE plpgsql;
"""

LEDGER_NEW = """
CREATE OR REPLACE FUNCTION ledger_allow_cycle_tag_only()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' AND coalesce(current_setting('app.org_purge', true), '') = 'on' THEN
        RETURN OLD;
    END IF;
    -- The ONLY permitted change to an append-only ledger row: tag it with a production cycle, once.
    IF TG_OP = 'UPDATE'
       AND OLD.production_cycle_id IS NULL
       AND NEW.production_cycle_id IS NOT NULL
       AND (to_jsonb(NEW) - 'production_cycle_id') = (to_jsonb(OLD) - 'production_cycle_id') THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION '% is append-only: % not permitted', TG_TABLE_NAME, TG_OP;
END;
$$ LANGUAGE plpgsql;
"""

LEDGER_OLD = """
CREATE OR REPLACE FUNCTION ledger_allow_cycle_tag_only()
RETURNS TRIGGER AS $$
BEGIN
    -- The ONLY permitted change to an append-only ledger row: tag it with a production cycle, once.
    IF TG_OP = 'UPDATE'
       AND OLD.production_cycle_id IS NULL
       AND NEW.production_cycle_id IS NOT NULL
       AND (to_jsonb(NEW) - 'production_cycle_id') = (to_jsonb(OLD) - 'production_cycle_id') THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION '% is append-only: % not permitted', TG_TABLE_NAME, TG_OP;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.execute(REJECT_NEW)
    op.execute(LEDGER_NEW)


def downgrade() -> None:
    op.execute(REJECT_OLD)
    op.execute(LEDGER_OLD)