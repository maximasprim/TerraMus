import uuid
from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, EmailStr, Field

EMPLOYMENT_STATUS_PATTERN = "^(active|on_leave|suspended|terminated)$"
EMPLOYMENT_TYPE_PATTERN = "^(full_time|part_time|casual|contract)$"


class EmployeeCreate(BaseModel):
    user_id: uuid.UUID | None = None
    full_name: str = Field(min_length=1, max_length=255)
    phone: str | None = None
    email: EmailStr | None = None
    department: str | None = None
    job_title: str | None = None
    employment_type: str = Field(default="full_time", pattern=EMPLOYMENT_TYPE_PATTERN)
    assigned_farm_id: uuid.UUID | None = None
    assigned_location_id: uuid.UUID | None = None
    hire_date: date | None = None
    notes: str | None = None


class EmployeeUpdate(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    department: str | None = None
    job_title: str | None = None
    employment_type: str | None = Field(default=None, pattern=EMPLOYMENT_TYPE_PATTERN)
    assigned_farm_id: uuid.UUID | None = None
    assigned_location_id: uuid.UUID | None = None
    notes: str | None = None


class EmployeeStatusUpdate(BaseModel):
    status: str = Field(pattern=EMPLOYMENT_STATUS_PATTERN)
    reason: str | None = None
    effective_date: date | None = None  # used only for status == terminated -> termination_date


class EmployeeStatusEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    from_status: str | None
    to_status: str
    reason: str | None
    changed_by: uuid.UUID | None
    changed_at: datetime


class EmployeeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID | None
    employee_number: str
    full_name: str
    phone: str | None
    email: str | None
    department: str | None
    job_title: str | None
    employment_type: str
    employment_status: str
    assigned_farm_id: uuid.UUID | None
    assigned_location_id: uuid.UUID | None
    hire_date: date | None
    termination_date: date | None
    notes: str | None
    created_at: datetime


class EmployeeDetailOut(EmployeeOut):
    status_history: list[EmployeeStatusEventOut]


class WorkShiftCreate(BaseModel):
    shift_date: date
    start_time: time | None = None
    end_time: time | None = None
    location_id: uuid.UUID | None = None
    notes: str | None = None


class WorkShiftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    employee_id: uuid.UUID
    shift_date: date
    start_time: time | None
    end_time: time | None
    location_id: uuid.UUID | None
    notes: str | None
