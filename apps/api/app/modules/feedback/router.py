import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.commerce.models import Listing
from app.modules.feedback.models import ProductFeedback
from app.modules.identity.deps import require_permission
from app.modules.identity.models import User
from app.modules.public.service import get_org_by_slug

MAX_PENDING_PER_LISTING = 25      # a flood of submissions cannot bury the moderation queue

public = APIRouter(prefix="/api/v1/public/{org_slug}", tags=["public-feedback"])
staff = APIRouter(prefix="/api/v1/feedback", tags=["feedback"])


class FeedbackSubmit(BaseModel):
    customer_name: str = Field(min_length=2, max_length=120)
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=1000)


class Moderate(BaseModel):
    status: str = Field(pattern="^(approved|rejected)$")


def _row(f: ProductFeedback) -> dict:
    return {"id": str(f.id), "listing_id": str(f.listing_id) if f.listing_id else None, "customer_name": f.customer_name,
            "rating": f.rating, "comment": f.comment, "status": f.status, "created_at": f.created_at.isoformat()}


@public.post("/listings/{listing_slug}/feedback", status_code=201)
async def submit_feedback(org_slug: str, listing_slug: str, req: FeedbackSubmit, db: AsyncSession = Depends(get_db)):
    org = await get_org_by_slug(db, org_slug)
    listing = (await db.execute(select(Listing).where(Listing.organization_id == org.id, Listing.slug == listing_slug))).scalar_one_or_none()
    if not listing:
        raise HTTPException(404, "Listing not found")
    pending = (await db.execute(select(func.count()).select_from(ProductFeedback).where(
        ProductFeedback.listing_id == listing.id, ProductFeedback.status == "pending"))).scalar_one()
    if pending >= MAX_PENDING_PER_LISTING:
        raise HTTPException(429, "Too many reviews are awaiting approval for this item; please try again later")
    db.add(ProductFeedback(organization_id=org.id, listing_id=listing.id, customer_name=req.customer_name.strip(), rating=req.rating,
                           comment=(req.comment or "").strip() or None))
    await db.commit()
    return {"status": "pending", "message": "Thank you! Your review will appear once the farm approves it."}


@public.get("/listings/{listing_slug}/feedback")
async def public_feedback(org_slug: str, listing_slug: str, db: AsyncSession = Depends(get_db)):
    org = await get_org_by_slug(db, org_slug)
    listing = (await db.execute(select(Listing).where(Listing.organization_id == org.id, Listing.slug == listing_slug))).scalar_one_or_none()
    if not listing:
        raise HTTPException(404, "Listing not found")
    rows = (await db.execute(select(ProductFeedback).where(ProductFeedback.listing_id == listing.id, ProductFeedback.status == "approved")
                             .order_by(ProductFeedback.created_at.desc()).limit(50))).scalars().all()
    avg = (sum(r.rating for r in rows) / len(rows)) if rows else None
    return {"count": len(rows), "average_rating": round(avg, 2) if avg else None,
            "reviews": [{"customer_name": r.customer_name, "rating": r.rating, "comment": r.comment, "created_at": r.created_at.isoformat()} for r in rows]}


@staff.get("")
async def list_feedback(status: str | None = Query(None, pattern="^(pending|approved|rejected)$"), listing_id: uuid.UUID | None = Query(None),
                        user: User = Depends(require_permission("cms.manage")), db: AsyncSession = Depends(get_db)):
    q = select(ProductFeedback).where(ProductFeedback.organization_id == user.organization_id)
    if status: q = q.where(ProductFeedback.status == status)
    if listing_id: q = q.where(ProductFeedback.listing_id == listing_id)
    return [_row(f) for f in (await db.execute(q.order_by(ProductFeedback.created_at.desc()).limit(500))).scalars()]


@staff.patch("/{feedback_id}")
async def moderate(feedback_id: uuid.UUID, req: Moderate, user: User = Depends(require_permission("cms.manage")), db: AsyncSession = Depends(get_db)):
    f = (await db.execute(select(ProductFeedback).where(ProductFeedback.id == feedback_id, ProductFeedback.organization_id == user.organization_id))).scalar_one_or_none()
    if not f:
        raise HTTPException(404, "Feedback not found")
    f.status, f.moderated_by, f.moderated_at = req.status, user.id, datetime.now(timezone.utc)
    await db.commit()
    return _row(f)


@staff.get("/summary")
async def feedback_summary(user: User = Depends(require_permission("cms.manage")), db: AsyncSession = Depends(get_db)):
    """Average rating and counts per listing (approved reviews only) plus the moderation backlog."""
    rows = (await db.execute(select(ProductFeedback.listing_id, func.count(), func.avg(ProductFeedback.rating)).where(
        ProductFeedback.organization_id == user.organization_id, ProductFeedback.status == "approved").group_by(ProductFeedback.listing_id))).all()
    pending = (await db.execute(select(func.count()).select_from(ProductFeedback).where(
        ProductFeedback.organization_id == user.organization_id, ProductFeedback.status == "pending"))).scalar_one()
    return {"pending_moderation": pending, "listings": [{"listing_id": str(l) if l else None, "reviews": n, "average_rating": round(float(a), 2)} for l, n, a in rows]}
