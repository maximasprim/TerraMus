"""Weights report: target days on farm.

Revision ID: 0049
Revises: 0048

  * intake_batches.target_days  - how many days a batch is planned to stay on the farm before market.
  * animals.target_days         - the same for one animal; it overrides its batch.
Both are nullable: nothing has a target number of days until the owner sets one, so nothing existing changes.
Downgrade drops the two columns.
"""
import sqlalchemy as sa
from alembic import op

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("intake_batches", sa.Column("target_days", sa.Integer(), nullable=True))
    op.add_column("animals", sa.Column("target_days", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("animals", "target_days")
    op.drop_column("intake_batches", "target_days")
