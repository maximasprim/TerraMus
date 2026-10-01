"""Listing photo management (multiple photos per listing).

Storage (see storage.py): with STORAGE_BACKEND=database the processed bytes
live in Postgres (`data`/`thumb_data`); with STORAGE_BACKEND=supabase they are
uploaded to a Supabase Storage bucket and only their object keys are stored
here, so browsers load them straight from the CDN. Rows of both kinds can
coexist, so switching backends never orphans existing photos. Only
lightweight metadata columns are selected for listing/admin views - the blobs
are `deferred` on the model and read solely by the media endpoint.

Ordering: `position` 0 is the cover photo (the only one shown on the home
page / store grid); the product page shows all of them in position order.
"""
import asyncio
import logging
import uuid
from typing import NamedTuple

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.commerce import schemas, storage
from app.modules.commerce.images import (
    InvalidImageError,
    MAX_IMAGES_PER_LISTING,
    MAX_UPLOAD_BYTES,
    process_image,
)
from app.modules.commerce.models import Listing, ListingImage

logger = logging.getLogger("app.images")

_META = (
    ListingImage.id, ListingImage.position, ListingImage.width, ListingImage.height,
    ListingImage.size_bytes, ListingImage.content_type, ListingImage.storage_key, ListingImage.thumb_key,
)


class ImageRef(NamedTuple):
    """What the public API needs per photo: its id plus direct CDN URLs when
    the photo lives in the bucket (both None for database-stored photos)."""
    id: uuid.UUID
    url: str | None
    thumb_url: str | None


class ImageSource(NamedTuple):
    """Where to get a photo's bytes: inline (`data`) or via a redirect."""
    data: bytes | None
    content_type: str
    redirect_url: str | None


def _urls(cfg: storage.StorageConfig, storage_key: str | None, thumb_key: str | None) -> tuple[str | None, str | None]:
    if storage_key and cfg.configured:
        return (
            storage.public_url(cfg, storage_key),
            storage.public_url(cfg, thumb_key) if thumb_key else None,
        )
    return None, None


def _out(row, cfg: storage.StorageConfig) -> schemas.ListingImageOut:
    url, thumb_url = _urls(cfg, row.storage_key, row.thumb_key)
    return schemas.ListingImageOut(
        id=row.id, position=row.position, width=row.width, height=row.height,
        size_bytes=row.size_bytes, content_type=row.content_type, url=url, thumb_url=thumb_url,
    )


async def _lock_listing(db: AsyncSession, org_id: uuid.UUID, listing_id: uuid.UUID) -> Listing:
    """Row-lock the listing so concurrent uploads/deletes/reorders on the same
    listing serialize (same pattern as the animal-row locking in commerce)."""
    result = await db.execute(
        select(Listing).where(Listing.id == listing_id, Listing.organization_id == org_id).with_for_update()
    )
    listing = result.scalar_one_or_none()
    if not listing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Listing not found")
    return listing


async def list_images(db: AsyncSession, org_id: uuid.UUID, listing_id: uuid.UUID) -> list[schemas.ListingImageOut]:
    exists = await db.execute(select(Listing.id).where(Listing.id == listing_id, Listing.organization_id == org_id))
    if exists.first() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Listing not found")
    rows = await db.execute(
        select(*_META)
        .where(ListingImage.listing_id == listing_id, ListingImage.organization_id == org_id)
        .order_by(ListingImage.position, ListingImage.created_at)
    )
    cfg = storage.config_from_settings()
    return [_out(r, cfg) for r in rows.all()]


async def _read_upload(file: UploadFile) -> bytes:
    raw = await file.read(MAX_UPLOAD_BYTES + 1)  # never buffer more than the cap (+1 to detect overflow)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"{file.filename or 'File'}: image is too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB per photo)",
        )
    return raw


def _storage_http_error(exc: storage.StorageError) -> HTTPException:
    if isinstance(exc, storage.StorageNotConfigured):
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Photo storage is not configured")
    return HTTPException(status.HTTP_502_BAD_GATEWAY, "Photo storage is unavailable - please try again")


