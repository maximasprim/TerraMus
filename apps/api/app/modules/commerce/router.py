import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.identity.deps import require_permission
from app.modules.identity.models import User
from app.modules.commerce import image_service, schemas, service

listings_router = APIRouter(prefix="/api/v1/listings", tags=["commerce"])
reservations_router = APIRouter(prefix="/api/v1/reservations", tags=["commerce"])
orders_router = APIRouter(prefix="/api/v1/orders", tags=["commerce"])


@listings_router.get("", response_model=list[schemas.ListingOut])
async def list_listings(
    species: str | None = Query(None),
    crop_type: str | None = Query(None),
    min_price: Decimal | None = Query(None),
    max_price: Decimal | None = Query(None),
    featured_only: bool = Query(False),
    user: User = Depends(require_permission("livestock.read")),
    db: AsyncSession = Depends(get_db),
):
    filters = schemas.ListingFilter(
        species=species, crop_type=crop_type, min_price=min_price, max_price=max_price, featured_only=featured_only,
    )
    listings = await service.list_listings(db, user.organization_id, filters)
    await image_service.attach_cover_info(db, listings)
    return listings


@listings_router.post("", response_model=schemas.ListingOut, status_code=201)
async def create_listing(
    req: schemas.ListingCreate,
    user: User = Depends(require_permission("listings.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.create_listing(db, user.organization_id, req)


@listings_router.get("/low-stock")
async def low_stock_crop_listings(
    user: User = Depends(require_permission("livestock.read")),
    db: AsyncSession = Depends(get_db),
):
    """Crop-produce listings that have a low_stock_threshold set and have
    fallen at or below it - the listings-side equivalent of inventory's
    low-stock endpoint. Registered before /{listing_id} so "low-stock" is
    never mistaken for a listing id."""
    return await service.list_low_stock_crop_listings(db, user.organization_id)


@listings_router.get("/{listing_id}", response_model=schemas.ListingOut)
async def get_listing(
    listing_id: uuid.UUID,
    user: User = Depends(require_permission("livestock.read")),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_listing(db, user.organization_id, listing_id)


@listings_router.patch("/{listing_id}", response_model=schemas.ListingOut)
async def update_listing(
    listing_id: uuid.UUID,
    req: schemas.ListingUpdate,
    user: User = Depends(require_permission("listings.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.update_listing(db, user.organization_id, listing_id, req)


@listings_router.post("/{listing_id}/deactivate", response_model=schemas.ListingOut)
async def deactivate_listing(
    listing_id: uuid.UUID,
    user: User = Depends(require_permission("listings.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.deactivate_listing(db, user.organization_id, listing_id)


@reservations_router.post("", response_model=schemas.ReservationOut, status_code=201)
async def create_reservation(
    req: schemas.ReservationCreate,
    user: User = Depends(require_permission("orders.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.create_reservation(db, user.organization_id, user.id, req)


@reservations_router.get("", response_model=list[schemas.ReservationOut])
async def list_reservations(
    status: str | None = None,
    user: User = Depends(require_permission("orders.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_reservations(db, user.organization_id, status)


@reservations_router.get("/{reservation_id}", response_model=schemas.ReservationOut)
async def get_reservation(
    reservation_id: uuid.UUID,
    user: User = Depends(require_permission("orders.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_reservation(db, user.organization_id, reservation_id)


@reservations_router.post("/{reservation_id}/cancel", response_model=schemas.ReservationOut)
async def cancel_reservation(
    reservation_id: uuid.UUID,
    user: User = Depends(require_permission("orders.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.cancel_reservation(db, user.organization_id, reservation_id, user.id)


@reservations_router.post("/expire-stale")
async def expire_stale_reservations(
    user: User = Depends(require_permission("orders.manage")),
    db: AsyncSession = Depends(get_db),
):
    expired = await service.expire_stale_reservations(db, user.organization_id)
    return {"expired_count": len(expired), "reservation_ids": [str(i) for i in expired]}


@orders_router.post("", response_model=schemas.OrderOut, status_code=201)
async def create_order(
    req: schemas.OrderCreate,
    user: User = Depends(require_permission("orders.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.create_order(db, user.organization_id, user.id, req)


@orders_router.get("", response_model=list[schemas.OrderOut])
async def list_orders(
    customer_id: uuid.UUID | None = Query(None),
    user: User = Depends(require_permission("orders.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_orders(db, user.organization_id, customer_id)


@orders_router.get("/{order_id}", response_model=schemas.OrderOut)
async def get_order(
    order_id: uuid.UUID,
    user: User = Depends(require_permission("orders.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_order(db, user.organization_id, order_id)


@orders_router.post("/{order_id}/status", response_model=schemas.OrderOut)
async def change_order_status(
    order_id: uuid.UUID,
    req: schemas.OrderStatusChange,
    user: User = Depends(require_permission("orders.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await service.change_order_status(db, user.organization_id, order_id, user.id, req)


# ------------------------------------------------------------ Listing photos --

@listings_router.get("/{listing_id}/images", response_model=list[schemas.ListingImageOut])
async def list_listing_images(
    listing_id: uuid.UUID,
    user: User = Depends(require_permission("livestock.read")),
    db: AsyncSession = Depends(get_db),
):
    return await image_service.list_images(db, user.organization_id, listing_id)


@listings_router.post("/{listing_id}/images", response_model=list[schemas.ListingImageOut], status_code=201)
async def upload_listing_images(
    listing_id: uuid.UUID,
    files: list[UploadFile] = File(...),
    user: User = Depends(require_permission("listings.manage")),
    db: AsyncSession = Depends(get_db),
):
    """Upload one or more photos (multipart field name: `files`). JPEG/PNG/WebP,
    up to 5 MB each and 8 per listing; validated and re-encoded server-side."""
    return await image_service.add_images(db, user.organization_id, listing_id, files)


@listings_router.put("/{listing_id}/images/order", response_model=list[schemas.ListingImageOut])
async def reorder_listing_images(
    listing_id: uuid.UUID,
    req: schemas.ListingImageOrder,
    user: User = Depends(require_permission("listings.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await image_service.reorder_images(db, user.organization_id, listing_id, req.image_ids)


@listings_router.delete("/{listing_id}/images/{image_id}", status_code=204)
async def delete_listing_image(
    listing_id: uuid.UUID,
    image_id: uuid.UUID,
    user: User = Depends(require_permission("listings.manage")),
    db: AsyncSession = Depends(get_db),
):
    await image_service.delete_image(db, user.organization_id, listing_id, image_id)
    return Response(status_code=204)


# Public, unauthenticated photo bytes. Deliberately keyed only by the photo's
# unguessable UUID (no org slug) so <img> tags work identically on the public
# storefront and inside the admin app. Photo ids never change content, so
# responses are cacheable forever.
media_router = APIRouter(prefix="/api/v1/media", tags=["media"])
_IMMUTABLE = {"Cache-Control": "public, max-age=31536000, immutable"}


def _media_response(source: "image_service.ImageSource"):
    if source.redirect_url:  # photo lives in the storage bucket - send the browser to its CDN
        return RedirectResponse(source.redirect_url, status_code=302, headers={"Cache-Control": "public, max-age=86400"})
    return Response(content=source.data, media_type=source.content_type, headers=_IMMUTABLE)


@media_router.get("/listing-images/{image_id}")
async def listing_image(image_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return _media_response(await image_service.get_image_source(db, image_id, thumb=False))


@media_router.get("/listing-images/{image_id}/thumb")
async def listing_image_thumb(image_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return _media_response(await image_service.get_image_source(db, image_id, thumb=True))
