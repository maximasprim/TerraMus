"""Phase 1: organizations, identity/RBAC, farm/branch/location, audit_logs

Revision ID: 0001
Revises:
Create Date: 2026-08-09

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="KES"),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Africa/Nairobi"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
    )

    op.create_table(
        "permissions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(128), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.UniqueConstraint("code", name="uq_permissions_code"),
    )

    op.create_table(
        "roles",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("is_system", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_roles_organization_id", "roles", ["organization_id"])

    op.create_table(
        "role_permissions",
        sa.Column("role_id", pg.UUID(as_uuid=True), sa.ForeignKey("roles.id"), primary_key=True),
        sa.Column("permission_id", pg.UUID(as_uuid=True), sa.ForeignKey("permissions.id"), primary_key=True),
    )

    op.create_table(
        "users",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("mfa_enabled", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_organization_id", "users", ["organization_id"])
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "user_roles",
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("role_id", pg.UUID(as_uuid=True), sa.ForeignKey("roles.id"), primary_key=True),
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("entity_type", sa.String(128), nullable=False),
        sa.Column("entity_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("previous_value", pg.JSONB, nullable=True),
        sa.Column("new_value", pg.JSONB, nullable=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_logs_organization_id", "audit_logs", ["organization_id"])

    op.create_table(
        "farms",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("county", sa.String(128), nullable=True),
        sa.Column("address", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_farms_organization_id", "farms", ["organization_id"])

    op.create_table(
        "branches",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("farm_id", pg.UUID(as_uuid=True), sa.ForeignKey("farms.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_branches_farm_id", "branches", ["farm_id"])

    op.create_table(
        "locations",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("branch_id", pg.UUID(as_uuid=True), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("location_type", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_locations_branch_id", "locations", ["branch_id"])


def downgrade() -> None:
    op.drop_table("locations")
    op.drop_table("branches")
    op.drop_table("farms")
    op.drop_table("audit_logs")
    op.drop_table("refresh_tokens")
    op.drop_table("user_roles")
    op.drop_table("users")
    op.drop_table("role_permissions")
    op.drop_table("roles")
    op.drop_table("permissions")
    op.drop_table("organizations")
