"""Feedlot core: intake/sale batches, batch links, exits, weigh sessions, costing docs.

Purely additive: new tables + new permission codes (seeded into the catalog and
granted to existing system roles). Nothing existing is altered.

Revision ID: 0029
Revises: 0028
"""
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects import postgresql as pg

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None

NEW_PERMISSIONS = [
    ("feedlot.read", "View feedlot batches, performance, costing and profitability"),
    ("feedlot.weigh", "Record weigh days (bulk weights)"),
    ("feedlot.manage", "Manage feedlot batches, costing documents and worksheet import/export"),
]
GRANTS = {
    "Farm Owner": [c for c, _ in NEW_PERMISSIONS],
    "Farm Manager": ["feedlot.read", "feedlot.weigh", "feedlot.manage"],
    "Livestock Manager": ["feedlot.read", "feedlot.weigh", "feedlot.manage"],
    "Veterinarian": ["feedlot.read"],
    "Farm Worker": ["feedlot.read", "feedlot.weigh"],
    "Accountant": ["feedlot.read"],
    "Sales Manager": ["feedlot.read"],
}


_STATUS_OLD = ("'active','for_sale','reserved','sold','transferred','deceased','missing','quarantined','archived'")
_STATUS_NEW = _STATUS_OLD + ",'culled'"


def _ts():
    return [sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False)]


def upgrade() -> None:
    op.create_table(
        "intake_batches",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("farm_id", pg.UUID(as_uuid=True), sa.ForeignKey("farms.id"), nullable=True),
        sa.Column("batch_number", sa.Integer, nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("delivered_on", sa.Date, nullable=False),
        sa.Column("source", sa.String(120), nullable=True),
        sa.Column("sex_class", sa.String(16), nullable=False, server_default="bull"),
        sa.Column("head_purchased", sa.Integer, nullable=False, server_default="0"),
        sa.Column("purchase_cost", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("transport_cost", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("other_fees", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("handlers_cost", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text, nullable=True),
        *_ts(),
        sa.UniqueConstraint("organization_id", "batch_number"),
        sa.CheckConstraint("sex_class in ('bull','steer','heifer','mixed')", name="valid_sex_class"),
    )
    op.create_index("ix_intake_batches_organization_id", "intake_batches", ["organization_id"])

    op.create_table(
        "sale_batches",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_number", sa.Integer, nullable=False),
        sa.Column("sold_on", sa.Date, nullable=False),
        sa.Column("price_per_kg", sa.Numeric(10, 2), nullable=True),
        sa.Column("buyer_name", sa.String(160), nullable=True),
        sa.Column("customer_id", pg.UUID(as_uuid=True), sa.ForeignKey("customers.id"), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        *_ts(),
        sa.UniqueConstraint("organization_id", "batch_number"),
    )
    op.create_index("ix_sale_batches_organization_id", "sale_batches", ["organization_id"])

    op.create_table(
        "feedlot_animals",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("animal_id", pg.UUID(as_uuid=True), sa.ForeignKey("animals.id"), nullable=False, unique=True),
        sa.Column("intake_batch_id", pg.UUID(as_uuid=True), sa.ForeignKey("intake_batches.id"), nullable=False),
        sa.Column("received_on", sa.Date, nullable=False),
        sa.Column("entry_weight_kg", sa.Numeric(8, 2), nullable=True),
        sa.Column("legacy_tag", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_feedlot_animals_organization_id", "feedlot_animals", ["organization_id"])
    op.create_index("ix_feedlot_animals_intake_batch_id", "feedlot_animals", ["intake_batch_id"])

    op.create_table(
        "feedlot_exits",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("animal_id", pg.UUID(as_uuid=True), sa.ForeignKey("animals.id"), nullable=False, unique=True),
        sa.Column("exit_type", sa.String(16), nullable=False),
        sa.Column("exit_date", sa.Date, nullable=False),
        sa.Column("sale_batch_id", pg.UUID(as_uuid=True), sa.ForeignKey("sale_batches.id"), nullable=True),
        sa.Column("exit_weight_kg", sa.Numeric(8, 2), nullable=True),
        sa.Column("price_per_kg", sa.Numeric(10, 2), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("customer_id", pg.UUID(as_uuid=True), sa.ForeignKey("customers.id"), nullable=True),
        sa.Column("salesperson", sa.String(120), nullable=True),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("created_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("exit_type in ('sold','culled','died')", name="valid_exit_type"),
    )
    op.create_index("ix_feedlot_exits_organization_id", "feedlot_exits", ["organization_id"])
    op.create_index("ix_feedlot_exits_sale_batch_id", "feedlot_exits", ["sale_batch_id"])

    op.create_table(
        "weigh_sessions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("farm_id", pg.UUID(as_uuid=True), sa.ForeignKey("farms.id"), nullable=True),
        sa.Column("weighed_on", sa.Date, nullable=False),
        sa.Column("scale_label", sa.String(80), nullable=True),
        sa.Column("notes", sa.String(255), nullable=True),
        sa.Column("head_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_weigh_sessions_organization_id", "weigh_sessions", ["organization_id"])
    op.create_index("ix_weigh_sessions_weighed_on", "weigh_sessions", ["weighed_on"])

    op.create_table(
        "costing_documents",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("data", pg.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        *_ts(),
        sa.UniqueConstraint("organization_id", "kind", "name"),
        sa.CheckConstraint("kind in ('settings','recipe','enterprise_budget','ration_plan','overhead_pool','land_use')",
                           name="valid_kind"),
    )
    op.create_index("ix_costing_documents_organization_id", "costing_documents", ["organization_id"])

    # "culled" = removed from the herd as unfit, with no sale revenue (terminal, like 'deceased').
    op.drop_constraint("valid_status", "animals", type_="check")
    op.create_check_constraint("valid_status", "animals", f"status in ({_STATUS_NEW})")

    _seed_permissions()


def _seed_permissions() -> None:
    bind = op.get_bind()
    existing = {r[0] for r in bind.execute(text("SELECT code FROM permissions")).fetchall()}
    for code, desc in NEW_PERMISSIONS:
        if code not in existing:
            bind.execute(text("INSERT INTO permissions (id, code, description) VALUES (:i, :c, :d)"),
                         {"i": str(uuid.uuid4()), "c": code, "d": desc})
    pid = {c: str(i) for i, c in bind.execute(text("SELECT id, code FROM permissions")).fetchall()}
    roles = bind.execute(text("SELECT id, name FROM roles WHERE is_system = true")).fetchall()
    for role_id, name in roles:
        for code in GRANTS.get(name, []):
            bind.execute(text("INSERT INTO role_permissions (role_id, permission_id) VALUES (:r, :p) "
                              "ON CONFLICT (role_id, permission_id) DO NOTHING"), {"r": str(role_id), "p": pid[code]})


def downgrade() -> None:
    bind = op.get_bind()
    codes = [c for c, _ in NEW_PERMISSIONS]
    bind.execute(text("DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code = ANY(:c))"), {"c": codes})
    bind.execute(text("DELETE FROM permissions WHERE code = ANY(:c)"), {"c": codes})
    # rows already 'culled' would violate the old definition
    op.execute("UPDATE animals SET status = 'archived' WHERE status = 'culled'")
    op.drop_constraint("valid_status", "animals", type_="check")
    op.create_check_constraint("valid_status", "animals", f"status in ({_STATUS_OLD})")
    for t in ("costing_documents", "weigh_sessions", "feedlot_exits", "feedlot_animals", "sale_batches", "intake_batches"):
        op.drop_table(t)
