"""Phase 7: cms (farm_profiles, testimonials, blog_posts, faqs, banners), listing slug

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-13

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("slug", sa.String(255), nullable=False, server_default=""))
    op.create_index("ix_listings_slug", "listings", ["slug"])
    op.alter_column("listings", "slug", server_default=None)

    op.create_table(
        "farm_profiles",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("farm_name", sa.String(255), nullable=False),
        sa.Column("tagline", sa.String(255), nullable=True),
        sa.Column("farm_story", sa.Text, nullable=True),
        sa.Column("logo_url", sa.String(500), nullable=True),
        sa.Column("address", sa.String(255), nullable=True),
        sa.Column("county", sa.String(128), nullable=True),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("website", sa.String(255), nullable=True),
        sa.Column("established_year", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", name="uq_farm_profiles_organization_id"),
    )

    op.create_table(
        "testimonials",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_name", sa.String(255), nullable=False),
        sa.Column("quote", sa.Text, nullable=False),
        sa.Column("rating", sa.Integer, nullable=True),
        sa.Column("is_published", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("is_featured", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("rating is null or (rating >= 1 and rating <= 5)", name="valid_rating"),
    )
    op.create_index("ix_testimonials_organization_id", "testimonials", ["organization_id"])
    op.create_index("ix_testimonials_is_published", "testimonials", ["is_published"])

    op.create_table(
        "blog_posts",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("excerpt", sa.String(500), nullable=True),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("cover_image_url", sa.String(500), nullable=True),
        sa.Column("author_name", sa.String(255), nullable=True),
        sa.Column("is_published", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("seo_title", sa.String(255), nullable=True),
        sa.Column("seo_description", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_blog_posts_organization_id", "blog_posts", ["organization_id"])
    op.create_index("ix_blog_posts_slug", "blog_posts", ["slug"])
    op.create_index("ix_blog_posts_is_published", "blog_posts", ["is_published"])
    op.create_unique_constraint("uq_blog_posts_org_slug", "blog_posts", ["organization_id", "slug"])

    op.create_table(
        "faqs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("question", sa.String(500), nullable=False),
        sa.Column("answer", sa.Text, nullable=False),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_published", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_faqs_organization_id", "faqs", ["organization_id"])
    op.create_index("ix_faqs_is_published", "faqs", ["is_published"])

    op.create_table(
        "banners",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("image_url", sa.String(500), nullable=False),
        sa.Column("link_url", sa.String(500), nullable=True),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("starts_at", sa.Date, nullable=True),
        sa.Column("ends_at", sa.Date, nullable=True),
    )
    op.create_index("ix_banners_organization_id", "banners", ["organization_id"])
    op.create_index("ix_banners_is_active", "banners", ["is_active"])


def downgrade() -> None:
    op.drop_table("banners")
    op.drop_table("faqs")
    op.drop_table("blog_posts")
    op.drop_table("testimonials")
    op.drop_table("farm_profiles")
    op.drop_index("ix_listings_slug", table_name="listings")
    op.drop_column("listings", "slug")
