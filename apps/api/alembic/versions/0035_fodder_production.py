"""Fodder production: products & market prices, plots, production cycles, costs, harvests, amortised investments,
stock movements, and the fodder.* permissions.

Additive only.

Revision ID: 0035
Revises: 0034
"""
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects import postgresql as pg

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None

NEW_PERMISSIONS = [
    ("fodder.read", "View fodder plots, production, stock, costs and reports"),
    ("fodder.record", "Record fodder harvests, costs, issues, losses and stock counts"),
    ("fodder.manage", "Manage fodder products, prices, plots, cycles, investments, purchases and sales"),
]
GRANTS = {
    "Farm Owner": [c for c, _ in NEW_PERMISSIONS],
    "Farm Manager": [c for c, _ in NEW_PERMISSIONS],
    "Livestock Manager": ["fodder.read", "fodder.record"],
    "Farm Worker": ["fodder.read", "fodder.record"],
    "Veterinarian": ["fodder.read"],
    "Accountant": ["fodder.read"],
    "Sales Manager": ["fodder.read"],
}


def _ts():
    return [sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False)]


def _id():
    return sa.Column("id", pg.UUID(as_uuid=True), primary_key=True)


def _org():
    return sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False)


def upgrade() -> None:
    op.create_table(
        "fodder_products", _id(), _org(), sa.Column("name", sa.String(160), nullable=False),
        sa.Column("category", sa.String(16), nullable=False, server_default="hay"), sa.Column("unit_label", sa.String(16), nullable=False, server_default="bale"),
        sa.Column("kg_per_unit", sa.Numeric(10, 3), nullable=False, server_default="1"), sa.Column("dry_matter_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("reorder_days", sa.Integer, nullable=False, server_default="14"), sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text, nullable=True), *_ts(), sa.UniqueConstraint("organization_id", "name"),
        sa.CheckConstraint("category in ('hay','silage','haylage','straw','green_chop','other')", name="valid_category"),
        sa.CheckConstraint("kg_per_unit > 0", name="positive_unit_weight"))
    op.create_index("ix_fodder_products_organization_id", "fodder_products", ["organization_id"])

    op.create_table(
        "fodder_prices", _id(), _org(),
        sa.Column("product_id", pg.UUID(as_uuid=True), sa.ForeignKey("fodder_products.id"), nullable=False),
        sa.Column("effective_from", sa.Date, nullable=False), sa.Column("price_per_kg", sa.Numeric(10, 4), nullable=False),
        sa.Column("source", sa.String(120), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("product_id", "effective_from"), sa.CheckConstraint("price_per_kg > 0", name="positive_price"))
    op.create_index("ix_fodder_prices_organization_id", "fodder_prices", ["organization_id"])

    op.create_table(
        "fodder_plots", _id(), _org(), sa.Column("farm_id", pg.UUID(as_uuid=True), sa.ForeignKey("farms.id"), nullable=True),
        sa.Column("name", sa.String(120), nullable=False), sa.Column("acres", sa.Numeric(8, 2), nullable=False),
        sa.Column("irrigated", sa.Boolean, nullable=False, server_default=sa.false()), sa.Column("crop", sa.String(80), nullable=True),
        sa.Column("established_on", sa.Date, nullable=True), sa.Column("status", sa.String(12), nullable=False, server_default="active"),
        sa.Column("notes", sa.Text, nullable=True), *_ts(), sa.UniqueConstraint("organization_id", "name"),
        sa.CheckConstraint("acres > 0", name="positive_acres"), sa.CheckConstraint("status in ('active','resting','retired')", name="valid_status"))
    op.create_index("ix_fodder_plots_organization_id", "fodder_plots", ["organization_id"])

    op.create_table(
        "fodder_cycles", _id(), _org(),
        sa.Column("plot_id", pg.UUID(as_uuid=True), sa.ForeignKey("fodder_plots.id"), nullable=False),
        sa.Column("product_id", pg.UUID(as_uuid=True), sa.ForeignKey("fodder_products.id"), nullable=False),
        sa.Column("label", sa.String(120), nullable=False), sa.Column("start_date", sa.Date, nullable=False), sa.Column("end_date", sa.Date, nullable=True),
        sa.Column("acres", sa.Numeric(8, 2), nullable=False), sa.Column("status", sa.String(8), nullable=False, server_default="open"),
        sa.Column("budget_name", sa.String(160), nullable=True), sa.Column("notes", sa.Text, nullable=True), *_ts(),
        sa.CheckConstraint("acres > 0", name="positive_acres"), sa.CheckConstraint("status in ('open','closed')", name="valid_status"),
        sa.CheckConstraint("end_date is null or end_date >= start_date", name="valid_dates"))
    op.create_index("ix_fodder_cycles_organization_id", "fodder_cycles", ["organization_id"])
    op.create_index("ix_fodder_cycles_plot_id", "fodder_cycles", ["plot_id"])

    op.create_table(
        "fodder_costs", _id(), _org(),
        sa.Column("cycle_id", pg.UUID(as_uuid=True), sa.ForeignKey("fodder_cycles.id"), nullable=False),
        sa.Column("cost_date", sa.Date, nullable=False), sa.Column("category", sa.String(16), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False), sa.Column("description", sa.String(255), nullable=True),
        sa.Column("finance_transaction_id", pg.UUID(as_uuid=True), nullable=True), sa.Column("created_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.CheckConstraint("amount > 0", name="positive_amount"),
        sa.CheckConstraint("category in ('seed','fertilizer','chemicals','labour','fuel','machinery_hire','irrigation','transport','packaging','other')", name="valid_category"))
    op.create_index("ix_fodder_costs_organization_id", "fodder_costs", ["organization_id"])
    op.create_index("ix_fodder_costs_cycle_id", "fodder_costs", ["cycle_id"])

    op.create_table(
        "fodder_investments", _id(), _org(), sa.Column("plot_id", pg.UUID(as_uuid=True), sa.ForeignKey("fodder_plots.id"), nullable=True),
        sa.Column("name", sa.String(160), nullable=False), sa.Column("cost", sa.Numeric(12, 2), nullable=False),
        sa.Column("salvage_value", sa.Numeric(12, 2), nullable=False, server_default="0"), sa.Column("in_service_on", sa.Date, nullable=False),
        sa.Column("life_years", sa.Numeric(5, 2), nullable=False), sa.Column("disposed_on", sa.Date, nullable=True), sa.Column("notes", sa.Text, nullable=True), *_ts(),
        sa.CheckConstraint("cost > 0 and salvage_value >= 0 and salvage_value <= cost", name="valid_amounts"), sa.CheckConstraint("life_years > 0", name="positive_life"))
    op.create_index("ix_fodder_investments_organization_id", "fodder_investments", ["organization_id"])

    op.create_table(
        "fodder_harvests", _id(), _org(),
        sa.Column("cycle_id", pg.UUID(as_uuid=True), sa.ForeignKey("fodder_cycles.id"), nullable=False),
        sa.Column("harvest_date", sa.Date, nullable=False), sa.Column("quantity", sa.Numeric(12, 2), nullable=False), sa.Column("kg", sa.Numeric(14, 2), nullable=False),
        sa.Column("quality", sa.String(8), nullable=True), sa.Column("notes", sa.String(255), nullable=True),
        sa.Column("created_by", pg.UUID(as_uuid=True), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity > 0 and kg > 0", name="positive_quantity"), sa.CheckConstraint("quality is null or quality in ('good','fair','poor')", name="valid_quality"))
    op.create_index("ix_fodder_harvests_organization_id", "fodder_harvests", ["organization_id"])
    op.create_index("ix_fodder_harvests_cycle_id", "fodder_harvests", ["cycle_id"])

    op.create_table(
        "fodder_movements", _id(), _org(),
        sa.Column("product_id", pg.UUID(as_uuid=True), sa.ForeignKey("fodder_products.id"), nullable=False),
        sa.Column("movement_date", sa.Date, nullable=False), sa.Column("movement_type", sa.String(12), nullable=False),
        sa.Column("kg_delta", sa.Numeric(14, 2), nullable=False), sa.Column("value", sa.Numeric(12, 2), nullable=True),
        sa.Column("reference_type", sa.String(16), nullable=True), sa.Column("reference_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("destination_type", sa.String(12), nullable=True), sa.Column("destination_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("destination_label", sa.String(120), nullable=True),
        sa.Column("customer_id", pg.UUID(as_uuid=True), sa.ForeignKey("customers.id"), nullable=True), sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("created_by", pg.UUID(as_uuid=True), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("movement_type in ('harvest','purchase','issue','sale','loss','count_adjust')", name="valid_type"),
        sa.CheckConstraint("kg_delta <> 0", name="nonzero_quantity"))
    op.create_index("ix_fodder_movements_organization_id", "fodder_movements", ["organization_id"])
    op.create_index("ix_fodder_movements_product_id", "fodder_movements", ["product_id"])
    op.create_index("ix_fodder_movements_movement_date", "fodder_movements", ["movement_date"])

    _seed_permissions()


def _seed_permissions() -> None:
    bind = op.get_bind()
    existing = {r[0] for r in bind.execute(text("SELECT code FROM permissions")).fetchall()}
    for code, desc in NEW_PERMISSIONS:
        if code not in existing:
            bind.execute(text("INSERT INTO permissions (id, code, description) VALUES (:i, :c, :d)"), {"i": str(uuid.uuid4()), "c": code, "d": desc})
    pid = {c: str(i) for i, c in bind.execute(text("SELECT id, code FROM permissions")).fetchall()}
    for role_id, name in bind.execute(text("SELECT id, name FROM roles WHERE is_system = true")).fetchall():
        for code in GRANTS.get(name, []):
            bind.execute(text("INSERT INTO role_permissions (role_id, permission_id) VALUES (:r, :p) ON CONFLICT (role_id, permission_id) DO NOTHING"), {"r": str(role_id), "p": pid[code]})



def downgrade() -> None:
    bind = op.get_bind()
    codes = [c for c, _ in NEW_PERMISSIONS]
    bind.execute(text("DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code = ANY(:c))"), {"c": codes})
    bind.execute(text("DELETE FROM permissions WHERE code = ANY(:c)"), {"c": codes})
    for t in ("fodder_movements", "fodder_harvests", "fodder_investments", "fodder_costs", "fodder_cycles", "fodder_plots", "fodder_prices", "fodder_products"):
        op.drop_table(t)
