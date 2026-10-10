"""Subscription tiers can cap crop plantings.

Plans capped animals and users but not crops, so a Free-tier farm could create
unlimited crop plantings. Adds `max_crop_plantings` (NULL = unlimited, like the
other limits). Tiers are seeded by code and never updated afterwards
(billing.service.ensure_default_tiers only inserts missing slugs), so this
migration also sets the cap on EXISTING tier rows, mirroring each tier's animal
cap - same scale, unlimited where animals are unlimited. Tune per plan in the
subscription_tiers table whenever you like.

The cap only blocks CREATING more plantings; nothing existing is removed.

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("subscription_tiers", sa.Column("max_crop_plantings", sa.Integer, nullable=True))
    op.execute("UPDATE subscription_tiers SET max_crop_plantings = max_animals WHERE max_animals IS NOT NULL")


def downgrade() -> None:
    op.drop_column("subscription_tiers", "max_crop_plantings")
