"""Optional bucket storage (Supabase) for listing photos.

Photo bytes may now live in an object-storage bucket instead of Postgres:
adds `storage_key` / `thumb_key` (the bucket object paths) and makes the two
blob columns nullable. Existing rows are untouched and keep being served from
the database, so switching STORAGE_BACKEND never orphans existing photos - the
two kinds simply coexist.

A CHECK guarantees every row has its bytes somewhere (blob OR bucket key).

Downgrade note: rows whose bytes live only in the bucket (data IS NULL) cannot
be represented by the older NOT NULL schema, so they are removed; the bucket
objects themselves are not touched and can be re-imported if needed.

Revision ID: 0025
Revises: 0024
Create Date: 2026-09-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("listing_images", sa.Column("storage_key", sa.String(255), nullable=True))
    op.add_column("listing_images", sa.Column("thumb_key", sa.String(255), nullable=True))
    op.alter_column("listing_images", "data", existing_type=sa.LargeBinary(), nullable=True)
    op.alter_column("listing_images", "thumb_data", existing_type=sa.LargeBinary(), nullable=True)
    op.create_check_constraint("has_bytes_or_key", "listing_images", "data IS NOT NULL OR storage_key IS NOT NULL")


def downgrade() -> None:
    op.drop_constraint("has_bytes_or_key", "listing_images", type_="check")
    op.execute("DELETE FROM listing_images WHERE data IS NULL")
    op.alter_column("listing_images", "thumb_data", existing_type=sa.LargeBinary(), nullable=False)
    op.alter_column("listing_images", "data", existing_type=sa.LargeBinary(), nullable=False)
    op.drop_column("listing_images", "thumb_key")
    op.drop_column("listing_images", "storage_key")
