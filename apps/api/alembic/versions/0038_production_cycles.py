"""Production cycles: one parent object that groups feedlot, finance and operational data.

Purely additive:
  * a new `production_cycles` table;
  * a NULLABLE `production_cycle_id` column on the records that belong to a cycle. Every existing row keeps
    NULL ("not assigned to a cycle"), so nothing existing changes meaning and every existing query keeps
    returning the same rows until a cycle filter is passed;
  * the two append-only ledgers (finance_transactions, stock_movements) get the column too. Their
    append-only trigger is replaced by one that ALSO permits exactly one kind of update: setting the cycle
    tag ONCE on a row that has none, with every other column byte-for-byte unchanged. Amounts, dates,
    categories and references can still never be edited, and a tag can never be changed or cleared;
  * costing documents may be cycle-specific: the old (organization, kind, name) uniqueness becomes
    (organization, kind, name, cycle) so each cycle can have its own "Standard ration" etc.;
  * two new permission codes (cycles.read, cycles.manage), seeded into the catalog and granted to the
    existing organisations' system roles.

Revision ID: 0038
Revises: 0037
"""
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects import postgresql as pg

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None

# table -> index name
PLAIN_TABLES = [
    "intake_batches", "sale_batches", "account_entries", "fuel_logs", "animal_groups", "fodder_cycles",
    "fodder_movements", "crop_plantings", "training_sessions", "costing_documents", "purchase_orders",
]
LEDGER_TABLES = ["finance_transactions", "stock_movements"]

NEW_PERMISSIONS = [
    ("cycles.read", "View production cycles and filter reports by cycle"),
    ("cycles.manage", "Create, edit, close and reopen production cycles; assign records to a cycle"),
]
GRANTS = {
    "Farm Owner": ["cycles.read", "cycles.manage"],
    "Farm Manager": ["cycles.read", "cycles.manage"],
    "Livestock Manager": ["cycles.read"],
    "Accountant": ["cycles.read"],
    "Sales Manager": ["cycles.read"],
    "Veterinarian": ["cycles.read"],
    "Farm Worker": ["cycles.read"],
    "Inventory Manager": ["cycles.read"],
}

LEDGER_TAG_FUNC = """
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
    op.create_table(
        "production_cycles",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("farm_id", pg.UUID(as_uuid=True), sa.ForeignKey("farms.id"), nullable=True),
        sa.Column("cycle_number", sa.Integer, nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("enterprise", sa.String(24), nullable=False, server_default="feedlot"),
        sa.Column("status", sa.String(12), nullable=False, server_default="planned"),
        sa.Column("start_date", sa.Date, nullable=True),
        sa.Column("end_date", sa.Date, nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("close_summary", pg.JSONB, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "cycle_number", name="uq_production_cycles_org_number"),
        sa.UniqueConstraint("organization_id", "name", name="uq_production_cycles_org_name"),
        sa.CheckConstraint("status in ('planned','running','closed')", name="ck_production_cycles_valid_status"),
        sa.CheckConstraint("end_date is null or start_date is null or end_date >= start_date",
                           name="ck_production_cycles_valid_dates"),
    )
    op.create_index("ix_production_cycles_organization_id", "production_cycles", ["organization_id"])

    for table in PLAIN_TABLES + LEDGER_TABLES:
        op.add_column(table, sa.Column("production_cycle_id", pg.UUID(as_uuid=True),
                                       sa.ForeignKey("production_cycles.id"), nullable=True))
        op.create_index(f"ix_{table}_production_cycle_id", table, ["production_cycle_id"])

    # --- ledgers: replace the strict append-only trigger with the "tag once" variant -------------------
    op.execute(LEDGER_TAG_FUNC)
    for table in LEDGER_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table};")
        op.execute(f"""
            CREATE TRIGGER {table}_append_only
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION ledger_allow_cycle_tag_only();
        """)

    # --- costing documents: unique per (org, kind, name, cycle) -----------------------------------------
    op.execute("""
        DO $$
        DECLARE c text;
        BEGIN
          FOR c IN
            SELECT con.conname FROM pg_constraint con
            JOIN pg_class rel ON rel.oid = con.conrelid
            WHERE rel.relname = 'costing_documents' AND con.contype = 'u'
              AND (SELECT array_agg(att.attname::text ORDER BY att.attname)
                   FROM unnest(con.conkey) k JOIN pg_attribute att ON att.attrelid = rel.oid AND att.attnum = k)
                  = ARRAY['kind','name','organization_id']
          LOOP
            EXECUTE format('ALTER TABLE costing_documents DROP CONSTRAINT %I', c);
          END LOOP;
        END $$;
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_costing_documents_org_kind_name_cycle
        ON costing_documents (organization_id, kind, name,
                              COALESCE(production_cycle_id, '00000000-0000-0000-0000-000000000000'::uuid));
    """)

    _seed_permissions()


def _seed_permissions() -> None:
    bind = op.get_bind()
    existing = {r[0] for r in bind.execute(text("SELECT code FROM permissions")).fetchall()}
    for code, desc in NEW_PERMISSIONS:
        if code not in existing:
            bind.execute(text("INSERT INTO permissions (id, code, description) VALUES (:i, :c, :d)"),
                         {"i": str(uuid.uuid4()), "c": code, "d": desc})
    pid = {c: str(i) for i, c in bind.execute(text("SELECT id, code FROM permissions")).fetchall()}
    for role_id, name in bind.execute(text("SELECT id, name FROM roles WHERE is_system = true")).fetchall():
        for code in GRANTS.get(name, []):
            bind.execute(text("INSERT INTO role_permissions (role_id, permission_id) VALUES (:r, :p) "
                              "ON CONFLICT (role_id, permission_id) DO NOTHING"), {"r": str(role_id), "p": pid[code]})


def downgrade() -> None:
    bind = op.get_bind()
    codes = [c for c, _ in NEW_PERMISSIONS]
    bind.execute(text("DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code = ANY(:c))"), {"c": codes})
    bind.execute(text("DELETE FROM permissions WHERE code = ANY(:c)"), {"c": codes})

    # Cycle-specific costing documents would collide with the original (org, kind, name) uniqueness.
    dup = bind.execute(text(
        "SELECT count(*) FROM (SELECT 1 FROM costing_documents GROUP BY organization_id, kind, name HAVING count(*) > 1) d")).scalar()
    if dup:
        raise RuntimeError(f"Cannot downgrade: {dup} costing document name(s) exist once per cycle. "
                           "Delete or rename the cycle-specific copies first.")
    op.execute("DROP INDEX IF EXISTS uq_costing_documents_org_kind_name_cycle;")
    op.create_unique_constraint("costing_documents_organization_id_kind_name_key", "costing_documents",
                                ["organization_id", "kind", "name"])

    for table in LEDGER_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table};")
        op.execute(f"""
            CREATE TRIGGER {table}_append_only
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION reject_audit_log_mutation();
        """)
    op.execute("DROP FUNCTION IF EXISTS ledger_allow_cycle_tag_only();")

    for table in PLAIN_TABLES + LEDGER_TABLES:
        op.drop_index(f"ix_{table}_production_cycle_id", table_name=table)
        op.drop_column(table, "production_cycle_id")
    op.drop_table("production_cycles")
