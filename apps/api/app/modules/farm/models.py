import uuid

from sqlalchemy import String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, UUIDPKMixin, TimestampMixin


class Farm(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "farms"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    county: Mapped[str | None] = mapped_column(String(128), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)

    branches: Mapped[list["Branch"]] = relationship(
        back_populates="farm", cascade="all, delete-orphan", lazy="selectin"
    )


class Branch(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "branches"

    farm_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("farms.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))

    farm: Mapped["Farm"] = relationship(back_populates="branches")
    locations: Mapped[list["Location"]] = relationship(
        back_populates="branch", cascade="all, delete-orphan", lazy="selectin"
    )


class Location(Base, UUIDPKMixin, TimestampMixin):
    """A paddock, barn, pen, grazing area, or quarantine zone (spec §3.3, §10)."""
    __tablename__ = "locations"

    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    location_type: Mapped[str] = mapped_column(String(32))  # paddock|barn|pen|grazing_area|quarantine

    branch: Mapped["Branch"] = relationship(back_populates="locations")
