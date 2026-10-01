import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.middleware import public_contact_limit
from app.modules.identity.deps import require_permission
from app.modules.identity.models import User
from app.modules.inquiries import schemas, service
from app.modules.inquiries.service import INQUIRY_PERMISSION
from app.modules.public.service import get_org_by_slug

# Staff inbox (authenticated, tenant-scoped).
router = APIRouter(prefix="/api/v1/inquiries", tags=["inquiries"])

# Public submission (no auth - spec §69 'do not force registration'). Same URL
# prefix family as the rest of the public API, kept in this module so the
# existing public router is untouched.
public_router = APIRouter(prefix="/api/v1/public/{org_slug}", tags=["public"])


@public_router.post(
    "/contact", response_model=schemas.InquiryReceipt, status_code=201,
    dependencies=[Depends(public_contact_limit)],
)
async def submit_inquiry(org_slug: str, req: schemas.InquiryCreate, db: AsyncSession = Depends(get_db)):
    org = await get_org_by_slug(db, org_slug)
    await service.create_inquiry(db, org.id, req)
    return schemas.InquiryReceipt(received=True)


@router.get("", response_model=list[schemas.InquiryOut])
async def list_inquiries(
    status: str | None = Query(None, pattern="^(new|read|replied|archived)$"),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_permission(INQUIRY_PERMISSION)),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_inquiries(db, user.organization_id, status, limit, offset)


@router.get("/summary", response_model=schemas.InquirySummary)
async def inquiry_summary(
    user: User = Depends(require_permission(INQUIRY_PERMISSION)), db: AsyncSession = Depends(get_db),
):
    return await service.summary(db, user.organization_id)


@router.patch("/{inquiry_id}", response_model=schemas.InquiryOut)
async def update_inquiry_status(
    inquiry_id: uuid.UUID, req: schemas.InquiryStatusUpdate,
    user: User = Depends(require_permission(INQUIRY_PERMISSION)), db: AsyncSession = Depends(get_db),
):
    return await service.update_status(db, user.organization_id, inquiry_id, req.status)
