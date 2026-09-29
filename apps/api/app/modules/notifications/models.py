import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UUIDPKMixin

# Spec §55 - notification categories map roughly to the permission areas a
# user already has, so "who gets notified" can be derived from RBAC rather
# than a separate subscription list to maintain.
NOTIFICATION_CATEGORIES = (
    "health", "breeding", "inventory", "orders", "payments", "system",
)


class Notification(Base, UUIDPKMixin):
    """In-app notifications (spec §13/§55). Email/SMS/push channels are a
    documented future extension - see notifications/channels.py - not
    implemented here since there's no reachable provider to verify against
    in this sandbox (same honesty stance as the Phase 5 payment providers)."""
    __tablename__ = "notifications"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    category: Mapped[str] = mapped_column(String(16), index=True)
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(String(500))
    related_entity_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    related_entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class NotificationPreference(Base):
    """One row per (user, category) - absence of a row means 'use the
    default' (enabled), matching spec §55's per-category opt-out model
    without needing to pre-populate every user/category pair."""
    __tablename__ = "notification_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    category: Mapped[str] = mapped_column(String(16), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class EmailOutbox(Base, UUIDPKMixin):
    """Durable record of every email attempted, regardless of which
    EmailProvider handled it - same reasoning as Payment being the durable
    record independent of which payment provider processed it (spec §11's
    provider abstraction, applied to the email channel added this session).
    Plain insert-only log, not append-only-triggered: an email send either
    happened or didn't, once - there's no status that transitions and needs
    a protected history the way order/PO/employee status does."""
    __tablename__ = "email_outbox"

    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    to_email: Mapped[str] = mapped_column(String(255), index=True)
    subject: Mapped[str] = mapped_column(String(255))
    body_text: Mapped[str] = mapped_column(String(2000))
    provider: Mapped[str] = mapped_column(String(16))
    accepted: Mapped[bool] = mapped_column(Boolean)
    related_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
