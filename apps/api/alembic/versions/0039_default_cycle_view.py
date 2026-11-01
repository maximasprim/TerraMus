"""Optional per-farm setting: open the admin console on the running production cycle by default.

Additive. 'all' (the default, and the value every existing organisation gets) means nothing changes: the console
opens on all cycles exactly as before.

Revision ID: 0039
Revises: 0038
"""
import sqlalchemy as sa
from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("default_cycle_view", sa.String(12), nullable=False, server_default="all"))
    op.create_check_constraint("ck_organizations_default_cycle_view", "organizations", "default_cycle_view in ('all','running')")


def downgrade() -> None:
    op.drop_constraint("ck_organizations_default_cycle_view", "organizations", type_="check")
    op.drop_column("organizations", "default_cycle_view")
