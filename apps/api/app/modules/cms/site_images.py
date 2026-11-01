"""Logo / banner images uploaded from the farm's own device.

The upload is validated and re-encoded with the same pipeline listing photos use (commerce/images.py: real-format
detection, size and pixel caps, EXIF/GPS stripped), stored either in Postgres or in the storage bucket (commerce/
storage.py, same STORAGE_BACKEND switch), and handed back as a public URL. The caller puts that URL in
`FarmProfile.logo_url` / `Banner.image_url` - the existing URL columns - so nothing that reads them changes.
"""
import asyncio
import re
import uuid
from typing import NamedTuple

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cms.models import Banner, FarmProfile, SiteImage
from app.modules.commerce import storage
from app.modules.commerce.images import InvalidImageError, MAX_UPLOAD_BYTES, process_image

KINDS = ("logo", "banner")
MAX_SITE_IMAGES_PER_ORG = 60  # a safety cap: abandoned uploads are small in number, but not unbounded

_URL_ID = re.compile(r"/api/v1/media/site-images/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})")


class ImageSource(NamedTuple):
    data: bytes | None
    content_type: str
    redirect_url: str | None


def _object_key(org_id: uuid.UUID, image_id: uuid.UUID) -> str:
    return f"{org_id}/site/{image_id}.jpg"


def _cdn_url(cfg: storage.StorageConfig, key: str | None) -> str | None:
    return storage.public_url(cfg, key) if key and cfg.configured else None


async def upload_site_image(db: AsyncSession, org_id: uuid.UUID, kind: str, upload: UploadFile) -> dict:
    if kind not in KINDS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "kind must be 'logo' or 'banner'")

    raw = await upload.read(MAX_UPLOAD_BYTES + 1)  # never buffer more than the cap (+1 to detect overflow)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"Image is too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB)",
        )
    try:
        processed = await asyncio.to_thread(process_image, raw)  # CPU-bound: keep it off the event loop
    except InvalidImageError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    count = (await db.execute(
        select(func.count()).select_from(SiteImage).where(SiteImage.organization_id == org_id)
    )).scalar_one()
    if count >= MAX_SITE_IMAGES_PER_ORG:
        raise HTTPException(status.HTTP_409_CONFLICT, "Too many uploaded site images - delete some banners first")

    cfg = storage.config_from_settings()
    image_id = uuid.uuid4()
    key: str | None = None
    if cfg.use_bucket:
        key = _object_key(org_id, image_id)
        try:
            await storage.upload_object(cfg, key, processed.data, processed.content_type)
        except storage.StorageNotConfigured:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Image storage is not configured")
        except storage.StorageError:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Image storage is unavailable - please try again")

    try:
        db.add(SiteImage(
            id=image_id, organization_id=org_id, kind=kind, content_type=processed.content_type,
            width=processed.width, height=processed.height, size_bytes=len(processed.data),
            data=None if key else processed.data, storage_key=key,
        ))
        await db.commit()
    except Exception:
        await storage.delete_objects(cfg, [key] if key else [])  # no orphaned bucket object
        raise
    return {
        "id": image_id, "kind": kind, "width": processed.width, "height": processed.height,
        "size_bytes": len(processed.data), "url": _cdn_url(cfg, key),
    }


async def get_image_source(db: AsyncSession, image_id: uuid.UUID) -> ImageSource:
    row = (await db.execute(
        select(SiteImage.data, SiteImage.content_type, SiteImage.storage_key).where(SiteImage.id == image_id)
    )).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image not found")
    data, content_type, key = row
    if data is not None:
        return ImageSource(bytes(data), content_type, None)
    url = _cdn_url(storage.config_from_settings(), key)
    if url:
        return ImageSource(None, content_type, url)
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Image not found")


def image_id_from_url(url: str | None) -> uuid.UUID | None:
    """The uploaded-image id inside a URL we issued (database-served form), else None - so a pasted external URL,
    or a bucket CDN URL, is simply never treated as ours."""
    match = _URL_ID.search(url or "")
    return uuid.UUID(match.group(1)) if match else None


async def release_if_unused(db: AsyncSession, org_id: uuid.UUID, url: str | None) -> None:
    """After a banner is deleted or a logo replaced: delete the uploaded image the old URL pointed at, but only if
    it belongs to this org and nothing (logo or any banner) still uses it. Best-effort - failure here must never
    undo the change the person actually asked for."""
    image_id = image_id_from_url(url)
    if image_id is None:
        return
    try:
        needle = f"%{image_id}%"
        still_used = (await db.execute(
            select(Banner.id).where(Banner.organization_id == org_id, Banner.image_url.like(needle)).limit(1)
        )).first() or (await db.execute(
            select(FarmProfile.id).where(FarmProfile.organization_id == org_id, FarmProfile.logo_url.like(needle)).limit(1)
        )).first()
        if still_used:
            return
        key = (await db.execute(
            select(SiteImage.storage_key).where(SiteImage.id == image_id, SiteImage.organization_id == org_id)
        )).scalar_one_or_none()
        await db.execute(delete(SiteImage).where(SiteImage.id == image_id, SiteImage.organization_id == org_id))
        await db.commit()
        if key:
            await storage.delete_objects(storage.config_from_settings(), [key])
    except Exception:
        await db.rollback()
