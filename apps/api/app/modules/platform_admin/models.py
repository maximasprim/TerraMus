import uuid
from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UUIDPKMixin, TimestampMixin


class PlatformAdmin(Base, UUIDPKMixin, TimestampMixin):
    """A platform/superuser account with cross-tenant visibility.

    Deliberately its OWN table, not a row in `users` and not an
    `organization_id`-scoped `Role` -- a platform admin is not a member of
    any tenant at all. This is a security boundary, not just a modeling
    choice: every existing tenant query in this codebase filters by
    `organization_id` (see docs/architecture.md "Tenant isolation" and the
    ~80 manual `.where(Model.organization_id == org_id)` filters across
    services). If platform-admin access were instead modeled as "a role
    with a magic permission" on the existing `User`/`Role` tables, a single
    missed filter or RBAC bug could accidentally leak cross-tenant access.
    Keeping it a wholly separate model + table + JWT token type (see
    security.py) means a bug in tenant RBAC structurally cannot grant
    platform-admin rights, and vice versa.
    """
    __tablename__ = "platform_admins"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # "superadmin" (default) can read AND write everything under /api/v1/platform.
    # "viewer" can only ever GET - enforced in deps.py's require_write_access,
    # not per-endpoint, so this one field covers every current and future
    # platform-admin route without needing to touch each one individually.
    role: Mapped[str] = mapped_column(String(16), default="superadmin")


class PlatformAdminPasswordResetToken(Base, UUIDPKMixin):
    """Same hashed-token-at-rest / short-lived / single-use pattern as
    identity.models.PasswordResetToken -- kept as a separate table rather
    than adding a nullable platform_admin_id to the existing one, because
    that table's FK is (correctly) non-nullable to users.id and widening it
    would touch a table tenant auth already depends on. This one is net-new
    and entirely additive."""
    __tablename__ = "platform_admin_password_reset_tokens"

    platform_admin_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform_admins.id"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
