import re
import uuid
from datetime import date, datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cms.models import FarmProfile, Testimonial, BlogPost, FAQ, Banner
from app.modules.cms import schemas


def _slugify(title: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return f"{base}-{uuid.uuid4().hex[:6]}"


# --------------------------------------------------------------- Profile ---

async def get_or_create_profile(db: AsyncSession, org_id: uuid.UUID, default_name: str = "") -> FarmProfile:
    result = await db.execute(select(FarmProfile).where(FarmProfile.organization_id == org_id))
    profile = result.scalar_one_or_none()
    if not profile:
        profile = FarmProfile(organization_id=org_id, farm_name=default_name or "Farm")
        db.add(profile)
        await db.commit()
        await db.refresh(profile)
    return profile


async def update_profile(db: AsyncSession, org_id: uuid.UUID, req: schemas.FarmProfileUpdate) -> FarmProfile:
    profile = await get_or_create_profile(db, org_id)
    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    await db.commit()
    await db.refresh(profile)
    return profile


# ----------------------------------------------------------- Testimonials ---

async def create_testimonial(db: AsyncSession, org_id: uuid.UUID, req: schemas.TestimonialCreate) -> Testimonial:
    testimonial = Testimonial(organization_id=org_id, **req.model_dump())
    db.add(testimonial)
    await db.commit()
    await db.refresh(testimonial)
    return testimonial


async def list_testimonials(db: AsyncSession, org_id: uuid.UUID, published_only: bool = False) -> list[Testimonial]:
    query = select(Testimonial).where(Testimonial.organization_id == org_id)
    if published_only:
        query = query.where(Testimonial.is_published.is_(True))
    result = await db.execute(query.order_by(Testimonial.sort_order, Testimonial.created_at.desc()))
    return list(result.scalars().all())


async def delete_testimonial(db: AsyncSession, org_id: uuid.UUID, testimonial_id: uuid.UUID) -> None:
    result = await db.execute(
        select(Testimonial).where(Testimonial.id == testimonial_id, Testimonial.organization_id == org_id)
    )
    testimonial = result.scalar_one_or_none()
    if not testimonial:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Testimonial not found")
    await db.delete(testimonial)
    await db.commit()


# ------------------------------------------------------------- Blog posts ---

async def create_blog_post(db: AsyncSession, org_id: uuid.UUID, req: schemas.BlogPostCreate) -> BlogPost:
    post = BlogPost(
        organization_id=org_id, slug=_slugify(req.title),
        published_at=datetime.now(timezone.utc) if req.is_published else None,
        **req.model_dump(),
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)
    return post


async def get_blog_post(db: AsyncSession, org_id: uuid.UUID, post_id: uuid.UUID) -> BlogPost:
    result = await db.execute(select(BlogPost).where(BlogPost.id == post_id, BlogPost.organization_id == org_id))
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Blog post not found")
    return post


async def update_blog_post(
    db: AsyncSession, org_id: uuid.UUID, post_id: uuid.UUID, req: schemas.BlogPostUpdate,
) -> BlogPost:
    post = await get_blog_post(db, org_id, post_id)
    changes = req.model_dump(exclude_unset=True)
    was_published = post.is_published
    for field, value in changes.items():
        setattr(post, field, value)
    if not was_published and post.is_published and post.published_at is None:
        post.published_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(post)
    return post


async def list_blog_posts(db: AsyncSession, org_id: uuid.UUID, published_only: bool = False) -> list[BlogPost]:
    query = select(BlogPost).where(BlogPost.organization_id == org_id)
    if published_only:
        query = query.where(BlogPost.is_published.is_(True))
    result = await db.execute(query.order_by(BlogPost.created_at.desc()))
    return list(result.scalars().all())


async def get_published_blog_post_by_slug(db: AsyncSession, org_id: uuid.UUID, slug: str) -> BlogPost:
    result = await db.execute(
        select(BlogPost).where(
            BlogPost.organization_id == org_id, BlogPost.slug == slug, BlogPost.is_published.is_(True),
        )
    )
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Blog post not found")
    return post


# -------------------------------------------------------------------- FAQ ---

async def create_faq(db: AsyncSession, org_id: uuid.UUID, req: schemas.FAQCreate) -> FAQ:
    faq = FAQ(organization_id=org_id, **req.model_dump())
    db.add(faq)
    await db.commit()
    await db.refresh(faq)
    return faq


async def list_faqs(db: AsyncSession, org_id: uuid.UUID, published_only: bool = False) -> list[FAQ]:
    query = select(FAQ).where(FAQ.organization_id == org_id)
    if published_only:
        query = query.where(FAQ.is_published.is_(True))
    result = await db.execute(query.order_by(FAQ.sort_order))
    return list(result.scalars().all())


# --------------------------------------------------------------- Banners ---

async def create_banner(db: AsyncSession, org_id: uuid.UUID, req: schemas.BannerCreate) -> Banner:
    banner = Banner(organization_id=org_id, **req.model_dump())
    db.add(banner)
    await db.commit()
    await db.refresh(banner)
    return banner


async def list_banners(db: AsyncSession, org_id: uuid.UUID, active_only: bool = False) -> list[Banner]:
    query = select(Banner).where(Banner.organization_id == org_id)
    if active_only:
        today = date.today()
        query = query.where(
            Banner.is_active.is_(True),
            (Banner.starts_at.is_(None)) | (Banner.starts_at <= today),
            (Banner.ends_at.is_(None)) | (Banner.ends_at >= today),
        )
    result = await db.execute(query.order_by(Banner.sort_order))
    return list(result.scalars().all())
