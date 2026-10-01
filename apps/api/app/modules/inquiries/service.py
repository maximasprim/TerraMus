import logging
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.inquiries import schemas
from app.modules.inquiries.models import ContactInquiry, INQUIRY_STATUSES
from app.modules.notifications.service import notify_users_with_permission

logger = logging.getLogger("app.inquiries")

# Same permission that gates order/customer handling - people who deal with
# buyers deal with enquiries. Reusing it avoids a new permission + role backfill.
INQUIRY_PERMISSION = "orders.manage"

# notifications.category is constrained by a DB CHECK (migration 0008) to a
# fixed set; "orders" is the right existing bucket for customer enquiries and
# avoids a schema change.
NOTIFICATION_CATEGORY = "orders"


async def create_inquiry(db: AsyncSession, org_id: uuid.UUID, req: schemas.InquiryCreate) -> ContactInquiry | None:
    if req.website:
        return None  # honeypot tripped - caller still answers 201 so bots learn nothing

    inquiry = ContactInquiry(
        organization_id=org_id, name=req.name, email=req.email,
        phone=(req.phone or None), message=req.message, listing_slug=(req.listing_slug or None),
    )
    db.add(inquiry)
    await db.commit()
    await db.refresh(inquiry)

    try:
        await notify_users_with_permission(
            db, org_id, INQUIRY_PERMISSION, NOTIFICATION_CATEGORY,
            f"New enquiry from {inquiry.name}"[:120], inquiry.message[:200],
            related_entity_type="inquiry", related_entity_id=inquiry.id,
        )
    except Exception:  # a notification hiccup must never lose the customer's message
        await db.rollback()
        logger.exception("failed to notify staff of inquiry %s", inquiry.id)
    return inquiry


async def list_inquiries(
    db: AsyncSession, org_id: uuid.UUID, status_filter: str | None, limit: int, offset: int,
) -> list[ContactInquiry]:
    query = select(ContactInquiry).where(ContactInquiry.organization_id == org_id)
    if status_filter:
        query = query.where(ContactInquiry.status == status_filter)
    result = await db.execute(query.order_by(ContactInquiry.created_at.desc()).limit(limit).offset(offset))
    return list(result.scalars().all())


async def summary(db: AsyncSession, org_id: uuid.UUID) -> schemas.InquirySummary:
    rows = await db.execute(
        select(ContactInquiry.status, func.count()).where(ContactInquiry.organization_id == org_id)
        .group_by(ContactInquiry.status)
    )
    counts = {s: 0 for s in INQUIRY_STATUSES}
    counts.update({s: c for s, c in rows.all() if s in counts})
    return schemas.InquirySummary(**counts)


async def update_status(db: AsyncSession, org_id: uuid.UUID, inquiry_id: uuid.UUID, new_status: str) -> ContactInquiry:
    result = await db.execute(
        select(ContactInquiry).where(ContactInquiry.id == inquiry_id, ContactInquiry.organization_id == org_id)
    )
    inquiry = result.scalar_one_or_none()
    if not inquiry:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Enquiry not found")
    inquiry.status = new_status
    await db.commit()
    await db.refresh(inquiry)
    return inquiry
