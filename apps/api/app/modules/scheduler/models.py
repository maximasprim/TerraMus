import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UUIDPKMixin


class AlertLog(Base, UUIDPKMixin):
    """When each alert was last sent, so a daily check does not repeat itself every single day."""
    __tablename__ = "alert_log"
    __table_args__ = (UniqueConstraint("organization_id", "alert_key"),)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    alert_key: Mapped[str] = mapped_column(String(200))
    last_sent_on: Mapped[date] = mapped_column(Date)
    times_sent: Mapped[int] = mapped_column(Integer, default=1)


class SchedulerRun(Base, UUIDPKMixin):
    """One row per job per day. The unique (job, run_date) IS the lock: whichever server inserts it runs the job."""
    __tablename__ = "scheduler_runs"
    __table_args__ = (UniqueConstraint("job", "run_date"),
                      CheckConstraint("status in ('running','ok','partial','failed')", name="valid_status"))
    job: Mapped[str] = mapped_column(String(60))
    run_date: Mapped[date] = mapped_column(Date)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="running")
    summary: Mapped[dict] = mapped_column(JSONB, default=dict)
