"""Allow the payment status 'needs_review'.

Used when money may have moved but the order cannot be settled cleanly (amount differs, receipt already used,
order cancelled or already paid). It lets the webhook ACCEPT the callback and record the payment for a person to
resolve, instead of rejecting it (which rolled everything back and left received money unrecorded).

Revision ID: 0033
Revises: 0032
"""
from alembic import op
from sqlalchemy import text

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None

OLD = "'initiated','pending','successful','failed','cancelled','refunded','partially_refunded'"


def upgrade() -> None:
    op.drop_constraint("valid_payment_status", "payments", type_="check")
    op.create_check_constraint("valid_payment_status", "payments", f"status in ({OLD},'needs_review')")


def downgrade() -> None:
    n = op.get_bind().execute(text("SELECT count(*) FROM payments WHERE status = 'needs_review'")).scalar()
    if n:
        raise RuntimeError(f"Cannot downgrade: {n} payment(s) are awaiting review. Resolve them first (they represent real money).")
    op.drop_constraint("valid_payment_status", "payments", type_="check")
    op.create_check_constraint("valid_payment_status", "payments", f"status in ({OLD})")
