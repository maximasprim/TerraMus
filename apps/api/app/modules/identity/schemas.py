import uuid
from datetime import datetime
from decimal import Decimal

from app.core.emailnorm import NormalizedEmail
from pydantic import BaseModel, ConfigDict, Field, field_validator


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    slug: str
    currency: str
    timezone: str
    invoice_prefix: str
    po_prefix: str
    employee_prefix: str
    asset_prefix: str
    tax_rate: Decimal
    default_weight_unit: str
    default_volume_unit: str


class OrganizationSettingsUpdate(BaseModel):
    """Spec §60 farm configuration. Deliberately excludes `name`/`slug` -
    the slug is baked into every public storefront URL and QR code already
    generated (spec §38/§45), so changing it silently would break links
    already handed out; renaming the organization is a bigger, separate
    operation this endpoint doesn't attempt."""
    currency: str | None = Field(default=None, min_length=3, max_length=8)
    timezone: str | None = None
    invoice_prefix: str | None = Field(default=None, min_length=1, max_length=16)
    po_prefix: str | None = Field(default=None, min_length=1, max_length=16)
    employee_prefix: str | None = Field(default=None, min_length=1, max_length=16)
    asset_prefix: str | None = Field(default=None, min_length=1, max_length=16)
    tax_rate: Decimal | None = Field(default=None, ge=0, le=100)
    default_weight_unit: str | None = Field(default=None, min_length=1, max_length=8)
    default_volume_unit: str | None = Field(default=None, min_length=1, max_length=8)


class RegisterRequest(BaseModel):
    organization_name: str = Field(min_length=2, max_length=255)
    full_name: str = Field(min_length=2, max_length=255)
    email: NormalizedEmail
    phone: str | None = None
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: NormalizedEmail
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    organization_id: uuid.UUID
    email: NormalizedEmail
    full_name: str
    phone: str | None
    is_active: bool
    created_at: datetime
    roles: list[RoleOut] = []


class MeResponse(BaseModel):
    user: UserOut
    organization: OrganizationOut
    permissions: list[str]


class CreateUserRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    email: NormalizedEmail
    phone: str | None = None
    password: str = Field(min_length=8, max_length=128)
    role_ids: list[uuid.UUID] = []


class UpdateUserRolesRequest(BaseModel):
    role_ids: list[uuid.UUID]


class AuditLogOut(BaseModel):
    user_name: str | None = None  # resolved actor name (None for system / platform-support actions)
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    user_id: uuid.UUID | None
    action: str
    entity_type: str
    entity_id: uuid.UUID | None
    previous_value: dict | None
    new_value: dict | None
    created_at: datetime


class PasswordResetRequest(BaseModel):
    email: NormalizedEmail


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class DomainSetRequest(BaseModel):
    domain: str = Field(min_length=3, max_length=255, description="e.g. farm.example.com")

    @field_validator("domain")
    @classmethod
    def _must_be_a_real_hostname(cls, value: str) -> str:
        from app.core.config import get_settings
        from app.core.domain_validation import hosts_from_urls, normalise_domain

        s = get_settings()
        return normalise_domain(value, hosts_from_urls([s.PUBLIC_SITE_BASE_URL, *s.CORS_ORIGINS]))


class DnsInstructions(BaseModel):
    a_record: str
    cname_record: str
    txt_record_name: str
    txt_record_value: str


class DomainStatusOut(BaseModel):
    domain: str | None
    verified: bool
    dns_instructions: DnsInstructions | None = None
    vercel_status: str | None = None