async def add_images(
    db: AsyncSession, org_id: uuid.UUID, listing_id: uuid.UUID, uploads: list[UploadFile],
) -> list[schemas.ListingImageOut]:
    """All-or-nothing: every file is validated and re-encoded BEFORE anything
    is stored, so a single bad file rejects the whole request and leaves the
    listing's photos untouched. If anything fails after objects were uploaded
    to the bucket, those objects are deleted again (no orphans)."""
    if not uploads:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No files were uploaded")
    if len(uploads) > MAX_IMAGES_PER_LISTING:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"A listing can have at most {MAX_IMAGES_PER_LISTING} photos",
        )

    # Cheap tenant/existence check first (no lock), so a wrong id 404s before
    # we spend CPU on decoding.
    owned = await db.execute(select(Listing.id).where(Listing.id == listing_id, Listing.organization_id == org_id))
    if owned.first() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Listing not found")

    # Do the slow parts (decode + re-encode, bucket uploads) BEFORE locking the
    # listing row. The row lock is also taken implicitly by anything that
    # updates the listing (e.g. a guest order deactivating it), so holding it
    # across seconds of processing/network I/O could stall checkout for that product.
    processed = []
    for upload in uploads:
        raw = await _read_upload(upload)
        try:
            # Pillow decode/encode is CPU-bound - keep it off the event loop.
            processed.append(await asyncio.to_thread(process_image, raw))
        except InvalidImageError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{upload.filename or 'File'}: {exc}")

    cfg = storage.config_from_settings()
    uploaded_keys: list[str] = []
    try:
        specs: list[tuple[uuid.UUID, str | None, str | None, object]] = []
        for item in processed:
            image_id = uuid.uuid4()
            key = thumb_key = None
            if cfg.use_bucket:
                key, thumb_key = storage.object_keys(org_id, listing_id, image_id)
                try:
                    await storage.upload_object(cfg, key, item.data, item.content_type)
                    uploaded_keys.append(key)
                    await storage.upload_object(cfg, thumb_key, item.thumb, item.content_type)
                    uploaded_keys.append(thumb_key)
                except storage.StorageError as exc:
                    raise _storage_http_error(exc)
            specs.append((image_id, key, thumb_key, item))

        # Lock only for the short count-check + insert, serialising concurrent uploads.
        await _lock_listing(db, org_id, listing_id)
        existing = (await db.execute(
            select(func.count()).select_from(ListingImage).where(ListingImage.listing_id == listing_id)
        )).scalar_one()
        if existing + len(specs) > MAX_IMAGES_PER_LISTING:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"A listing can have at most {MAX_IMAGES_PER_LISTING} photos ({existing} already uploaded)",
            )
        last_position = (await db.execute(
            select(func.coalesce(func.max(ListingImage.position), -1)).where(ListingImage.listing_id == listing_id)
        )).scalar_one()

        created: list[ListingImage] = []
        for offset, (image_id, key, thumb_key, item) in enumerate(specs, start=1):
            image = ListingImage(
                id=image_id, organization_id=org_id, listing_id=listing_id, position=last_position + offset,
                content_type=item.content_type, width=item.width, height=item.height, size_bytes=len(item.data),
                # bytes live in the DB only when there's no bucket key
                data=None if key else item.data, thumb_data=None if key else item.thumb,
                storage_key=key, thumb_key=thumb_key,
            )
            db.add(image)
            created.append(image)
        await db.commit()
    except Exception:
        await storage.delete_objects(cfg, uploaded_keys)  # don't leave orphaned objects behind
        raise
    return [_out(i, cfg) for i in created]


