"""Phase 22: configurable organization settings (spec §56/§57/§60)

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-05

"""
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("invoice_prefix", sa.String(16), nullable=False, server_default="INV"))
    op.add_column("organizations", sa.Column("po_prefix", sa.String(16), nullable=False, server_default="PO"))
    op.add_column("organizations", sa.Column("employee_prefix", sa.String(16), nullable=False, server_default="EMP"))
    op.add_column("organizations", sa.Column("asset_prefix", sa.String(16), nullable=False, server_default="AST"))
    op.add_column("organizations", sa.Column("tax_rate", sa.Numeric(5, 2), nullable=False, server_default="0"))
    op.add_column("organizations", sa.Column("default_weight_unit", sa.String(8), nullable=False, server_default="kg"))
    op.add_column("organizations", sa.Column("default_volume_unit", sa.String(8), nullable=False, server_default="L"))


def downgrade() -> None:
    op.drop_column("organizations", "default_volume_unit")
    op.drop_column("organizations", "default_weight_unit")
    op.drop_column("organizations", "tax_rate")
    op.drop_column("organizations", "asset_prefix")
    op.drop_column("organizations", "employee_prefix")
    op.drop_column("organizations", "po_prefix")
    op.drop_column("organizations", "invoice_prefix")
