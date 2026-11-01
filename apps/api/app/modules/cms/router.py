import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.identity.deps import require_permission
from app.modules.identity.models import User
from app.modules.cms import schemas, service, site_images

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


@router.delete("/banners/{banner_id}", status_code=204)
async def delete_banner(
    banner_id: uuid.UUID,
    user: User = Depends(require_permission("cms.manage")),
    db: AsyncSession = Depends(get_db),
):
    await service.delete_banner(db, user.organization_id, banner_id)
    return Response(status_code=204)


@router.post("/images", response_model=schemas.SiteImageOut, status_code=201)
async def upload_site_image(
    kind: str = Query("banner", pattern="^(logo|banner)$"),
    file: UploadFile = File(...),
    user: User = Depends(require_permission("cms.manage")),
    db: AsyncSession = Depends(get_db),
):
    """Upload a logo or banner image from the device; put the resulting URL in the profile's `logo_url` or a
    banner's `image_url`. (See the frontend's ImageUploadField.)"""
    return await site_images.upload_site_image(db, user.organization_id, kind, file)


# Public, unauthenticated image bytes keyed only by the image's unguessable UUID - the same arrangement (and the
# same prefix) as commerce's listing photos, so a plain <img> works on the public storefront.
media_router = APIRouter(prefix="/api/v1/media", tags=["media"])


@media_router.get("/site-images/{image_id}")
async def site_image(image_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    source = await site_images.get_image_source(db, image_id)
    if source.redirect_url:
        return RedirectResponse(source.redirect_url, status_code=302, headers={"Cache-Control": "public, max-age=86400"})
    return Response(content=source.data, media_type=source.content_type,
                    headers={"Cache-Control": "public, max-age=31536000, immutable"})
