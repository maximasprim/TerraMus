"""Two small follow-ups to 0020/0021:

1. `listings.low_stock_threshold` (nullable, crop-produce listings only) -
   lets staff say "warn me when less than X kg/bags/etc. remain unsold",
   mirroring inventory's reorder_level concept but for a computed crop-stock
   ledger rather than a stored counter.
2. Backfill "listings.manage" and "orders.manage" onto the "Crop Manager"
   role identity/permissions.py's DEFAULT_ROLE_GRANTS now includes (needed
   so a Crop Manager can actually sell what they grow, not just record it) -
   for every EXISTING organization, since roles are seeded once at
   registration time and this role predates having these two permissions.

Revision ID: 0022
Revises: 0021
Create Date: 2026-09-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None

CROP_MANAGER_NEW_PERMISSIONS = ["listings.manage", "orders.manage", "livestock.read"]


def upgrade() -> None:
    op.add_column("listings", sa.Column("low_stock_threshold", sa.Numeric(12, 2), nullable=True))

    bind = op.get_bind()
    perm_rows = bind.execute(
        text("SELECT id, code FROM permissions WHERE code = ANY(:codes)"),
        {"codes": CROP_MANAGER_NEW_PERMISSIONS},
    ).fetchall()
    perm_id_by_code = {code: str(pid) for pid, code in perm_rows}

    role_rows = bind.execute(
        text("SELECT id FROM roles WHERE name = 'Crop Manager' AND is_system = true")
    ).fetchall()
    for role_id, in role_rows:
        for code in CROP_MANAGER_NEW_PERMISSIONS:
            perm_id = perm_id_by_code.get(code)
            if not perm_id:
                continue
            bind.execute(
                text(
                    "INSERT INTO role_permissions (role_id, permission_id) VALUES (:role_id, :permission_id) "
                    "ON CONFLICT (role_id, permission_id) DO NOTHING"
                ),
                {"role_id": str(role_id), "permission_id": perm_id},
            )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(text("""
        DELETE FROM role_permissions
        WHERE role_id IN (SELECT id FROM roles WHERE name = 'Crop Manager' AND is_system = true)
        AND permission_id IN (SELECT id FROM permissions WHERE code = ANY(:codes))
    """), {"codes": CROP_MANAGER_NEW_PERMISSIONS})
    op.drop_column("listings", "low_stock_threshold")
