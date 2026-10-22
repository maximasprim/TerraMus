import uuid
from datetime import date

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin, UUIDPKMixin

SESSION_STATUSES = ("scheduled", "in_progress", "completed", "cancelled")
ENROLMENT_STATUSES = ("registered", "attended", "completed", "no_show", "cancelled")


class TrainingCourse(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "training_courses"
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(60), nullable=True)
    duration_days: Mapped[int] = mapped_column(Integer, default=1)
    fee: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trainer: Mapped[str | None] = mapped_column(String(160), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class TrainingSession(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "training_sessions"
    __table_args__ = (CheckConstraint("status in ('scheduled','in_progress','completed','cancelled')", name="valid_session_status"),
                      CheckConstraint("end_date >= start_date", name="valid_dates"))
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    course_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("training_courses.id"), index=True)
    farm_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("farms.id"), nullable=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    venue: Mapped[str | None] = mapped_column(String(200), nullable=True)
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fee: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="scheduled")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class TrainingEnrolment(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "training_enrolments"
    __table_args__ = (UniqueConstraint("organization_id", "certificate_number"),
                      CheckConstraint("status in ('registered','attended','completed','no_show','cancelled')", name="valid_enrolment_status"))
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("training_sessions.id"), index=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True)
    participant_name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fee_charged: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    status: Mapped[str] = mapped_column(String(16), default="registered")
    certificate_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    certificate_issued_on: Mapped[date | None] = mapped_column(Date, nullable=True)


class TrainingAttendance(Base, UUIDPKMixin):
    __tablename__ = "training_attendance"
    __table_args__ = (UniqueConstraint("enrolment_id", "day"),)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    enrolment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("training_enrolments.id"))
    day: Mapped[date] = mapped_column(Date)
    present: Mapped[bool] = mapped_column(Boolean)
