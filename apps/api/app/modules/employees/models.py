import uuid
from datetime import date, datetime, time

from sqlalchemy import String, Text, Date, DateTime, Time, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, UUIDPKMixin, TimestampMixin

# Spec §27: "employment status" - active while working, on_leave for a
# temporary absence, suspended pending a disciplinary/administrative matter,
# terminated as the only terminal state. Deliberately not modelling payroll/
# attendance/leave-request detail here - spec §27 explicitly lists those as
# "potential future modules" to design *for*, not build now.
EMPLOYMENT_STATUSES = ("active", "on_leave", "suspended", "terminated")

_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "active": {"on_leave", "suspended", "terminated"},
    "on_leave": {"active", "terminated"},
    "suspended": {"active", "terminated"},
    "terminated": set(),
}


class Employee(Base, UUIDPKMixin, TimestampMixin):
    """Spec §27 employee profile.

    Deliberately a separate table from `identity.User`, linked by an optional
    `user_id`: every *system user* who is farm staff (e.g. a Farm Worker
    logging in to record weights) can have a matching Employee HR profile,
    but not every Employee needs system access (e.g. a casual laborer who
    never logs in). `user_id` is how the two are reconciled without forcing
    one model to do both jobs.
    """
    __tablename__ = "employees"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    employee_number: Mapped[str] = mapped_column(String(32), index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    department: Mapped[str | None] = mapped_column(String(128), nullable=True)  # e.g. livestock, dairy, sales
    job_title: Mapped[str | None] = mapped_column(String(128), nullable=True)
    employment_type: Mapped[str] = mapped_column(String(32), default="full_time")  # full_time|part_time|casual|contract
    employment_status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    assigned_farm_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("farms.id"), nullable=True)
    assigned_location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id"), nullable=True
    )
    hire_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    termination_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    shifts: Mapped[list["WorkShift"]] = relationship(back_populates="employee", cascade="all, delete-orphan")


class EmployeeStatusEvent(Base, UUIDPKMixin):
    """Append-only employment-status history - same rationale/mechanism as
    every other status trail in this codebase (spec §28: important actions,
    here specifically "role/employment changed", must be auditable)."""
    __tablename__ = "employee_status_events"

    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    to_status: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WorkShift(Base, UUIDPKMixin, TimestampMixin):
    """Spec §27 "work schedules" - a lightweight rota entry, not a full
    scheduling/attendance system (that stays future scope, per spec's own
    phrasing). Records who is expected where, when; does not track actual
    clock-in/clock-out (that's attendance, explicitly deferred)."""
    __tablename__ = "work_shifts"

    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), index=True)
    shift_date: Mapped[date] = mapped_column(Date, index=True)
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    location_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("locations.id"), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)

    employee: Mapped["Employee"] = relationship(back_populates="shifts")


class EmployeeCounter(Base):
    """Per-org gap-free employee numbering under a row lock - same pattern as
    finance.InvoiceCounter / procurement.PurchaseOrderCounter."""
    __tablename__ = "employee_counters"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    next_number: Mapped[int] = mapped_column(Integer, default=1)
