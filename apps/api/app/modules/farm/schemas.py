import uuid
from pydantic import BaseModel, ConfigDict, Field


class LocationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    location_type: str = Field(pattern="^(paddock|barn|pen|grazing_area|quarantine)$")


class LocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    branch_id: uuid.UUID
    name: str
    location_type: str


class BranchCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class BranchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    farm_id: uuid.UUID
    name: str
    locations: list[LocationOut] = []


class FarmCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    county: str | None = None
    address: str | None = None


class FarmOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    county: str | None
    address: str | None
    branches: list[BranchOut] = []
