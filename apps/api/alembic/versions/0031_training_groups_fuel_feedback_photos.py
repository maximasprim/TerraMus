"""Training services, flock/fish groups, fuel logs, product feedback, animal photos.

Purely additive: new tables and new permission codes (seeded into the catalog and
granted to existing system roles).

Revision ID: 0031
Revises: 0030
"""
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects import postgresql as pg

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None

NEW_PERMISSIONS = [
    ("training.read", "View training courses, sessions and enrolments"),
    ("training.manage", "Manage training courses, sessions, enrolments and certificates"),
    ("groups.read", "View flocks / fish / rabbit groups and their records"),
    ("groups.record", "Record daily group data (mortality, eggs, feed, weights)"),
    ("groups.manage", "Create, sell and close flocks / fish / rabbit groups"),
]
GRANTS = {
    "Farm Owner": [c for c, _ in NEW_PERMISSIONS],
    "Farm Manager": [c for c, _ in NEW_PERMISSIONS],
    "Livestock Manager": ["groups.read", "groups.record", "groups.manage"],
    "Farm Worker": ["groups.read", "groups.record"],
    "Veterinarian": ["groups.read"],
    "Sales Manager": ["training.read", "training.manage"],
    "Accountant": ["training.read", "groups.read"],
}


def _ts():
    return [sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False)]


def _org():
    return sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False)


