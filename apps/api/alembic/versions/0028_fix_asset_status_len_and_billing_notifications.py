"""Fix two column/constraint mismatches found by running the full test suite.

1. assets.status was VARCHAR(16) but the valid status 'under_maintenance' is 17
   characters, so setting an asset to that status failed at the database
   (StringDataRightTruncation) even though the schema and CHECK allow it.
   Widened to VARCHAR(32).

2. billing/service.py emits notifications with category 'billing', but the
   notifications CHECK constraint only allowed
   health/breeding/inventory/orders/payments/system, so the notification
   inserted after a successful subscription payment violated the constraint and
   broke the webhook. 'billing' is now an allowed category.

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None

_OLD = "category in ('health','breeding','inventory','orders','payments','system')"
_NEW = "category in ('health','breeding','inventory','orders','payments','system','billing')"


def upgrade() -> None:
    op.alter_column("assets", "status", type_=sa.String(32), existing_type=sa.String(16),
                    existing_nullable=False, existing_server_default="in_use")
    op.drop_constraint("valid_notification_category", "notifications", type_="check")
    op.create_check_constraint("valid_notification_category", "notifications", _NEW)


def downgrade() -> None:
    # Rows already using the new values would violate the old definitions.
    op.execute("DELETE FROM notifications WHERE category = 'billing'")
    op.execute("UPDATE assets SET status = 'in_storage' WHERE status = 'under_maintenance'")
    op.drop_constraint("valid_notification_category", "notifications", type_="check")
    op.create_check_constraint("valid_notification_category", "notifications", _OLD)
    op.alter_column("assets", "status", type_=sa.String(16), existing_type=sa.String(32),
                    existing_nullable=False, existing_server_default="in_use")
