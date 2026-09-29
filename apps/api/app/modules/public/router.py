import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.public import schemas, service
from app.modules.commerce import schemas as commerce_schemas
from app.modules.payments import schemas as payment_schemas

# No auth dependency anywhere in this router - spec §69: "Do not force
# registration before browsing." Every response here goes through the
# narrow public schemas in public/schemas.py; nothing here ever touches an
# internal *Out schema (AnimalOut, ListingOut, etc.) directly.
router = APIRouter(prefix="/api/v1/public/{org_slug}", tags=["public"])

# Separate router (no {org_slug} in its prefix — there IS no slug yet at
# this point, that's the whole reason this endpoint exists) for the
# frontend's Next.js middleware (apps/web/src/middleware.ts) to call on
# every request to a hostname that isn't the app's own — turning "what
# domain is this" into "which org's /shop/{slug} to actually serve".
# Registered separately in main.py alongside `router`.
domain_router = APIRouter(prefix="/api/v1/public", tags=["public"])


@domain_router.get("/resolve-domain", response_model=schemas.ResolveDomainOut | None)
async def resolve_domain(host: str = Query(...), db: AsyncSession = Depends(get_db)):
    """Returns the org slug for a VERIFIED custom domain, or null if the
    host isn't a recognized/verified tenant domain — the middleware falls
    back to normal routing (404, or the marketing site) in that case rather
    than silently trusting an unverified or unknown Host header."""
    from app.modules.identity.service import get_organization_by_verified_domain

    # Strip a port if present (e.g. local dev hitting "farm.example.com:3000")
    # and normalize case — DNS/HTTP hosts are case-insensitive.
    host = host.split(":")[0].lower()
    org = await get_organization_by_verified_domain(db, host)
    if not org:
        return None
    return schemas.ResolveDomainOut(slug=org.slug)


@router.get("/profile", response_model=schemas.PublicFarmProfileOut)
async def public_profile(org_slug: str, db: AsyncSession = Depends(get_db)):
    org = await service.get_org_by_slug(db, org_slug)
    return await service.get_public_profile(db, org.id)


@router.get("/listings", response_model=list[schemas.PublicListingOut])
async def public_listings(
    org_slug: str, species: str | None = Query(None), crop_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    org = await service.get_org_by_slug(db, org_slug)
    return await service.list_public_listings(db, org.id, species, crop_type)


@router.get("/listings/{slug}", response_model=schemas.PublicListingOut)
async def public_listing_detail(org_slug: str, slug: str, db: AsyncSession = Depends(get_db)):
    org = await service.get_org_by_slug(db, org_slug)
    return await service.get_public_listing_by_slug(db, org.id, slug)


@router.get("/animals/{animal_id}/qr-profile", response_model=schemas.AnimalQRProfileOut)
async def public_animal_qr_profile(org_slug: str, animal_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Spec §38 - where a scanned animal QR code resolves to. No auth
    required (same as every other endpoint in this router); the response
    shape is the narrow allowlist AnimalQRProfileOut, not the full staff
    AnimalOut."""
    org = await service.get_org_by_slug(db, org_slug)
    return await service.get_animal_qr_profile(db, org.id, animal_id)


@router.get("/testimonials", response_model=list[schemas.PublicTestimonialOut])
async def public_testimonials(org_slug: str, db: AsyncSession = Depends(get_db)):
    org = await service.get_org_by_slug(db, org_slug)
    return await service.list_public_testimonials(db, org.id)


@router.get("/blog", response_model=list[schemas.PublicBlogPostSummary])
async def public_blog_list(org_slug: str, db: AsyncSession = Depends(get_db)):
    org = await service.get_org_by_slug(db, org_slug)
    return await service.list_public_blog_posts(db, org.id)


@router.get("/blog/{slug}", response_model=schemas.PublicBlogPostDetail)
async def public_blog_detail(org_slug: str, slug: str, db: AsyncSession = Depends(get_db)):
    org = await service.get_org_by_slug(db, org_slug)
    return await service.get_public_blog_post(db, org.id, slug)


@router.get("/faqs", response_model=list[schemas.PublicFAQOut])
async def public_faqs(org_slug: str, db: AsyncSession = Depends(get_db)):
    org = await service.get_org_by_slug(db, org_slug)
    return await service.list_public_faqs(db, org.id)


@router.get("/banners", response_model=list[schemas.PublicBannerOut])
async def public_banners(org_slug: str, db: AsyncSession = Depends(get_db)):
    org = await service.get_org_by_slug(db, org_slug)
    return await service.list_public_banners(db, org.id)


@router.post("/orders", response_model=schemas.PublicOrderConfirmation, status_code=201)
async def public_create_order(org_slug: str, req: schemas.PublicOrderCreate, db: AsyncSession = Depends(get_db)):
    """Guest checkout (spec §69) - no login required. Reuses the same
    concurrency-safe row-locking order-creation logic staff use
    (commerce/service.py create_order), just entered from a different door."""
    org = await service.get_org_by_slug(db, org_slug)
    return await service.create_guest_order(db, org.id, req)


@router.get("/orders/{order_id}", response_model=commerce_schemas.OrderOut)
async def public_get_order(org_slug: str, order_id: uuid.UUID, email: str = Query(...), db: AsyncSession = Depends(get_db)):
    """Order status lookup for a guest - requires the checkout email as a
    lightweight ownership check (see service.get_guest_order docstring)."""
    org = await service.get_org_by_slug(db, org_slug)
    return await service.get_guest_order(db, org.id, order_id, email)


@router.post("/orders/{order_id}/pay/{provider}", response_model=payment_schemas.PaymentOut, status_code=201)
async def public_initiate_payment(
    org_slug: str, order_id: uuid.UUID, provider: str,
    req: schemas.PublicPaymentRequest, db: AsyncSession = Depends(get_db),
):
    org = await service.get_org_by_slug(db, org_slug)
    return await service.initiate_guest_payment(db, org.id, order_id, provider, req)


@router.get("/sitemap.xml")
async def sitemap(org_slug: str, db: AsyncSession = Depends(get_db)):
    """Spec §45. A real deployment serves this from the Next.js frontend
    (which owns the actual page URLs); this backend version is the data
    source that frontend's sitemap generator would call, and is directly
    useful as-is for any deployment that doesn't have that frontend yet."""
    org = await service.get_org_by_slug(db, org_slug)
    listings = await service.list_public_listings(db, org.id)
    posts = await service.list_public_blog_posts(db, org.id)

    base = f"/public/{org_slug}"
    urls = [base, f"{base}/about", f"{base}/livestock", f"{base}/blog", f"{base}/faqs", f"{base}/contact"]
    urls += [f"{base}/listings/{l.slug}" for l in listings]
    urls += [f"{base}/blog/{p.slug}" for p in posts]

    xml_entries = "".join(f"<url><loc>{u}</loc></url>" for u in urls)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{xml_entries}</urlset>'
    return Response(content=xml, media_type="application/xml")


@router.get("/robots.txt")
async def robots(org_slug: str, db: AsyncSession = Depends(get_db)):
    await service.get_org_by_slug(db, org_slug)  # 404s cleanly if the org doesn't exist
    content = f"User-agent: *\nAllow: /\nSitemap: /api/v1/public/{org_slug}/sitemap.xml\n"
    return Response(content=content, media_type="text/plain")
