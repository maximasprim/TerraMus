import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class PlatformAdminLoginRequest(BaseModel):
    email: EmailStr
    password: str


class PlatformAdminTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PlatformAdminOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    role: str

    class Config:
        from_attributes = True


class OrganizationSummaryOut(BaseModel):
    """Cross-tenant admin view of an org - intentionally separate from
    identity.schemas' tenant-facing OrganizationOut, which a regular user
    sees for their own org only. This one adds fields (suspension status,
    user counts, subscription tier) that no tenant user should ever see
    about their own org via a self-service endpoint."""
    id: uuid.UUID
    name: str
    slug: str
    currency: str
    is_suspended: bool
    user_count: int
    subscription_tier: str | None
    subscription_status: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class OrganizationStatusUpdate(BaseModel):
    is_suspended: bool
    reason: str | None = None


class PlatformAdminCreateRequest(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    role: str = Field("superadmin", pattern="^(superadmin|viewer)$")


class PlatformAdminStatusUpdate(BaseModel):
    is_active: bool


class PlatformAdminRoleUpdate(BaseModel):
    role: str = Field(pattern="^(superadmin|viewer)$")


class PlatformAdminPasswordResetRequest(BaseModel):
    email: EmailStr


class PlatformAdminPasswordResetConfirm(BaseModel):
    token: str
    new_password: str


class PlatformDashboardStats(BaseModel):
    total_organizations: int
    active_organizations: int
    suspended_organizations: int
    total_users: int
    organizations_by_tier: dict[str, int]
    mrr_kes: float  # sum of active subscriptions' monthly_price_kes
    signups_last_30_days: int


class LifecycleCheckResult(BaseModel):
    marked_past_due: int
    marked_cancelled: int
    skipped: bool = False
