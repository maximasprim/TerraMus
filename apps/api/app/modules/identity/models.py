import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Boolean, ForeignKey, Table, Column, DateTime, Numeric, Index, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, UUIDPKMixin, TimestampMixin


class Organization(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "organizations"
    # Many orgs may CLAIM a domain; only one may hold it VERIFIED (migration 0026).
    __table_args__ = (
        Index("uq_organizations_verified_custom_domain", "custom_domain", unique=True, postgresql_where=text("domain_verified")),
    )

    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    currency: Mapped[str] = mapped_column(String(8), default="KES")
    # Platform-admin superuser feature: a suspended org's users can no
    # longer log in or make authenticated requests (enforced in
    # identity/deps.py get_current_user). Additive column, defaults False,
    # every existing org is unaffected.
    is_suspended: Mapped[bool] = mapped_column(Boolean, default=False)
    # Custom domain for this org's public storefront (apps/web's
    # /shop/{slug} pages, reachable at e.g. farm.example.com instead of
    # yourapp.com/shop/farm-slug). custom_domain is the tenant-supplied
    # domain; domain_verification_token is the value they must publish as a
    # DNS TXT record before domain_verified flips to True — proof of DNS
    # control, checked independently of whether Vercel has already started
    # routing traffic there (see core/vercel_client.py's module docstring
    # for why that's not the same thing). Nothing reads custom_domain as
    # "live" for routing purposes unless domain_verified is also True.
    custom_domain: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    domain_verification_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    domain_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    domain_added_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Africa/Nairobi")
    # Spec §56/§57/§60 farm/organization configuration - added this session.
    # Every per-org sequential numbering scheme in this codebase (invoices,
    # purchase orders, employees, assets) previously hard-coded its prefix
    # ("INV-", "PO-", "EMP-", "AST-"); these four columns are what those
    # counter functions now read instead. tax_rate is a flat percentage
    # applied to invoice subtotals (spec §57: "Do not hard-code tax rates.
    # Make tax rules configurable") - deliberately a single flat rate, not a
    # full multi-bracket/product-category tax engine, since nothing in this
    # spec asks for more than that.
    invoice_prefix: Mapped[str] = mapped_column(String(16), default="INV")
    po_prefix: Mapped[str] = mapped_column(String(16), default="PO")
    employee_prefix: Mapped[str] = mapped_column(String(16), default="EMP")
    asset_prefix: Mapped[str] = mapped_column(String(16), default="AST")
    tax_rate: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    default_weight_unit: Mapped[str] = mapped_column(String(8), default="kg")
    default_volume_unit: Mapped[str] = mapped_column(String(8), default="L")

    users: Mapped[list["User"]] = relationship(back_populates="organization")
    roles: Mapped[list["Role"]] = relationship(back_populates="organization")


class User(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "users"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    email: Mapped[str] = mapped_column(String(255), index=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    organization: Mapped["Organization"] = relationship(back_populates="users")
    roles: Mapped[list["Role"]] = relationship(
        secondary="user_roles", back_populates="users", lazy="selectin"
    )
    # Nullable link to the Customer CRM record (modules/customers) - set only
    # for self-service customer-portal accounts (Phase 15), never for staff.
    # A plain string FK target ("customers.id") rather than an ORM
    # relationship: identity must not import the customers module (it would
    # invert the existing one-way dependency direction, where customers/
    # public/commerce import from identity, never the reverse).
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True, index=True
    )


class Permission(Base, UUIDPKMixin):
    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(128), unique=True, index=True)  # e.g. "livestock.create"
    description: Mapped[str] = mapped_column(String(255))


class Role(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "roles"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)

    organization: Mapped["Organization"] = relationship(back_populates="roles")
    permissions: Mapped[list["Permission"]] = relationship(secondary="role_permissions")
    users: Mapped[list["User"]] = relationship(secondary="user_roles", back_populates="roles")


role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", UUID(as_uuid=True), ForeignKey("roles.id"), primary_key=True),
    Column("permission_id", UUID(as_uuid=True), ForeignKey("permissions.id"), primary_key=True),
)

user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True),
    Column("role_id", UUID(as_uuid=True), ForeignKey("roles.id"), primary_key=True),
)


class RefreshToken(Base, UUIDPKMixin):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class PasswordResetToken(Base, UUIDPKMixin):
    """Spec §5 identity service: 'password reset.' Same hashed-token-at-rest
    pattern as RefreshToken directly above - only the SHA-256 hash is ever
    stored, the raw token exists only in the email sent to the user and the
    request that redeems it, so a database read alone can never produce a
    usable reset link. Short-lived (see identity/service.py's expiry) and
    single-use (`used_at` set on redemption, checked before allowing reuse)."""
    __tablename__ = "password_reset_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class AuditLog(Base, UUIDPKMixin):
    __tablename__ = "audit_logs"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(String(128))
    entity_type: Mapped[str] = mapped_column(String(128))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    previous_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
