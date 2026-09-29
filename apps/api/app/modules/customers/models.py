import uuid

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UUIDPKMixin, TimestampMixin

CUSTOMER_TYPES = (
    "individual", "butcher", "hotel", "restaurant", "institution",
    "livestock_trader", "wholesaler", "farm", "corporate",
)


class Customer(Base, UUIDPKMixin, TimestampMixin):
    """Spec §16 (Customer Management/CRM). Not linked to a login directly -
    identity.User.customer_id (added Phase 15) points *at* this table, kept
    as a one-way optional FK from the User side rather than a relationship
    declared here, so this module still doesn't need to import identity."""
    __tablename__ = "customers"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    name: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    customer_type: Mapped[str] = mapped_column(String(32), default="individual", index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
