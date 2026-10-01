import uuid

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UUIDPKMixin, TimestampMixin

INQUIRY_STATUSES = ("new", "read", "replied", "archived")


class ContactInquiry(Base, UUIDPKMixin, TimestampMixin):
    """A message a visitor sent through the public site's contact form.
    Deliberately stores only what the visitor typed (no IP/user-agent) - the
    farm needs a way to reply, not a tracking record."""
    __tablename__ = "contact_inquiries"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    listing_slug: Mapped[str | None] = mapped_column(String(255), nullable=True)  # set when asked from a product page
    status: Mapped[str] = mapped_column(String(16), default="new", index=True)
