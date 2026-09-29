import uuid
from datetime import date, datetime

from sqlalchemy import String, Text, Integer, Boolean, Date, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UUIDPKMixin, TimestampMixin


class FarmProfile(Base, UUIDPKMixin, TimestampMixin):
    """Spec §15/§33 - the public-facing profile, deliberately separate from
    `Organization` (Phase 1). `Organization` holds internal tenant settings
    (currency, timezone, slug used for auth/API routing); `FarmProfile` holds
    what a visitor to the public site actually sees. Keeping them apart means
    a marketing copy edit can never accidentally touch billing/tenant config."""
    __tablename__ = "farm_profiles"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True, index=True)
    farm_name: Mapped[str] = mapped_column(String(255))
    tagline: Mapped[str | None] = mapped_column(String(255), nullable=True)
    farm_story: Mapped[str | None] = mapped_column(Text, nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    county: Mapped[str | None] = mapped_column(String(128), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    established_year: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Testimonial(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "testimonials"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    customer_name: Mapped[str] = mapped_column(String(255))
    quote: Mapped[str] = mapped_column(Text)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-5
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class BlogPost(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "blog_posts"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    slug: Mapped[str] = mapped_column(String(255), index=True)
    title: Mapped[str] = mapped_column(String(255))
    excerpt: Mapped[str | None] = mapped_column(String(500), nullable=True)
    body: Mapped[str] = mapped_column(Text)
    cover_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    author_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    seo_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    seo_description: Mapped[str | None] = mapped_column(String(500), nullable=True)


class FAQ(Base, UUIDPKMixin):
    __tablename__ = "faqs"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    question: Mapped[str] = mapped_column(String(500))
    answer: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class Banner(Base, UUIDPKMixin):
    __tablename__ = "banners"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    title: Mapped[str] = mapped_column(String(255))
    image_url: Mapped[str] = mapped_column(String(500))
    link_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    starts_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    ends_at: Mapped[date | None] = mapped_column(Date, nullable=True)
