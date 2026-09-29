import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.notifications.models import Notification, NotificationPreference, EmailOutbox
from app.modules.notifications.email import get_email_provider
from app.modules.identity.models import User
from app.modules.identity.service import get_users_with_permission


async def send_email(
    db: AsyncSession, to: str, subject: str, body_text: str,
    organization_id: uuid.UUID | None = None, related_user_id: uuid.UUID | None = None,
) -> EmailOutbox:
    """Spec §13/§55 email channel. Always writes an EmailOutbox row - even
    when the provider raises - so a failed send is visible in the ledger
    rather than silently vanishing; the exception still propagates to the
    caller (a background event handler, per notifications/handlers.py's
    fire-and-forget-with-own-session pattern) so it gets logged there too."""
    settings = get_settings()
    provider = get_email_provider(settings.EMAIL_PROVIDER_MODE)
    try:
        result = await provider.send(to, subject, body_text)
        accepted = result.accepted
    except Exception:
        accepted = False
        raise
    finally:
        outbox = EmailOutbox(
            organization_id=organization_id, to_email=to, subject=subject, body_text=body_text,
            provider=settings.EMAIL_PROVIDER_MODE, accepted=accepted, related_user_id=related_user_id,
        )
        db.add(outbox)
        await db.commit()
    return outbox


async def _is_enabled(db: AsyncSession, user_id: uuid.UUID, category: str) -> bool:
    result = await db.execute(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user_id, NotificationPreference.category == category,
        )
    )
    pref = result.scalar_one_or_none()
    return pref.enabled if pref else True  # default: on


async def notify_users_with_permission(
    db: AsyncSession, org_id: uuid.UUID, permission_code: str, category: str,
    title: str, body: str, related_entity_type: str | None = None, related_entity_id: uuid.UUID | None = None,
) -> int:
    """Core fan-out used by notifications/handlers.py: everyone in the org
    with the given permission gets a notification, unless they've opted out
    of this category (spec §55)."""
    users = await get_users_with_permission(db, org_id, permission_code)
    count = 0
    for user in users:
        if not await _is_enabled(db, user.id, category):
            continue
        db.add(Notification(
            organization_id=org_id, user_id=user.id, category=category,
            title=title, body=body,
            related_entity_type=related_entity_type, related_entity_id=related_entity_id,
        ))
        count += 1
    await db.commit()
    return count


async def list_notifications(db: AsyncSession, user: User, unread_only: bool = False) -> list[Notification]:
    query = select(Notification).where(
        Notification.organization_id == user.organization_id, Notification.user_id == user.id,
    )
    if unread_only:
        query = query.where(Notification.is_read.is_(False))
    result = await db.execute(query.order_by(Notification.created_at.desc()))
    return list(result.scalars().all())


async def mark_read(db: AsyncSession, user: User, notification_id: uuid.UUID) -> Notification:
    result = await db.execute(
        select(Notification).where(Notification.id == notification_id, Notification.user_id == user.id)
    )
    notification = result.scalar_one_or_none()
    if not notification:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
    notification.is_read = True
    await db.commit()
    await db.refresh(notification)
    return notification


async def mark_all_read(db: AsyncSession, user: User) -> int:
    result = await db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.is_read.is_(False))
        .values(is_read=True)
    )
    await db.commit()
    return result.rowcount


async def set_preference(db: AsyncSession, user: User, category: str, enabled: bool) -> NotificationPreference:
    result = await db.execute(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user.id, NotificationPreference.category == category,
        )
    )
    pref = result.scalar_one_or_none()
    if pref:
        pref.enabled = enabled
    else:
        pref = NotificationPreference(user_id=user.id, category=category, enabled=enabled)
        db.add(pref)
    await db.commit()
    return pref


async def list_email_outbox(db: AsyncSession, org_id: uuid.UUID) -> list[EmailOutbox]:
    """Staff-visible send log - spec §13/§55 email channel, added this
    session alongside the channel itself. Org-scoped like everything else;
    password-reset emails (which have organization_id set from the
    requesting user's own org) show up here too, not just order/customer
    emails."""
    result = await db.execute(
        select(EmailOutbox).where(EmailOutbox.organization_id == org_id).order_by(EmailOutbox.sent_at.desc()).limit(200)
    )
    return list(result.scalars().all())