async def delete_image(db: AsyncSession, org_id: uuid.UUID, listing_id: uuid.UUID, image_id: uuid.UUID) -> None:
    await _lock_listing(db, org_id, listing_id)
    result = await db.execute(
        select(ListingImage).where(ListingImage.listing_id == listing_id, ListingImage.organization_id == org_id)
        .order_by(ListingImage.position, ListingImage.created_at)
    )
    images = list(result.scalars().all())  # blobs are deferred - metadata only
    target = next((i for i in images if i.id == image_id), None)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Photo not found")
    keys = [k for k in (target.storage_key, target.thumb_key) if k]
    await db.delete(target)
    for new_position, image in enumerate((i for i in images if i.id != image_id)):
        image.position = new_position  # close the gap so 0 is always the cover
    await db.commit()
    # After the DB change: a leftover object is harmless, a failed delete request must not undo the delete.
    await storage.delete_objects(storage.config_from_settings(), keys)


async def reorder_images(
    db: AsyncSession, org_id: uuid.UUID, listing_id: uuid.UUID, image_ids: list[uuid.UUID],
) -> list[schemas.ListingImageOut]:
    """`image_ids` must be exactly the listing's current photos, in the new
    order; the first becomes the cover."""
    await _lock_listing(db, org_id, listing_id)
    result = await db.execute(
        select(ListingImage).where(ListingImage.listing_id == listing_id, ListingImage.organization_id == org_id)
    )
    by_id = {i.id: i for i in result.scalars().all()}
    if len(set(image_ids)) != len(image_ids) or set(image_ids) != set(by_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "image_ids must list every photo on this listing exactly once")
    for position, image_id in enumerate(image_ids):
        by_id[image_id].position = position
    await db.commit()
    return await list_images(db, org_id, listing_id)


async def get_image_source(db: AsyncSession, image_id: uuid.UUID, thumb: bool) -> ImageSource:
    """Database-stored photos are returned inline; bucket-stored photos as a
    redirect to their public CDN URL."""
    data_col = ListingImage.thumb_data if thumb else ListingImage.data
    key_col = ListingImage.thumb_key if thumb else ListingImage.storage_key
    row = (await db.execute(select(data_col, ListingImage.content_type, key_col).where(ListingImage.id == image_id))).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Photo not found")
    data, content_type, key = row
    if data is not None:
        return ImageSource(data=bytes(data), content_type=content_type, redirect_url=None)
    cfg = storage.config_from_settings()
    if key and cfg.configured:
        return ImageSource(data=None, content_type=content_type, redirect_url=storage.public_url(cfg, key))
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Photo not found")


async def image_refs_by_listing(db: AsyncSession, listing_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[ImageRef]]:
    """One query for a whole page of listings (no N+1). Refs come back in
    display order, cover first."""
    if not listing_ids:
        return {}
    rows = await db.execute(
        select(ListingImage.listing_id, ListingImage.id, ListingImage.storage_key, ListingImage.thumb_key)
        .where(ListingImage.listing_id.in_(listing_ids))
        .order_by(ListingImage.position, ListingImage.created_at)
    )
    cfg = storage.config_from_settings()
    grouped: dict[uuid.UUID, list[ImageRef]] = {}
    for listing_id, image_id, key, thumb_key in rows.all():
        url, thumb_url = _urls(cfg, key, thumb_key)
        grouped.setdefault(listing_id, []).append(ImageRef(image_id, url, thumb_url))
    return grouped


async def attach_cover_info(db: AsyncSession, listings: list[Listing]) -> None:
    """Annotates ORM listing objects (transient attributes, not columns) with
    `cover_image_id` / `cover_thumb_url` / `image_count`, which ListingOut
    exposes for the admin grid. Purely additive - other endpoints returning
    ListingOut simply get the schema defaults (None / None / 0)."""
    grouped = await image_refs_by_listing(db, [listing.id for listing in listings])
    for listing in listings:
        refs = grouped.get(listing.id, [])
        listing.cover_image_id = refs[0].id if refs else None
        listing.cover_thumb_url = refs[0].thumb_url if refs else None
        listing.image_count = len(refs)
