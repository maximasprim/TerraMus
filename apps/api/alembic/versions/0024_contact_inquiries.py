"""Public-site contact form inbox.

Adds `contact_inquiries`: messages visitors send through a farm's public
contact page, triaged by staff (new / read / replied / archived).

Purely additive - no existing table or column is modified.

Revision ID: 0024
Revises: 0023
Create Date: 2026-09-30
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contact_inquiries",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("listing_slug", sa.String(255), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="new"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_contact_inquiries_organization_id", "contact_inquiries", ["organization_id"])
    op.create_index("ix_contact_inquiries_status", "contact_inquiries", ["status"])


def downgrade() -> None:
    op.drop_index("ix_contact_inquiries_status", table_name="contact_inquiries")
    op.drop_index("ix_contact_inquiries_organization_id", table_name="contact_inquiries")
    op.drop_table("contact_inquiries")
