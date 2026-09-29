import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.identity.deps import require_permission
from app.modules.identity.models import User
from app.modules.cms import schemas, service

router = APIRouter(prefix="/api/v1/cms", tags=["cms"])


@router.get("/profile", response_model=schemas.FarmProfileOut)
async def get_profile(
    user: User = Depends(require_permission("cms.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_or_create_profile(db, user.organization_id)


@router.put("/profile", response_model=schemas.FarmProfileOut)
async def update_profile(
    req: schemas.FarmProfileUpdate,
    user: User = Depends(require_permission("cms.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.update_profile(db, user.organization_id, req)


@router.get("/testimonials", response_model=list[schemas.TestimonialOut])
async def list_testimonials(
    user: User = Depends(require_permission("cms.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_testimonials(db, user.organization_id)


@router.post("/testimonials", response_model=schemas.TestimonialOut, status_code=201)
async def create_testimonial(
    req: schemas.TestimonialCreate,
    user: User = Depends(require_permission("cms.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.create_testimonial(db, user.organization_id, req)


@router.delete("/testimonials/{testimonial_id}", status_code=204)
async def delete_testimonial(
    testimonial_id: uuid.UUID,
    user: User = Depends(require_permission("cms.manage")),
    db: AsyncSession = Depends(get_db),
):
    await service.delete_testimonial(db, user.organization_id, testimonial_id)


@router.get("/blog", response_model=list[schemas.BlogPostOut])
async def list_blog_posts(
    user: User = Depends(require_permission("cms.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_blog_posts(db, user.organization_id)


@router.post("/blog", response_model=schemas.BlogPostOut, status_code=201)
async def create_blog_post(
    req: schemas.BlogPostCreate,
    user: User = Depends(require_permission("cms.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.create_blog_post(db, user.organization_id, req)


@router.patch("/blog/{post_id}", response_model=schemas.BlogPostOut)
async def update_blog_post(
    post_id: uuid.UUID,
    req: schemas.BlogPostUpdate,
    user: User = Depends(require_permission("cms.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.update_blog_post(db, user.organization_id, post_id, req)


@router.get("/faqs", response_model=list[schemas.FAQOut])
async def list_faqs(
    user: User = Depends(require_permission("cms.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_faqs(db, user.organization_id)


@router.post("/faqs", response_model=schemas.FAQOut, status_code=201)
async def create_faq(
    req: schemas.FAQCreate,
    user: User = Depends(require_permission("cms.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.create_faq(db, user.organization_id, req)


@router.get("/banners", response_model=list[schemas.BannerOut])
async def list_banners(
    user: User = Depends(require_permission("cms.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_banners(db, user.organization_id)


@router.post("/banners", response_model=schemas.BannerOut, status_code=201)
async def create_banner(
    req: schemas.BannerCreate,
    user: User = Depends(require_permission("cms.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.create_banner(db, user.organization_id, req)
