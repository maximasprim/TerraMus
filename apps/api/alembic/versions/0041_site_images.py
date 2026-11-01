"""Logo / banner images uploaded from the device.

Adds `site_images`. The farm profile's `logo_url` and a banner's `image_url` keep working exactly as before
(they are still plain URL columns); an uploaded image just gets a public URL that is stored in them.

Purely additive - no existing table or column is modified.

Revision ID: 0041
Revises: 0040
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "site_images",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("content_type", sa.String(32), nullable=False, server_default="image/jpeg"),
        sa.Column("width", sa.Integer, nullable=False),
        sa.Column("height", sa.Integer, nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("data", sa.LargeBinary, nullable=True),
        sa.Column("storage_key", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind in ('logo','banner')", name="ck_site_images_kind"),
        sa.CheckConstraint("data is not null or storage_key is not null", name="ck_site_images_has_bytes"),
    )
    op.create_index("ix_site_images_organization_id", "site_images", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_site_images_organization_id", table_name="site_images")
    op.drop_table("site_images")
