import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field, model_validator


class CourseCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str | None = None
    category: str | None = None
    duration_days: int = Field(default=1, ge=1, le=365)
    fee: Decimal = Field(default=Decimal("0"), ge=0)
    capacity: int | None = Field(default=None, ge=1)
    trainer: str | None = None


class CourseUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = None
    category: str | None = None
    duration_days: int | None = Field(default=None, ge=1, le=365)
    fee: Decimal | None = Field(default=None, ge=0)
    capacity: int | None = Field(default=None, ge=1)
    trainer: str | None = None
    is_active: bool | None = None


class SessionCreate(BaseModel):
    course_id: uuid.UUID
    start_date: date
    end_date: date | None = None            # defaults to start + course duration - 1
    farm_id: uuid.UUID | None = None
    venue: str | None = None
    capacity: int | None = Field(default=None, ge=1)
    fee: Decimal | None = Field(default=None, ge=0)
    notes: str | None = None


class SessionUpdate(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    venue: str | None = None
    capacity: int | None = Field(default=None, ge=1)
    fee: Decimal | None = Field(default=None, ge=0)
    status: str | None = Field(default=None, pattern="^(scheduled|in_progress|completed|cancelled)$")
    notes: str | None = None


class EnrolRequest(BaseModel):
    participant_name: str = Field(min_length=2, max_length=200)
    phone: str | None = None
    email: EmailStr | None = None
    customer_id: uuid.UUID | None = None
    fee_override: Decimal | None = Field(default=None, ge=0)
    bill: bool = True                       # create a charge on the participant's customer account


class EnrolmentStatusUpdate(BaseModel):
    status: str = Field(pattern="^(registered|attended|completed|no_show|cancelled)$")


class AttendanceMark(BaseModel):
    day: date
    present: bool = True


class CertificateRequest(BaseModel):
    force: bool = False                     # issue even if attendance is below the minimum
