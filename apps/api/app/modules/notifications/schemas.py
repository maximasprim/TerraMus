import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    category: str
    title: str
    body: str
    related_entity_type: str | None
    related_entity_id: uuid.UUID | None
    is_read: bool
    created_at: datetime


class PreferenceUpdate(BaseModel):
    category: str
    enabled: bool


class ScheduledChecksResult(BaseModel):
    vaccinations_due_notified: int
    low_stock_notified: int
    reservations_expired: int


class EmailOutboxOut(BaseModel):
    """Spec §13/§55 email channel - a staff-visible send log, mainly for
    answering 'did the customer actually get an email' during support/
    debugging. Deliberately excludes body_text from the list view (an
    admin checking delivery status doesn't need to re-read every email's
    full content in a table row) - full content is available via the
    detail lookup if genuinely needed."""
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    to_email: str
    subject: str
    provider: str
    accepted: bool
    sent_at: datetime
