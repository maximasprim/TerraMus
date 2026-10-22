"""Animal profile photo: validated, re-encoded and size-capped (one photo per animal)."""
import io
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import LargeBinary, DateTime, ForeignKey, Integer, String, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UUIDPKMixin, get_db
from app.modules.identity.deps import require_permission
from app.modules.identity.models import User
from app.modules.livestock.models import Animal

MAX_UPLOAD = 5 * 1024 * 1024
MAX_EDGE = 900


class AnimalPhoto(Base, UUIDPKMixin):
    __tablename__ = "animal_photos"
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    animal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("animals.id"), unique=True)
    content_type: Mapped[str] = mapped_column(String(40))
    data: Mapped[bytes] = mapped_column(LargeBinary)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


router = APIRouter(prefix="/api/v1/livestock/{animal_id}/photo", tags=["livestock"])


async def _animal(db, org_id, animal_id) -> Animal:
    a = (await db.execute(select(Animal).where(Animal.id == animal_id, Animal.organization_id == org_id))).scalar_one_or_none()
    if not a:
        raise HTTPException(404, "Animal not found")
    return a


@router.put("")
async def upload_photo(animal_id: uuid.UUID, file: UploadFile = File(...), user: User = Depends(require_permission("livestock.update")),
                       db: AsyncSession = Depends(get_db)):
    from PIL import Image, ImageOps, UnidentifiedImageError
    await _animal(db, user.organization_id, animal_id)
    raw = await file.read(MAX_UPLOAD + 1)
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(413, "Photo is larger than 5 MB")
    try:
        img = Image.open(io.BytesIO(raw)); img.verify()
        img = Image.open(io.BytesIO(raw))
        if img.format not in ("JPEG", "PNG", "WEBP"):
            raise HTTPException(422, "Use a JPEG, PNG or WebP photo")
        img = ImageOps.exif_transpose(img).convert("RGB")      # honour phone orientation; drop metadata (GPS etc.)
    except (UnidentifiedImageError, OSError):
        raise HTTPException(422, "That file is not a valid image")
    img.thumbnail((MAX_EDGE, MAX_EDGE))
    buf = io.BytesIO(); img.save(buf, "JPEG", quality=85, optimize=True)
    existing = (await db.execute(select(AnimalPhoto).where(AnimalPhoto.animal_id == animal_id))).scalar_one_or_none()
    if existing:
        existing.data, existing.width, existing.height, existing.content_type = buf.getvalue(), img.width, img.height, "image/jpeg"
    else:
        db.add(AnimalPhoto(organization_id=user.organization_id, animal_id=animal_id, content_type="image/jpeg", data=buf.getvalue(), width=img.width, height=img.height))
    await db.commit()
    return {"width": img.width, "height": img.height, "bytes": len(buf.getvalue())}


@router.get("")
async def get_photo(animal_id: uuid.UUID, user: User = Depends(require_permission("livestock.read")), db: AsyncSession = Depends(get_db)):
    await _animal(db, user.organization_id, animal_id)
    p = (await db.execute(select(AnimalPhoto).where(AnimalPhoto.animal_id == animal_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(404, "This animal has no photo")
    return Response(p.data, media_type=p.content_type, headers={"Cache-Control": "private, max-age=300"})


@router.delete("", status_code=204)
async def delete_photo(animal_id: uuid.UUID, user: User = Depends(require_permission("livestock.update")), db: AsyncSession = Depends(get_db)):
    await _animal(db, user.organization_id, animal_id)
    p = (await db.execute(select(AnimalPhoto).where(AnimalPhoto.animal_id == animal_id))).scalar_one_or_none()
    if p:
        await db.delete(p); await db.commit()
