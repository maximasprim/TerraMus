import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

ENTERPRISE_PATTERN = "^(feedlot|fodder|crops|poultry|fish|rabbits|training|mixed)$"
STATUS_PATTERN = "^(planned|running|closed)$"


class CycleCreate(BaseModel):
    name: str | None = Field(default=None, max_length=120)          # default "Cycle {n}"
    cycle_number: int | None = Field(default=None, ge=1)             # default: next free number
    enterprise: str = Field(default="feedlot", pattern=ENTERPRISE_PATTERN)
    farm_id: uuid.UUID | None = None
    start_date: date | None = None
    end_date: date | None = None
    status: str = Field(default="planned", pattern="^(planned|running)$")
    notes: str | None = None

    @model_validator(mode="after")
    def _dates(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")
        return self


class CycleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    enterprise: str | None = Field(default=None, pattern=ENTERPRISE_PATTERN)
    farm_id: uuid.UUID | None = None
    start_date: date | None = None
    end_date: date | None = None
    notes: str | None = None


class CycleClose(BaseModel):
    end_date: date | None = None
    force: bool = Field(default=False, description="Close even though animals are still on feed (they stay in the cycle).")
    notes: str | None = None


class CycleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    cycle_number: int
    name: str
    enterprise: str
    status: str
    farm_id: uuid.UUID | None = None
    start_date: date | None = None
    end_date: date | None = None
    closed_at: datetime | None = None
    close_summary: dict | None = None
    notes: str | None = None
    created_at: datetime
    # filled by the service
    head_registered: int = 0
    head_active: int = 0
    intake_batches: int = 0


class CyclePreferences(BaseModel):
    default_view: str = Field(pattern="^(all|running)$")


class CyclePreferencesOut(BaseModel):
    default_view: str
    # What "running" resolves to right now: the id when there is exactly one running cycle, otherwise null
    # (with several running cycles the console stays on "all cycles" rather than guess).
    default_cycle_id: uuid.UUID | None = None
    running_cycles: int = 0


class DateWindow(BaseModel):
    from_date: date
    to_date: date
    tables: list[str] = Field(default_factory=list, description="Which kinds of record to tag; empty = all supported kinds")
    activity: str | None = Field(default=None, description="Only records of this activity (where the record has one)")
    farm_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _ok(self):
        if self.to_date < self.from_date:
            raise ValueError("to_date cannot be before from_date")
        return self


class AssignRequest(BaseModel):
    intake_batch_ids: list[uuid.UUID] = Field(default_factory=list)
    sale_batch_ids: list[uuid.UUID] = Field(default_factory=list)
    by_date: DateWindow | None = None
    dry_run: bool = Field(default=True, description="Preview only. Set false to apply.")
