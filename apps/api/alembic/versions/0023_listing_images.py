"""Multiple photos per listing.

Adds `listing_images`: one row per photo, holding the processed (re-encoded,
EXIF-stripped) full-size and thumbnail bytes plus display order. `position` 0
is the cover photo shown on the home/store grids; the product page shows all.

Purely additive - no existing table or column is modified.

Revision ID: 0023
Revises: 0022
Create Date: 2026-09-30
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "listing_images",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("listing_id", pg.UUID(as_uuid=True), sa.ForeignKey("listings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("content_type", sa.String(32), nullable=False, server_default="image/jpeg"),
        sa.Column("width", sa.Integer, nullable=False),
        sa.Column("height", sa.Integer, nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("data", sa.LargeBinary, nullable=False),
        sa.Column("thumb_data", sa.LargeBinary, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_listing_images_organization_id", "listing_images", ["organization_id"])
    op.create_index("ix_listing_images_listing_id", "listing_images", ["listing_id"])


def downgrade() -> None:
    op.drop_index("ix_listing_images_listing_id", table_name="listing_images")
    op.drop_index("ix_listing_images_organization_id", table_name="listing_images")
    op.drop_table("listing_images")