def upgrade() -> None:
    op.create_table(
        "training_courses", sa.Column("id", pg.UUID(as_uuid=True), primary_key=True), _org(),
        sa.Column("title", sa.String(200), nullable=False), sa.Column("description", sa.Text, nullable=True),
        sa.Column("category", sa.String(60), nullable=True), sa.Column("duration_days", sa.Integer, nullable=False, server_default="1"),
        sa.Column("fee", sa.Numeric(12, 2), nullable=False, server_default="0"), sa.Column("capacity", sa.Integer, nullable=True),
        sa.Column("trainer", sa.String(160), nullable=True), sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        *_ts())
    op.create_index("ix_training_courses_organization_id", "training_courses", ["organization_id"])

    op.create_table(
        "training_sessions", sa.Column("id", pg.UUID(as_uuid=True), primary_key=True), _org(),
        sa.Column("course_id", pg.UUID(as_uuid=True), sa.ForeignKey("training_courses.id"), nullable=False),
        sa.Column("farm_id", pg.UUID(as_uuid=True), sa.ForeignKey("farms.id"), nullable=True),
        sa.Column("start_date", sa.Date, nullable=False), sa.Column("end_date", sa.Date, nullable=False),
        sa.Column("venue", sa.String(200), nullable=True), sa.Column("capacity", sa.Integer, nullable=True),
        sa.Column("fee", sa.Numeric(12, 2), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="scheduled"), sa.Column("notes", sa.Text, nullable=True),
        *_ts(), sa.CheckConstraint("status in ('scheduled','in_progress','completed','cancelled')", name="valid_session_status"),
        sa.CheckConstraint("end_date >= start_date", name="valid_dates"))
    op.create_index("ix_training_sessions_organization_id", "training_sessions", ["organization_id"])
    op.create_index("ix_training_sessions_course_id", "training_sessions", ["course_id"])

    op.create_table(
        "training_enrolments", sa.Column("id", pg.UUID(as_uuid=True), primary_key=True), _org(),
        sa.Column("session_id", pg.UUID(as_uuid=True), sa.ForeignKey("training_sessions.id"), nullable=False),
        sa.Column("customer_id", pg.UUID(as_uuid=True), sa.ForeignKey("customers.id"), nullable=True),
        sa.Column("participant_name", sa.String(200), nullable=False), sa.Column("phone", sa.String(40), nullable=True),
        sa.Column("email", sa.String(255), nullable=True), sa.Column("fee_charged", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="registered"),
        sa.Column("certificate_number", sa.String(40), nullable=True), sa.Column("certificate_issued_on", sa.Date, nullable=True),
        *_ts(), sa.UniqueConstraint("organization_id", "certificate_number"),
        sa.CheckConstraint("status in ('registered','attended','completed','no_show','cancelled')", name="valid_enrolment_status"))
    op.create_index("ix_training_enrolments_organization_id", "training_enrolments", ["organization_id"])
    op.create_index("ix_training_enrolments_session_id", "training_enrolments", ["session_id"])

    op.create_table(
        "training_attendance", sa.Column("id", pg.UUID(as_uuid=True), primary_key=True), _org(),
        sa.Column("enrolment_id", pg.UUID(as_uuid=True), sa.ForeignKey("training_enrolments.id"), nullable=False),
        sa.Column("day", sa.Date, nullable=False), sa.Column("present", sa.Boolean, nullable=False),
        sa.UniqueConstraint("enrolment_id", "day"))
    op.create_index("ix_training_attendance_organization_id", "training_attendance", ["organization_id"])

    op.create_table(
        "animal_groups", sa.Column("id", pg.UUID(as_uuid=True), primary_key=True), _org(),
        sa.Column("farm_id", pg.UUID(as_uuid=True), sa.ForeignKey("farms.id"), nullable=True),
        sa.Column("code", sa.String(40), nullable=False), sa.Column("name", sa.String(160), nullable=False),
        sa.Column("species", sa.String(16), nullable=False), sa.Column("purpose", sa.String(24), nullable=True),
        sa.Column("breed", sa.String(80), nullable=True), sa.Column("source", sa.String(160), nullable=True),
        sa.Column("start_date", sa.Date, nullable=False), sa.Column("initial_count", sa.Integer, nullable=False),
        sa.Column("current_count", sa.Integer, nullable=False), sa.Column("acquisition_cost", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(12), nullable=False, server_default="active"), sa.Column("closed_on", sa.Date, nullable=True),
        sa.Column("notes", sa.Text, nullable=True), *_ts(), sa.UniqueConstraint("organization_id", "code"),
        sa.CheckConstraint("species in ('poultry','rabbits','fish','pigs','other')", name="valid_species"),
        sa.CheckConstraint("status in ('active','closed')", name="valid_status"),
        sa.CheckConstraint("initial_count > 0 and current_count >= 0", name="valid_counts"))
    op.create_index("ix_animal_groups_organization_id", "animal_groups", ["organization_id"])

    op.create_table(
        "group_records", sa.Column("id", pg.UUID(as_uuid=True), primary_key=True), _org(),
        sa.Column("group_id", pg.UUID(as_uuid=True), sa.ForeignKey("animal_groups.id"), nullable=False),
        sa.Column("record_date", sa.Date, nullable=False), sa.Column("record_type", sa.String(16), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 2), nullable=False), sa.Column("unit", sa.String(16), nullable=True),
        sa.Column("value", sa.Numeric(12, 2), nullable=True), sa.Column("avg_weight_kg", sa.Numeric(8, 3), nullable=True),
        sa.Column("product", sa.String(24), nullable=True),
        sa.Column("customer_id", pg.UUID(as_uuid=True), sa.ForeignKey("customers.id"), nullable=True),
        sa.Column("notes", sa.String(255), nullable=True), sa.Column("created_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("record_type in ('mortality','cull','production','feed','weight_sample','sale','addition')", name="valid_record_type"),
        sa.CheckConstraint("quantity >= 0", name="non_negative_quantity"))
    op.create_index("ix_group_records_organization_id", "group_records", ["organization_id"])
    op.create_index("ix_group_records_group_id", "group_records", ["group_id"])
    op.create_index("ix_group_records_record_date", "group_records", ["record_date"])

    op.create_table(
        "fuel_logs", sa.Column("id", pg.UUID(as_uuid=True), primary_key=True), _org(),
        sa.Column("asset_id", pg.UUID(as_uuid=True), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("farm_id", pg.UUID(as_uuid=True), sa.ForeignKey("farms.id"), nullable=True),
        sa.Column("log_date", sa.Date, nullable=False), sa.Column("litres", sa.Numeric(8, 2), nullable=False),
        sa.Column("cost", sa.Numeric(12, 2), nullable=False, server_default="0"), sa.Column("meter_reading", sa.Numeric(12, 1), nullable=True),
        sa.Column("purpose", sa.String(120), nullable=True), sa.Column("activity", sa.String(24), nullable=True),
        sa.Column("driver", sa.String(120), nullable=True), sa.Column("finance_transaction_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", pg.UUID(as_uuid=True), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("litres > 0 and cost >= 0", name="valid_amounts"))
    op.create_index("ix_fuel_logs_organization_id", "fuel_logs", ["organization_id"])
    op.create_index("ix_fuel_logs_asset_id", "fuel_logs", ["asset_id"])
    op.create_index("ix_fuel_logs_log_date", "fuel_logs", ["log_date"])

    op.create_table(
        "product_feedback", sa.Column("id", pg.UUID(as_uuid=True), primary_key=True), _org(),
        sa.Column("listing_id", pg.UUID(as_uuid=True), sa.ForeignKey("listings.id"), nullable=True),
        sa.Column("customer_name", sa.String(120), nullable=False), sa.Column("rating", sa.Integer, nullable=False),
        sa.Column("comment", sa.String(1000), nullable=True), sa.Column("status", sa.String(12), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("moderated_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("moderated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("rating between 1 and 5", name="valid_rating"),
        sa.CheckConstraint("status in ('pending','approved','rejected')", name="valid_status"))
    op.create_index("ix_product_feedback_organization_id", "product_feedback", ["organization_id"])
    op.create_index("ix_product_feedback_listing_id", "product_feedback", ["listing_id"])

    op.create_table(
        "animal_photos", sa.Column("id", pg.UUID(as_uuid=True), primary_key=True), _org(),
        sa.Column("animal_id", pg.UUID(as_uuid=True), sa.ForeignKey("animals.id"), nullable=False, unique=True),
        sa.Column("content_type", sa.String(40), nullable=False), sa.Column("data", sa.LargeBinary, nullable=False),
        sa.Column("width", sa.Integer, nullable=False), sa.Column("height", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_animal_photos_organization_id", "animal_photos", ["organization_id"])
    _seed_permissions()


def _seed_permissions() -> None:
    bind = op.get_bind()
    existing = {r[0] for r in bind.execute(text("SELECT code FROM permissions")).fetchall()}
    for code, desc in NEW_PERMISSIONS:
        if code not in existing:
            bind.execute(text("INSERT INTO permissions (id, code, description) VALUES (:i, :c, :d)"), {"i": str(uuid.uuid4()), "c": code, "d": desc})
    pid = {c: str(i) for i, c in bind.execute(text("SELECT id, code FROM permissions")).fetchall()}
    for role_id, name in bind.execute(text("SELECT id, name FROM roles WHERE is_system = true")).fetchall():
        for code in GRANTS.get(name, []):
            bind.execute(text("INSERT INTO role_permissions (role_id, permission_id) VALUES (:r, :p) ON CONFLICT (role_id, permission_id) DO NOTHING"),
                         {"r": str(role_id), "p": pid[code]})


def downgrade() -> None:
    bind = op.get_bind()
    codes = [c for c, _ in NEW_PERMISSIONS]
    bind.execute(text("DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code = ANY(:c))"), {"c": codes})
    bind.execute(text("DELETE FROM permissions WHERE code = ANY(:c)"), {"c": codes})
    for t in ("animal_photos", "product_feedback", "fuel_logs", "group_records", "animal_groups", "training_attendance",
              "training_enrolments", "training_sessions", "training_courses"):
        op.drop_table(t)
