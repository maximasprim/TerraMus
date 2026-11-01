"""Batch numbers restart in every production cycle.

Intake batches and sale batches were unique per (organization, batch_number), so a second production cycle could
not have its own "Batch 1", "Batch 2" ... This migration replaces that with:

  * unique (organization, cycle, batch_number) for batches that belong to a cycle, and
  * unique (organization, batch_number) for batches that belong to no cycle (exactly the old rule for them).

Purely loosening: every row that satisfied the old rule satisfies the new ones, so nothing can fail on upgrade and
no data is touched. Downgrade refuses if two cycles now share a number (it would violate the old rule).

Revision ID: 0040
Revises: 0039
"""
from alembic import op
from sqlalchemy import text

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None

TABLES = ("intake_batches", "sale_batches")


def upgrade() -> None:
    for t in TABLES:
        op.execute(f"""
            DO $$
            DECLARE c text;
            BEGIN
              FOR c IN
                SELECT con.conname FROM pg_constraint con
                JOIN pg_class rel ON rel.oid = con.conrelid
                WHERE rel.relname = '{t}' AND con.contype = 'u'
                  AND (SELECT array_agg(att.attname::text ORDER BY att.attname)
                       FROM unnest(con.conkey) k JOIN pg_attribute att ON att.attrelid = rel.oid AND att.attnum = k)
                      = ARRAY['batch_number','organization_id']
              LOOP
                EXECUTE format('ALTER TABLE {t} DROP CONSTRAINT %I', c);
              END LOOP;
            END $$;
        """)
        op.execute(f"CREATE UNIQUE INDEX uq_{t}_org_cycle_number ON {t} (organization_id, production_cycle_id, batch_number) "
                   "WHERE production_cycle_id IS NOT NULL;")
        op.execute(f"CREATE UNIQUE INDEX uq_{t}_org_number_unassigned ON {t} (organization_id, batch_number) "
                   "WHERE production_cycle_id IS NULL;")


def downgrade() -> None:
    bind = op.get_bind()
    for t in TABLES:
        dup = bind.execute(text(
            f"SELECT count(*) FROM (SELECT 1 FROM {t} GROUP BY organization_id, batch_number HAVING count(*) > 1) d")).scalar()
        if dup:
            raise RuntimeError(f"Cannot downgrade: {dup} {t} number(s) are used in more than one production cycle. "
                               "Renumber or delete the duplicates first.")
    for t in TABLES:
        op.execute(f"DROP INDEX IF EXISTS uq_{t}_org_cycle_number;")
        op.execute(f"DROP INDEX IF EXISTS uq_{t}_org_number_unassigned;")
        op.create_unique_constraint(f"{t}_organization_id_batch_number_key", t, ["organization_id", "batch_number"])
